"""RTDMS "Brick" enclosure: Raspberry Pi 5 (+ Active Cooler) lying flat, IR camera on the front wall.

    python brick.py              -> out/*.step + out/*.stl   (shell, lid, camera_clip)
    python brick.py --pi-model   -> also ref_derived/pi5_board.stl (needed by render.scad)

Frame: x = width (+x is on your right when you look at the camera), y = depth (0 = front face,
+y towards the back), z = up (0 = underside).

Where the numbers come from (see ../ref/SOURCES.md):
  * Pi 5 heights, board position: OpenPiCase STEP assembly (USB stack 16.2 mm over the board, board
    underside 5.2 mm above the case bottom).
  * Camera openings and clamp depth: night-vision camera mount (head_front / head_back STLs):
    lens Ø15, IR spots Ø21 at ±27.5 mm, light-sensor notches Ø7, 7.0 mm from the inside of the
    front face to the back of the IR boards.
The camera is clamped by two clips pressing the IR boards against the front wall (no screws into
the camera board, so its hole spacing doesn't matter). If it rattles, add 1 mm foam tape to the pads.
"""
from pathlib import Path

import cadquery as cq
from cadquery import Vector

OUT = Path(__file__).parent / "out"

# ---------- box ----------
WALL = 2.4
FLOOR = 2.4
LID_T = 2.4
CLR = 0.3
INNER_W = 104.0          # Pi model spans x -44.9..44.2 (USB stack overhangs 0.9 mm more than spec)
D = 75.0                 # depth, front to back
H_SHELL = 27.6           # shell height = lid's inner face (USB stack top is 22.9)
W = INNER_W + 2 * WALL   # 108.8
R_V = 5.0                # vertical corner radius

# ---------- Raspberry Pi 5 ----------
# native coords: component side up, origin at the USB-C-end / HDMI-edge corner, 85 x 56 mm.
# Placed rotated 180 deg: USB-C/HDMI edge at the back, USB/Ethernet end on the left (-x).
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
PCB_Z0, PCB_T = 5.2, 1.5
USBC_NX = 11.2
SD_NY = 28.0
PI_FRONT_Y = 15.0        # GPIO edge


def pb(nx, ny):
    """native Pi coords -> box (x, y)"""
    return (44.0 - nx, PI_FRONT_Y + 56.0 - ny)


# ---------- camera (front-view coords: x right, z up, relative to the lens centre) ----------
CAM_ZC = 15.0
LENS_D = 15.4
COLLAR_OD, COLLAR_L = 17.0, 2.7
IR_DX, IR_D = 27.5, 21.4
LDR = [(-15.9, 7.0), (15.9, -7.1)]
LDR_D = 7.0
EYE_L, EYE_H, EYE_DEPTH = 82.0, 24.6, 0.4   # stadium recess around the camera (face stays 2.0 mm)
CLAMP = 7.0              # inside of front face -> back of IR boards
PAD_D, PAD_L = 6.0, 1.0
CLIP_T, CLIP_H = 2.5, 12.0
CLIP_X0, CLIP_X1, CLIP_SCREW_X = 20.5, 48.0, 44.0
BAR_Y0 = WALL + CLAMP + PAD_L               # clip's front face (10.4)

POSTS = [(sx * 49.0, y) for sx in (-1, 1) for y in (20.0, D - WALL - 3.0)]   # sink 0.25 mm into the walls (no tangent edges)


def cyl(d, h, pnt, dirn):
    return cq.Workplane().add(cq.Solid.makeCylinder(d / 2, h, Vector(*pnt), Vector(*dirn)))


def ybox(cx, y0, cz, w, depth, h, r=0.0):
    """box spanning y0..y0+depth, centred on (cx, cz); r rounds the edges parallel to y"""
    b = cq.Workplane().box(w, depth, h).translate((cx, y0 + depth / 2, cz))
    return b.edges("|Y").fillet(r) if r else b


def xslot(x0, cy, cz, length, depth, w):
    """slot through a side wall (runs along y)"""
    return cq.Workplane().box(depth, length, w).edges("|X").fillet(w / 2 - 0.05).translate((x0, cy, cz))


def stadium_y(cx, cz, length, height, y0, depth):
    r = height / 2
    s = ybox(cx, y0, cz, length - 2 * r, depth, height)
    for sx in (-1, 1):
        s = s.union(cyl(height, depth, (cx + sx * (length / 2 - r), y0, cz), (0, 1, 0)))
    return s


