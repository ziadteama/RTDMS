"""RTDMS "Brick Snap" enclosure: the Brick box with NO screws.

    python brick_snap.py     -> out/*.step (assembled position) + out/print/*.stl (print orientation)

Same outer box, same Pi 5 / camera positions as ../brick/. Only the way things are held changed:

  * Lid:    4 snap-fit arms hang from the lid and click into 4 windows in the side walls.
            Press the arm tips in through the windows to open it.
  * Pi 5:   4 locating pins on the standoffs go through the board's holes. 4 posts under the lid
            rest 0.2 mm above the board and hold it down. No screws, no clips on the board.
  * Camera: each IR-board clip slides in from the top into a slot at the outer end of the front wall
            and is clamped there (the same leaf spring as before, just held by plastic instead of a screw).

Frame: x = width (+x on your right when you look at the camera), y = depth (0 = front face,
+y towards the back), z = up (0 = underside).
"""
from pathlib import Path

import cadquery as cq
from cadquery import Vector

HERE = Path(__file__).parent
OUT = HERE / "out"

# ---------- box (unchanged from ../brick/brick.py) ----------
WALL = 2.4
FLOOR = 2.4
LID_T = 2.4
CLR = 0.3                # lid lip to wall clearance
INNER_W = 104.0
D = 85.0
H_SHELL = 42.6
W = INNER_W + 2 * WALL   # 108.8
R_V = 5.0

# ---------- Raspberry Pi 5 (unchanged) ----------
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
PCB_Z0, PCB_T = 5.2, 1.5
USBC_NX = 11.2
PI_FRONT_Y = 15.0


def pb(nx, ny):
    """native Pi coords -> box (x, y)"""
    return (44.0 - nx, PI_FRONT_Y + 56.0 - ny)


# ---------- camera (unchanged) ----------
CAM_ZC = 15.0
LENS_D = 15.4
COLLAR_OD, COLLAR_L = 17.0, 2.7
IR_DX, IR_D = 27.5, 21.4
LDR = [(-15.9, 7.0), (15.9, -7.1)]
LDR_D = 7.0
EYE_L, EYE_H, EYE_DEPTH = 82.0, 24.6, 0.4
CLAMP = 7.0              # inside of front face -> back of IR boards  (y = 9.4)
IR_BACK_Y = WALL + CLAMP

# ---------- NEW: Pi pins and hold-down posts ----------
PIN_D = 2.4              # Pi hole is 2.7: 0.15 mm each side
PIN_TOP = PCB_Z0 + PCB_T + 0.8                  # pin pokes 0.8 mm through the board
POST_D = 5.6
POST_GAP = 0.2           # post end is 0.2 mm above the board (no preload, no bending)
POST_Z0 = PCB_Z0 + PCB_T + POST_GAP
POST_HOLE_D, POST_HOLE_DEPTH = 3.4, 1.8         # receives the pin tip; loose on purpose
POST_HOLES = PI_HOLES    # drop two entries (e.g. the back ones) if the Active Cooler touches them

# ---------- NEW: lid snap arms ----------
HOOK_Y = (14.0, 71.0)    # arm centres along y (4 arms: 2 per long side)
ARM_W = 8.0
ARM_T_ROOT, ARM_T_TIP = 2.2, 1.6                # tapered: even stress along the arm
ARM_L = 16.5             # underside of the lid plate -> arm tip
HOOK_OUT = 1.0           # hook sticks out 1.0 mm past the arm face (0.7 mm past the wall: that is the bend)
HOOK_H = 2.5
LIP_X = INNER_W / 2 - CLR                       # 51.7: outer face of lid lip and arms
Z_RET = H_SHELL - (ARM_L - HOOK_H)              # 28.6: top of the hook = the retaining face
WIN_W = ARM_W + 1.6
WIN_Z0, WIN_Z1 = Z_RET - 4.0, Z_RET + 0.1       # window 4.1 mm tall, hook sits in its upper part
SLIT = 1.0               # gap in the lid lip on each side of an arm

# ---------- NEW: camera clip slot ----------
CLIP_T = 2.0
CLIP_H = 10.0
CLIP_X0, CLIP_X1 = 20.5, 48.0
PAD_D = 6.0
PRELOAD = 0.3
SLOT_X0, SLOT_X1 = 42.5, 48.3                   # slot the clip's outer end slides into
BLOCK_Y = IR_BACK_Y + 1.0                       # front face of the slot = 10.4
LIP_Y0 = BLOCK_Y + 0.4 + CLIP_T                 # clip is pushed back against this face = 12.8
LIP_T = 2.0
CLIP_Y0 = LIP_Y0 - CLIP_T                       # clip front face = 10.8
PAD_L = CLIP_Y0 - (IR_BACK_Y - PRELOAD)         # 1.7: pad tip is 0.3 mm past the IR-board back
SLOT_ZTOP = 22.5


