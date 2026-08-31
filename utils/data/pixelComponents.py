import trimesh

from .pixelPlan import Face
from .vector import Vector3


# Axes: X = pixel column, Z = pixel row, Y = height (the vertical/print
# axis - Y-up). Every layer of height is exactly 1 world unit.
TUBE_MARGIN = 0.12           # how far the tube is inset from the pixel's unit-square edge
WALL_THICKNESS = 0.1         # shell thickness when a Tube is hollow
BULGE_SIZE = 0.10            # how far a cap flares out past the grid edge on a clear side


def _box(x0, x1, y0, y1, z0, z1):
    """An axis-aligned box mesh spanning the given bounds."""
    box = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    box.apply_translation(((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0))
    return box


class Pixel:
    """The solid for one occupied grid cell, in plain boxes: a Cap (the
    top unit-height layer, flared outward on any clear/bulged side) and,
    if taller than one layer, a Tube beneath it (inset on bulged sides -
    that clearance is what lets two diagonal same-color neighbors' caps
    overlap into the shared corner without their tubes colliding).

    No hand-fitted seams between pieces - see componentTriangles, which
    merges every pixel's boxes in a component with a real boolean union,
    so nothing here has to line up by construction the way independently
    triangulated Cap/Tube/Collar pieces used to."""

    def __init__(self, plan, hollow: bool):
        self.plan = plan

        x0, z0 = float(plan.x), float(plan.y)
        x1, z1 = x0 + 1.0, z0 + 1.0
        capX0 = x0 - (BULGE_SIZE if Face.WEST in plan.bulged else 0.0)
        capX1 = x1 + (BULGE_SIZE if Face.EAST in plan.bulged else 0.0)
        capZ0 = z0 - (BULGE_SIZE if Face.NORTH in plan.bulged else 0.0)
        capZ1 = z1 + (BULGE_SIZE if Face.SOUTH in plan.bulged else 0.0)
        capY0, capY1 = plan.height - 1.0, float(plan.height)

        self.solids = [_box(capX0, capX1, capY0, capY1, capZ0, capZ1)]
        self.cavities = []

        if capY0 > 0:
            m = TUBE_MARGIN
            # Fused and plain-wall sides need no clearance from their
            # neighbor: the tube sits flush with the grid boundary there
            # instead of inset, so the two tubes' solids actually meet
            # (fused) or touch (plain wall) rather than each standing
            # apart with a gap between them - only bulged sides (a clear
            # side, or a height mismatch) stay inset.
            flush = plan.flushTubeSides
            tubeX0 = x0 if Face.WEST in flush else x0 + m
            tubeX1 = x1 if Face.EAST in flush else x1 - m
            tubeZ0 = z0 if Face.NORTH in flush else z0 + m
            tubeZ1 = z1 if Face.SOUTH in flush else z1 - m
            self.solids.append(_box(tubeX0, tubeX1, 0.0, capY0, tubeZ0, tubeZ1))

            if hollow:
                t = WALL_THICKNESS
                cavX0, cavX1 = tubeX0 + t, tubeX1 - t
                cavZ0, cavZ1 = tubeZ0 + t, tubeZ1 - t
                if cavX1 > cavX0 and cavZ1 > cavZ0:
                    # Punches all the way through the tube's own floor (a
                    # hair past y=0) so the cavity comes out fully open on
                    # the print bed side rather than leaving a paper-thin
                    # floor sliver there - and stops exactly at the cap's
                    # own underside (capY0), which then seals it from above
                    # once everything is unioned together.
                    self.cavities.append(_box(cavX0, cavX1, -0.01, capY0, cavZ0, cavZ1))

    def warnings(self):
        return []


def componentTriangles(pixels):
    """The merged solid for one physically-connected group of pixels (see
    Mesh._calculateMesh), as a flat list of Vector3 - 3 per triangle, no
    shared indices, matching this codebase's usual triangle-soup
    convention. A real boolean union does the work a small forest of
    Notch/Inlet/Collar/seam-patch helpers used to: overlapping or exactly
    touching boxes just merge, with none of that needing to line up by
    hand."""
    solids = [box for pixel in pixels for box in pixel.solids]
    cavities = [box for pixel in pixels for box in pixel.cavities]

    merged = trimesh.boolean.union(solids) if len(solids) > 1 else solids[0]
    if cavities:
        cavity = trimesh.boolean.union(cavities) if len(cavities) > 1 else cavities[0]
        merged = trimesh.boolean.difference([merged, cavity])

    triangles = []
    for face in merged.faces:
        for vertexIndex in face:
            x, y, z = merged.vertices[vertexIndex]
            triangles.append(Vector3(float(x), float(y), float(z)))
    return triangles