def shell():
    outer = (cq.Workplane().box(W, D, H_SHELL, centered=(True, False, False))
             .edges("|Z").fillet(R_V).faces("<Z").edges().fillet(1.5))
    inner = (cq.Workplane().box(INNER_W, D - 2 * WALL, H_SHELL, centered=(True, False, False))
             .edges("|Z").fillet(R_V - WALL).translate((0, WALL, FLOOR)))
    s = outer.cut(inner)

    # front: lens collar, clip bosses
    s = s.union(cyl(COLLAR_OD, COLLAR_L, (0, WALL - 0.01, CAM_ZC), (0, 1, 0)))
    for sx in (-1, 1):
        s = s.union(cyl(7.0, BAR_Y0 - WALL + 0.01, (sx * CLIP_SCREW_X, WALL - 0.01, CAM_ZC), (0, 1, 0)))
    # Pi standoffs and lid posts
    for h in PI_HOLES:
        x, y = pb(*h)
        s = s.union(cyl(6.0, PCB_Z0 - FLOOR + 0.01, (x, y, FLOOR - 0.01), (0, 0, 1)))
    for x, y in POSTS:
        s = s.union(cyl(6.5, H_SHELL - FLOOR, (x, y, FLOOR - 0.01), (0, 0, 1)))

    cuts = [
        stadium_y(0, CAM_ZC, EYE_L, EYE_H, -1, 1 + EYE_DEPTH),                 # eye recess
        cyl(LENS_D, WALL + COLLAR_L + 2, (0, -1, CAM_ZC), (0, 1, 0)),           # lens
    ]
    cuts += [cyl(IR_D, WALL + 2, (sx * IR_DX, -1, CAM_ZC), (0, 1, 0)) for sx in (-1, 1)]
    cuts += [cyl(LDR_D, WALL + 2, (x, -1, CAM_ZC + z), (0, 1, 0)) for x, z in LDR]
    cuts += [cyl(2.1, 7.0, (sx * CLIP_SCREW_X, BAR_Y0 + 0.01, CAM_ZC), (0, -1, 0)) for sx in (-1, 1)]
    cuts += [cyl(2.1, 4.5, (*pb(*h), PCB_Z0 + 0.01), (0, 0, -1)) for h in PI_HOLES]
    cuts += [cyl(2.5, 10.0, (x, y, H_SHELL + 0.01), (0, 0, -1)) for x, y in POSTS]
    # back: USB-C (fits an overmoulded plug) + vents
    cuts.append(ybox(pb(USBC_NX, 0)[0], D - WALL - 1, PCB_Z0 + PCB_T + 1.65, 14.0, WALL + 2, 8.5, 3.0))
    cuts += [ybox(0, D - WALL - 1, z, 44.0, WALL + 2, 3.0, 1.45) for z in (13.0, 18.0, 23.0)]
    # sides: vents; right side: microSD access under the board
    for sx in (-1, 1):
        cuts += [xslot(sx * (W / 2 - WALL / 2), 44.0, z, 36.0, WALL + 2, 3.0) for z in (11.0, 16.0, 21.0)]
    sd_y = pb(0, SD_NY)[1]
    cuts.append(cq.Workplane().box(WALL + 2, 14.0, 3.4).translate((W / 2 - WALL / 2, sd_y, 4.7)))
    for c in cuts:
        s = s.cut(c)
    return s


def lid():
    plate = (cq.Workplane().box(W, D, LID_T, centered=(True, False, False))
             .edges("|Z").fillet(R_V).faces(">Z").edges().fillet(1.2).translate((0, 0, H_SHELL)))
    lw, ld = INNER_W - 2 * CLR, D - 2 * WALL - 2 * CLR
    lip = (cq.Workplane().box(lw, ld, 1.5, centered=(True, False, False))
           .cut(cq.Workplane().box(lw - 3.2, ld - 3.2, 1.5, centered=(True, False, False)).translate((0, 1.6, 0)))
           .translate((0, WALL + CLR, H_SHELL - 1.5)))
    l = plate.union(lip)
    for x, y in POSTS:
        l = l.cut(cyl(6.5 + 2 * CLR, 1.6, (x, y, H_SHELL - 1.6), (0, 0, 1)))
        l = l.cut(cyl(3.4, LID_T + 2, (x, y, H_SHELL - 1), (0, 0, 1)))
        l = l.cut(cq.Workplane().add(cq.Solid.makeCone(1.7, 3.3, 1.6, Vector(x, y, H_SHELL + LID_T - 1.6 + 0.001))))
    for i in range(9):   # fan grille over the Active Cooler
        y = 23.0 + i * 5.5
        l = l.cut(cq.Workplane().box(72.0, 3.0, LID_T + 4).edges("|Z").fillet(1.45).translate((0, y, H_SHELL)))
    return l


def camera_clip():
    """Print two. The same part fits both sides (rotate 180 deg about the front-back axis)."""
    c = ybox((CLIP_X0 + CLIP_X1) / 2, BAR_Y0, CAM_ZC, CLIP_X1 - CLIP_X0, CLIP_T, CLIP_H, 0)
    c = c.edges("|Y").fillet(2.0)
    c = c.union(cyl(PAD_D, PAD_L + 0.01, (IR_DX, BAR_Y0 + 0.01, CAM_ZC), (0, -1, 0)))
    c = c.cut(cyl(2.8, CLIP_T + 2, (CLIP_SCREW_X, BAR_Y0 - 1, CAM_ZC), (0, 1, 0)))
    c = c.cut(cyl(5.4, 1.2, (CLIP_SCREW_X, BAR_Y0 + CLIP_T - 1.2, CAM_ZC), (0, 1, 0)))
    return c


def export_pi_model():
    """Pi 5 board model for render.scad, cut out of the OpenPiCase STEP (solids 1-591)."""
    step = cq.importers.importStep(str(Path(__file__).parent / "../ref/openpicase/files/RPi Camera Case.step"))
    pi = cq.Compound.makeCompound(step.solids().vals()[1:592])
    dst = Path(__file__).parent / "ref_derived" / "pi5_board.stl"
    dst.parent.mkdir(exist_ok=True)
    cq.exporters.export(cq.Workplane().add(pi), str(dst), tolerance=0.1)
    print(f"wrote {dst}")


def main():
    import sys
    if "--pi-model" in sys.argv:
        export_pi_model()
    OUT.mkdir(exist_ok=True)
    parts = {"shell": shell(), "lid": lid(), "camera_clip": camera_clip()}
    for name, p in parts.items():
        cq.exporters.export(p, str(OUT / f"{name}.step"))
        cq.exporters.export(p, str(OUT / f"{name}.stl"), tolerance=0.05, angularTolerance=0.2)
        bb = p.val().BoundingBox()
        print(f"{name:12s} {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f} mm  valid={p.val().isValid()}")
    print(f"assembled outer size: {W:.1f} x {D:.1f} x {H_SHELL + LID_T:.1f} mm (W x D x H)")


if __name__ == "__main__":
    main()