def cyl(d, h, pnt, dirn):
    return cq.Workplane().add(cq.Solid.makeCylinder(d / 2, h, Vector(*pnt), Vector(*dirn)))


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane().box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def ybox(cx, y0, cz, w, depth, h, r=0.0):
    b = cq.Workplane().box(w, depth, h).translate((cx, y0 + depth / 2, cz))
    return b.edges("|Y").fillet(r) if r else b


def xslot(x0, cy, cz, length, depth, w):
    return cq.Workplane().box(depth, length, w).edges("|X").fillet(w / 2 - 0.05).translate((x0, cy, cz))


def stadium_y(cx, cz, length, height, y0, depth):
    r = height / 2
    s = ybox(cx, y0, cz, length - 2 * r, depth, height)
    for sx in (-1, 1):
        s = s.union(cyl(height, depth, (cx + sx * (length / 2 - r), y0, cz), (0, 1, 0)))
    return s


def mirror_x(w):
    return w.mirror("YZ")


# ------------------------------------------------------------------ shell
def clip_slot():
    """+x side: slot that holds the outer end of the camera clip (mirrored for -x)."""
    xs = SLOT_X0
    front = box(xs, W / 2 - WALL + 0.1, WALL - 0.01, BLOCK_Y, FLOOR - 0.01, SLOT_ZTOP)
    end = box(SLOT_X1, W / 2 - WALL + 0.1, WALL - 0.01, LIP_Y0 + LIP_T, FLOOR - 0.01, SLOT_ZTOP)
    lip = box(xs, W / 2 - WALL + 0.1, LIP_Y0, LIP_Y0 + LIP_T, FLOOR - 0.01, SLOT_ZTOP)
    stop = box(xs, SLOT_X1, BLOCK_Y - 0.01, LIP_Y0 + 0.01, FLOOR - 0.01, CAM_ZC - CLIP_H / 2)
    return front.union(end).union(lip).union(stop)


def shell():
    outer = (cq.Workplane().box(W, D, H_SHELL, centered=(True, False, False))
             .edges("|Z").fillet(R_V).faces("<Z").edges().fillet(1.5))
    inner = (cq.Workplane().box(INNER_W, D - 2 * WALL, H_SHELL, centered=(True, False, False))
             .edges("|Z").fillet(R_V - WALL).translate((0, WALL, FLOOR)))
    s = outer.cut(inner)

    s = s.union(cyl(COLLAR_OD, COLLAR_L, (0, WALL - 0.01, CAM_ZC), (0, 1, 0)))
    s = s.union(clip_slot()).union(mirror_x(clip_slot()))
    # Pi standoffs with locating pins (pin goes through the board's hole)
    for h in PI_HOLES:
        x, y = pb(*h)
        s = s.union(cyl(6.0, PCB_Z0 - FLOOR + 0.01, (x, y, FLOOR - 0.01), (0, 0, 1)))
        pin = (cq.Workplane().circle(PIN_D / 2).extrude(PIN_TOP - PCB_Z0 + 0.01)
               .faces(">Z").chamfer(0.5).translate((x, y, PCB_Z0 - 0.01)))
        s = s.union(pin)

    cuts = [
        stadium_y(0, CAM_ZC, EYE_L, EYE_H, -1, 1 + EYE_DEPTH),
        cyl(LENS_D, WALL + COLLAR_L + 2, (0, -1, CAM_ZC), (0, 1, 0)),
    ]
    cuts += [cyl(IR_D, WALL + 2, (sx * IR_DX, -1, CAM_ZC), (0, 1, 0)) for sx in (-1, 1)]
    cuts += [cyl(LDR_D, WALL + 2, (x, -1, CAM_ZC + z), (0, 1, 0)) for x, z in LDR]
    # back: USB-C + vents
    cuts.append(ybox(pb(USBC_NX, 0)[0], D - WALL - 1, PCB_Z0 + PCB_T + 1.65, 14.0, WALL + 2, 8.5, 3.0))
    cuts += [ybox(0, D - WALL - 1, z, 44.0, WALL + 2, 3.0, 1.45) for z in (13.0, 18.0, 23.0)]
    # sides: vents
    for sx in (-1, 1):
        cuts += [xslot(sx * (W / 2 - WALL / 2), 44.0, z, 36.0, WALL + 2, 3.0) for z in (11.0, 16.0, 21.0)]
    # sides: windows for the lid hooks (through the wall: you can push the hook in from outside)
    for sx in (-1, 1):
        for hy in HOOK_Y:
            x0, x1 = sorted((sx * (INNER_W / 2 - 2.0), sx * (W / 2 + 1.0)))
            cuts.append(box(x0, x1, hy - WIN_W / 2, hy + WIN_W / 2, WIN_Z0, WIN_Z1))
    for c in cuts:
        s = s.cut(c)
    return s


