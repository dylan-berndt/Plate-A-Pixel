import numpy as np
from OpenGL import GL
from OpenGL.GL import shaders as GLShaders
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt

from .ui import *
from .data import *

# The base plate isn't a palette color (see Mesh._calculateMesh - it's
# appended past the real palette, len(palette)) - this is just a fixed
# tan to render it as, sampled from design/ui-mockup.html's base plate.
BASE_COLOR = (196, 168, 140)

VERTEX_SHADER = """
#version 150
in vec3 position;
in vec3 normal;
uniform mat4 uMVP;
out vec3 vNormal;
void main() {
    vNormal = normal;
    gl_Position = uMVP * vec4(position, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 150
in vec3 vNormal;
uniform vec3 uColor;
uniform vec3 uLightDir;
out vec4 fragColor;
void main() {
    vec3 n = normalize(vNormal);
    // abs(), not max(dot, 0): per-triangle normals aren't consistently
    // outward-facing (see the no-culling note in initializeGL - the same
    // trimesh winding inconsistency would otherwise light a real chunk of
    // faces as if they pointed away from the light, rendering them near-
    // black instead of matching their neighbors).
    float diffuse = abs(dot(n, normalize(-uLightDir)));
    vec3 lit = uColor * 0.4 + uColor * diffuse * 0.7;
    fragColor = vec4(min(lit, vec3(1.0)), 1.0);
}
"""


def _perspective(fovYRadians, aspect, near, far):
    f = 1.0 / np.tan(fovYRadians / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / max(aspect, 1e-6)
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def _lookAt(eye, target, up):
    eye = np.asarray(eye, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)
    forward = target - eye
    norm = np.linalg.norm(forward)
    forward = forward / norm if norm > 1e-8 else np.array([0, 0, -1], dtype=np.float32)
    side = np.cross(forward, up)
    sideNorm = np.linalg.norm(side)
    side = side / sideNorm if sideNorm > 1e-8 else np.array([1, 0, 0], dtype=np.float32)
    trueUp = np.cross(side, forward)

    m = np.eye(4, dtype=np.float32)
    m[0, :3], m[1, :3], m[2, :3] = side, trueUp, -forward
    m[0, 3] = -np.dot(side, eye)
    m[1, 3] = -np.dot(trueUp, eye)
    m[2, 3] = np.dot(forward, eye)
    return m


def _trianglesToArrays(triangles):
    """A flat Vector3 list (3 per triangle - see Mesh.meshes) into
    (positions, normals) float32 arrays. Normals are flat per-triangle
    (the same face normal repeated for all 3 corners) rather than
    vertex-averaged - these are boxy, axis-aligned pixel solids
    (pixelComponents.py), so a hard-edged low-poly look is the correct
    one, not smoothed shading."""
    positions = np.array([(v.x, v.y, v.z) for v in triangles], dtype=np.float32)
    normals = np.zeros_like(positions)
    for i in range(0, len(positions), 3):
        a, b, c = positions[i], positions[i + 1], positions[i + 2]
        n = np.cross(b - a, c - a)
        length = np.linalg.norm(n)
        if length > 1e-8:
            n = n / length
        normals[i:i + 3] = n
    return positions, normals


class _ColorBuffer:
    """One color's worth of GPU geometry - every component sharing that
    color gets concatenated into a single VBO, since they all draw with
    the same uColor anyway (see MeshElement._rebuildBuffers)."""

    def __init__(self, color, positions, normals):
        self.color = tuple(c / 255.0 for c in color)
        self.vertexCount = len(positions)
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)

        self.positionVbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.positionVbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, positions.nbytes, positions, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self.normalVbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.normalVbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, normals.nbytes, normals, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        GL.glBindVertexArray(0)

    def destroy(self):
        GL.glDeleteBuffers(2, [self.positionVbo, self.normalVbo])
        GL.glDeleteVertexArrays(1, [self.vao])


