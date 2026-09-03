import sys
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication
from utils import *


def main():
    # MeshElement's shaders are GLSL 150 (GL 3.2) - without requesting that
    # explicitly, the context Qt creates is whatever the platform/driver
    # defaults to, which isn't guaranteed to satisfy that version on every
    # vendor. Must be set before the QApplication is constructed (Qt only
    # reads the default format when it creates the first native GL context).
    glFormat = QSurfaceFormat()
    glFormat.setVersion(3, 2)
    glFormat.setProfile(QSurfaceFormat.CoreProfile)
    glFormat.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(glFormat)

    app = QApplication(sys.argv)

    appController = AppController()
    window = AppWindow(appController)
    window.setCanvasArea(CanvasArea(appController, theme=window.theme))
    window.setMeshElement(MeshElement(theme=window.theme))

    def openExportDialog():
        controller = appController.activeController
        if controller is None:
            return
        ExportDialog(controller, theme=window.theme, parent=window).exec()

    window.setExportHandler(openExportDialog)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    # Required for ProjectController's mesh-computation process pool: on
    # Windows and macOS, multiprocessing's "spawn" start method re-imports
    # this file as __main__ in every worker process. Without this guard,
    # each worker would re-run the whole app (a second QApplication, a
    # second window) instead of just importing computeMeshData.
    main()