# ------------------------------------------------------------------ lid
def arm():
    """One snap arm on the +x side, hanging down from the lid plate (assembled position)."""
    xo = LIP_X
    z0, zt = H_SHELL + 0.5, H_SHELL - ARM_L
    prof = [(xo - ARM_T_ROOT, z0), (xo, z0), (xo, Z_RET), (xo + HOOK_OUT, Z_RET),
            (xo + HOOK_OUT, Z_RET - (HOOK_H - HOOK_OUT)), (xo, zt), (xo - ARM_T_TIP, zt)]
    a = cq.Workplane("XZ").polyline(prof).close().extrude(ARM_W / 2, both=True)   # centred on y = 0
    return a


def lid():
    plate = (cq.Workplane().box(W, D, LID_T, centered=(True, False, False))
             .edges("|Z").fillet(R_V).faces(">Z").edges().fillet(1.2).translate((0, 0, H_SHELL)))
    lw, ld = INNER_W - 2 * CLR, D - 2 * WALL - 2 * CLR
    lip = (cq.Workplane().box(lw, ld, 1.5, centered=(True, False, False)).edges("|Z").fillet(R_V - WALL - CLR)   # follows the shell's rounded inside corners
           .cut(cq.Workplane().box(lw - 3.2, ld - 3.2, 1.5, centered=(True, False, False)).edges("|Z").fillet(0.7).translate((0, 1.6, 0)))
           .translate((0, WALL + CLR, H_SHELL - 1.5)))
    # open the lip around each arm so the arm can flex on its own
    for sx in (-1, 1):
        for hy in HOOK_Y:
            x0, x1 = sorted((sx * (LIP_X - 3.0), sx * (LIP_X + 0.5)))
            lip = lip.cut(box(x0, x1, hy - ARM_W / 2 - SLIT, hy + ARM_W / 2 + SLIT, H_SHELL - 2.0, H_SHELL))
    l = plate.union(lip)
    for hy in HOOK_Y:
        a = arm().translate((0, hy, 0))
        l = l.union(a).union(mirror_x(a))
    for i in range(9):   # fan grille over the Active Cooler
        y = 23.0 + i * 5.5
        l = l.cut(cq.Workplane().box(72.0, 3.0, LID_T + 4).edges("|Z").fillet(1.45).translate((0, y, H_SHELL)))
    # hold-down posts: a solid patch where a post meets the grille, then the post itself
    for h in POST_HOLES:
        x, y = pb(*h)
        l = l.union(cyl(POST_D + 4.0, LID_T, (x, y, H_SHELL), (0, 0, 1)))
        l = l.union(cyl(POST_D, H_SHELL + 0.5 - POST_Z0, (x, y, POST_Z0), (0, 0, 1)))
        l = l.cut(cyl(POST_HOLE_D, POST_HOLE_DEPTH, (x, y, POST_Z0 - 0.01), (0, 0, 1)))
    return l


# ------------------------------------------------------------------ camera clip
def camera_clip():
    """Print two (the file holds one). Right side as printed; left side: the same clip turned upside down."""
    c = ybox((CLIP_X0 + CLIP_X1) / 2, CLIP_Y0, CAM_ZC, CLIP_X1 - CLIP_X0, CLIP_T, CLIP_H, 0)
    c = c.edges("|Y").fillet(2.0)
    c = c.union(cyl(PAD_D, PAD_L + 0.01, (IR_DX, CLIP_Y0 + 0.01, CAM_ZC), (0, -1, 0)))
    return c


# ------------------------------------------------------------------ export
def print_orient(name, p):
    """Rotate/move a part into the orientation it is printed in, sitting on z = 0."""
    if name == "lid":      # outer face down, posts and arms up
        p = p.rotate((0, 0, 0), (1, 0, 0), 180)
    elif name == "camera_clip":   # back face (y = LIP_Y0) down, pad up
        p = p.rotate((0, 0, 0), (1, 0, 0), -90)
    bb = p.val().BoundingBox()
    return p.translate((-(bb.xmin + bb.xmax) / 2, -(bb.ymin + bb.ymax) / 2, -bb.zmin))


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "print").mkdir(exist_ok=True)
    (OUT / "assembled").mkdir(exist_ok=True)
    parts = {"shell": shell(), "lid": lid(), "camera_clip": camera_clip()}
    for name, p in parts.items():
        cq.exporters.export(p, str(OUT / f"{name}.step"))
        cq.exporters.export(p, str(OUT / "assembled" / f"{name}.stl"), tolerance=0.05, angularTolerance=0.2)   # for render.scad
        q = print_orient(name, p)
        cq.exporters.export(q, str(OUT / "print" / f"{name}.stl"), tolerance=0.03, angularTolerance=0.15)
        bb = q.val().BoundingBox()
        print(f"{name:12s} print size {bb.xlen:6.1f} x {bb.ylen:6.1f} x {bb.zlen:6.1f} mm  "
              f"solids={len(p.solids().vals())} valid={p.val().isValid()}")
    print(f"assembled outer size: {W:.1f} x {D:.1f} x {H_SHELL + LID_T:.1f} mm (W x D x H)")


if __name__ == "__main__":
    main()
