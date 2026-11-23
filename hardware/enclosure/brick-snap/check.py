"""Geometry checks for the snap enclosure. Run: python check.py   (loads the real Pi 5 board model: ~1 min)

1. every part is one valid solid
2. assembled: nothing that should be separate overlaps (shell / lid / clips / Pi board / camera)
3. printability: how much surface hangs out over empty space (> 45 deg) in the print orientation
4. snap-fit numbers: bend, strain, engagement
"""
import math
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh

import brick_snap as b

HERE = Path(__file__).parent


def vol(shape_a, shape_b):
    try:
        return shape_a.intersect(shape_b).val().Volume()
    except Exception:
        return 0.0


def pi_board():
    step = cq.importers.importStep(str(HERE / "../ref/openpicase/files/RPi Camera Case.step"))
    pi = cq.Compound.makeCompound(step.solids().vals()[1:592])
    # STEP frame -> box frame, same transform as brick/render.scad: rotate 90 about z, move (52.5, 43, 0).
    # The STEP board's underside is at z = 5.0, but the standoffs are 5.2 tall, so the real board sits
    # 0.2 mm higher than the model: lift it, or every check above the board is 0.2 mm optimistic.
    return cq.Workplane().add(pi).rotate((0, 0, 0), (0, 0, 1), 90).translate((52.5, 43, 0.2))


def camera_standin():
    """Camera board + 2 IR boards + domes, from brick/render.scad (rough stand-in, not measured)."""
    c = cq.Workplane().box(25, 1.6, 24, centered=False).translate((-12.5, 8.5, b.CAM_ZC - 12))
    for s in (-1, 1):
        c = c.union(b.cyl(24, 1.6, (s * 27.5, 7.8, b.CAM_ZC), (0, 1, 0)))
        c = c.union(b.cyl(18, 7.2, (s * 27.5, 0.6, b.CAM_ZC), (0, 1, 0)))
    return c


def main():
    shell, lid, clip = b.shell(), b.lid(), b.camera_clip()
    clip_l = clip.rotate((0, 0, 0), (0, 1, 0), 180).translate((0, 0, 2 * b.CAM_ZC))
    print("1. solids")
    for n, p in (("shell", shell), ("lid", lid), ("clip", clip)):
        print(f"   {n:6s} solids={len(p.solids().vals())} valid={p.val().isValid()} volume={p.val().Volume()/1000:.1f} cm3")

    print("2. assembled overlaps (mm3, want 0 unless noted)")
    pi = pi_board()
    cam = camera_standin()
    rows = [("shell  x lid", shell, lid), ("shell  x clip L", shell, clip_l),
            ("lid    x clip R", lid, clip), ("lid    x Pi board", lid, pi), ("shell  x Pi board", shell, pi),
            ("clip   x Pi board", clip, pi), ("clip R x camera (pad preload, want ~0.3 mm deep)", clip, cam),
            ("shell  x clip R crush rib (want small: 0.1 mm crush)", shell, clip),
            ("shell  x camera", shell, cam)]
    for n, a, c in rows:
        print(f"   {n:52s} {vol(a, c):8.2f}")

    print("3. overhangs in print orientation (faces tilted > 45 deg from vertical and facing down, not on the bed)")
    for name in ("shell", "lid", "camera_clip"):
        m = trimesh.load(str(b.OUT / "print" / f"{name}.stl"))
        n = m.face_normals
        area = m.area_faces
        c = m.triangles_center
        bad = (n[:, 2] < -0.707) & (c[:, 2] > 0.05)
        print(f"   {name:12s} overhang area {area[bad].sum():7.1f} mm2 of {m.area:8.1f}")
        # cluster by height
        zs = np.round(c[bad, 2], 0)
        for z in sorted(set(zs)):
            sel = zs == z
            a = area[bad][sel].sum()
            if a > 8:
                xy = c[bad][sel]
                print(f"      z~{z:5.1f}: {a:6.1f} mm2  x {xy[:,0].min():.0f}..{xy[:,0].max():.0f}  y {xy[:,1].min():.0f}..{xy[:,1].max():.0f}")

    print("4. snap-fit")
    wall_in = b.INNER_W / 2
    bend = b.LIP_X + b.HOOK_OUT - wall_in
    L = b.ARM_L - b.HOOK_H / 2
    t = (b.ARM_T_ROOT + b.ARM_T_TIP) / 2
    eps = 1.5 * t * bend / L**2
    print(f"   hook bend while closing   {bend:.2f} mm")
    print(f"   arm length / mean thick   {L:.1f} / {t:.2f} mm")
    print(f"   strain at the root        {eps*100:.2f} %  (PLA across layers ~1.5 % limit, PETG more)")
    print(f"   retaining engagement      {bend:.2f} mm   ({b.WIN_Z1 - b.Z_RET:.1f} mm slack above the hook)")
    print(f"   wall above window         {b.H_SHELL - b.WIN_Z1:.1f} mm")
    # camera clip: can it rock in its slot? (the bug in the first version: 0.4 mm slack = pad backs off 1.1 mm)
    bb = clip.val().BoundingBox()
    rib_front = clip.intersect(b.box(b.RIB_X - 1, b.RIB_X + 1, 0, b.CLIP_Y0, 0, 40)).val().BoundingBox().ymin
    print(f"   clip: pad tip y {bb.ymin:.2f} (IR board back {b.IR_BACK_Y:.1f}, preload {b.IR_BACK_Y - bb.ymin:.2f} mm)")
    print(f"   clip: crush rib front y {rib_front:.2f} vs slot front face {b.BLOCK_Y:.2f} -> "
          f"{b.BLOCK_Y - rib_front:.2f} mm crush; clip back on the lip at y {b.LIP_Y0:.2f}: no rocking room")
    print(f"   lid post end above board  {b.POST_Z0 - (b.PCB_Z0 + b.PCB_T):.2f} mm; pin tip inside post hole by "
          f"{b.POST_Z0 + b.POST_HOLE_DEPTH - b.PIN_TOP:.2f} mm")


if __name__ == "__main__":
    main()