class MeshElement(QOpenGLWidget):
    """The 3D print preview: one draw call per palette color (plus the
    base plate), each a flat-shaded solid built straight from
    Project.mesh.meshes (see data/mesh.py) - no separate scene graph,
    since a Mesh's own per-color grouping is already exactly the
    draw-call grouping this needs.

    Orbits on left-drag, pans on middle-drag (matching CanvasArea's own
    middle-mouse pan, for one consistent gesture across both views),
    zooms on the wheel."""

    def __init__(self, theme: Theme = None, **kwargs):
        super().__init__(**kwargs)
        self._theme = theme or Theme()
        self._projectController = None
        self._colorBuffers = []
        self._program = None
        self._meshDirty = False

        self.yaw = np.radians(45)
        self.pitch = np.radians(30)
        self.distance = 10.0
        self.target = np.zeros(3, dtype=np.float32)

        self._dragButton = None
        self._lastPos = None

    def bindProject(self, projectController):
        if self._projectController is not None:
            self._projectController.meshReady.disconnect(self._onMeshChanged)
            self._projectController.meshInvalidated.disconnect(self._onMeshChanged)
        self._projectController = projectController
        if projectController is not None:
            projectController.meshReady.connect(self._onMeshChanged)
            projectController.meshInvalidated.connect(self._onMeshChanged)
        self._meshDirty = True
        self._resetCamera = True
        self.update()

    def _onMeshChanged(self):
        self._meshDirty = True
        self.update()

    # -- GL lifecycle -----------------------------------------------------

    def initializeGL(self):
        GL.glEnable(GL.GL_DEPTH_TEST)
        # No face culling: trimesh's boolean union/difference output (see
        # componentTriangles in pixelComponents.py) doesn't guarantee
        # consistent CCW winding across a merged solid's triangles - measured
        # ~30% of a raised pixel's faces wound the "wrong" way after a
        # union. Culling on that basis would silently drop real, visible
        # geometry rather than just cost a bit of harmless overdraw on this
        # low-poly mesh.
        theme = self._theme
        r, g, b = (int(theme.clay200[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        GL.glClearColor(r, g, b, 1.0)
        self._program = GLShaders.compileProgram(
            GLShaders.compileShader(VERTEX_SHADER, GL.GL_VERTEX_SHADER),
            GLShaders.compileShader(FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER),
        )

    def resizeGL(self, w, h):
        GL.glViewport(0, 0, max(1, w), max(1, h))

    def paintGL(self):
        if self._meshDirty:
            self._rebuildBuffers()
            self._meshDirty = False

        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if not self._colorBuffers:
            return

        aspect = self.width() / max(1, self.height())
        view = self._viewMatrix()
        projection = _perspective(np.radians(45), aspect, 0.1, max(self.distance * 4, 10.0))
        mvp = projection @ view

        GL.glUseProgram(self._program)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program, "uMVP"), 1, GL.GL_TRUE, mvp.astype(np.float32))
        GL.glUniform3f(GL.glGetUniformLocation(self._program, "uLightDir"), -0.4, -1.0, -0.3)
        colorLoc = GL.glGetUniformLocation(self._program, "uColor")

        for buffer in self._colorBuffers:
            GL.glUniform3f(colorLoc, *buffer.color)
            GL.glBindVertexArray(buffer.vao)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, buffer.vertexCount)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)

    def _viewMatrix(self):
        eye = self.target + self.distance * np.array([
            np.cos(self.pitch) * np.sin(self.yaw),
            np.sin(self.pitch),
            np.cos(self.pitch) * np.cos(self.yaw),
        ], dtype=np.float32)
        return _lookAt(eye, self.target, up=(0, 1, 0))

    def _rebuildBuffers(self):
        for buffer in self._colorBuffers:
            buffer.destroy()
        self._colorBuffers = []

        if self._projectController is None:
            return
        mesh = self._projectController.project.mesh
        palette = self._projectController.project.canvas.palette

        allPositions = []
        for colorIndex, components in enumerate(mesh.meshes):
            triangles = [v for component in components for v in component]
            if not triangles:
                continue
            positions, normals = _trianglesToArrays(triangles)
            allPositions.append(positions)
            color = palette[colorIndex].color if colorIndex < len(palette) else BASE_COLOR
            self._colorBuffers.append(_ColorBuffer(color, positions, normals))

        if getattr(self, "_resetCamera", False) and allPositions:
            allPoints = np.concatenate(allPositions, axis=0)
            low, high = allPoints.min(axis=0), allPoints.max(axis=0)
            self.target = (low + high) / 2.0
            self.distance = max(float(np.linalg.norm(high - low)), 1.0) * 1.4
            self._resetCamera = False

    def resetView(self):
        self._resetCamera = True
        self._meshDirty = True
        self.update()

    # -- navigation ---------------------------------------------------

    def orbit(self, dx, dy):
        self.yaw -= dx * 0.01
        self.pitch = min(np.radians(89), max(np.radians(-89), self.pitch + dy * 0.01))
        self.update()

    def pan(self, dx, dy):
        eye = self.target + self.distance * np.array([
            np.cos(self.pitch) * np.sin(self.yaw),
            np.sin(self.pitch),
            np.cos(self.pitch) * np.cos(self.yaw),
        ])
        forward = (self.target - eye)
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, (0, 1, 0))
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        scale = self.distance * 0.0015
        self.target = self.target - right * dx * scale + up * dy * scale
        self.update()

    def travel(self, position, delta):
        """Move the camera by a screen-space delta at the given widget-
        local position - the general entry point mouseMoveEvent calls;
        orbit()/pan() are the named special cases of it."""
        self.orbit(delta[0], delta[1])

    def zoomBy(self, factor):
        self.distance = max(0.5, self.distance * factor)
        self.update()

    # -- Qt events -------------------------------------------------------

    def mousePressEvent(self, event):
        self._dragButton = event.button()
        self._lastPos = event.position()

    def mouseMoveEvent(self, event):
        if self._lastPos is None:
            return
        pos = event.position()
        dx, dy = pos.x() - self._lastPos.x(), pos.y() - self._lastPos.y()
        self._lastPos = pos
        if self._dragButton == Qt.LeftButton:
            self.travel((pos.x(), pos.y()), (dx, dy))
        elif self._dragButton == Qt.MiddleButton:
            self.pan(dx, dy)

    def mouseReleaseEvent(self, event):
        self._dragButton = None
        self._lastPos = None

    def wheelEvent(self, event):
        factor = 0.9 if event.angleDelta().y() > 0 else 1 / 0.9
        self.zoomBy(factor)
