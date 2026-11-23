"""Cross-section drawings of the three holding points (assembled position). python sections.py -> renders/sections.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib.patches import Polygon

import brick_snap as b

M = {n: trimesh.load(str(b.OUT / "assembled" / f"{n}.stl")) for n in ("shell", "lid", "camera_clip")}
COL = {"shell": "#4b5563", "lid": "#3b82f6", "camera_clip": "#f59e0b"}


def cut(ax, origin, normal, axes, parts):
    """slice every part with a plane; draw the filled outline. axes = (i, j) world axes shown as (horizontal, vertical)"""
    for n in parts:
        mesh = M[n]
        for flip in (False, True) if n == "camera_clip_l" else (False,):
            pass
        sec = mesh.section(plane_origin=origin, plane_normal=normal)
        if sec is None:
            continue
        for poly in sec.discrete:
            pts = poly[:, list(axes)]
            ax.add_patch(Polygon(pts, closed=True, fc=COL[n], ec="black", lw=0.5, alpha=0.9))
    ax.set_aspect("equal"); ax.autoscale_view(); ax.grid(alpha=0.2)


fig, axs = plt.subplots(2, 2, figsize=(15, 11))

# 1. lid snap arm, section through an arm (y = 14), right wall
ax = axs[0, 0]
cut(ax, (0, 14, 0), (0, 1, 0), (0, 2), ("shell", "lid"))
ax.set_xlim(44, 56); ax.set_ylim(20, 47)
ax.set_title("1. Lid snap arm in its window  (section y = 14, right wall)\nhook is 0.7 mm into the window, its flat top face is under the wall above the window")
ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)")
ax.annotate("lid plate", (53.5, 43.8), fontsize=9)
ax.annotate("arm (tapered 2.2 -> 1.6)", (47.0, 35), fontsize=9)
ax.annotate("hook", (52.9, 27.3), fontsize=9)
ax.annotate("window (open)", (53.6, 25.0), fontsize=9)

# 2. Pi pin + lid post (section through the hole at y = 18.5, x = 40.5)
ax = axs[0, 1]
cut(ax, (0, b.pb(*b.PI_HOLES[2])[1], 0), (0, 1, 0), (0, 2), ("shell", "lid"))
x0 = b.pb(*b.PI_HOLES[2])[0]
ax.add_patch(Polygon([(x0 - 6, b.PCB_Z0), (x0 + 6, b.PCB_Z0), (x0 + 6, b.PCB_Z0 + b.PCB_T), (x0 - 6, b.PCB_Z0 + b.PCB_T)],
                     closed=True, fc="#22c55e", ec="black", lw=0.5, alpha=0.9))
ax.set_xlim(x0 - 7, x0 + 7); ax.set_ylim(0, 15)
ax.set_title("2. Pi 5 on its pin, post above  (section through a mounting hole)\ngreen = the Pi board; post stops 0.2 mm above it")
ax.set_xlabel("x (mm)"); ax.set_ylabel("z (mm)")

# 3. camera clip in its slot (section z = 15, plan view), right front corner
ax = axs[1, 0]
cut(ax, (0, 0, 15), (0, 0, 1), (0, 1), ("shell", "camera_clip"))
ax.add_patch(Polygon([(18, 7.8), (36, 7.8), (36, 9.4), (18, 9.4)], closed=True, fc="#9ca3af", ec="black", lw=0.5, alpha=0.9))
ax.set_xlim(14, 54); ax.set_ylim(0, 20)
ax.set_title("3. Camera clip in its slot  (plan, section z = 15, right front corner)\ngrey = IR board; pad touches it; the clip's outer end is held between the front block and the back lip")
ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm, front wall at 0)")

# 4. whole box side section at x = 50.8 (through arms + windows), to see where the 4 arms sit
ax = axs[1, 1]
cut(ax, (50.8, 0, 0), (1, 0, 0), (1, 2), ("shell", "lid"))
ax.set_xlim(-2, 87); ax.set_ylim(-2, 48)
ax.set_title("4. Side view section at x = 50.8: 2 arms per side (y = 14 and 71), windows in the wall")
ax.set_xlabel("y (mm, front = 0)"); ax.set_ylabel("z (mm)")

plt.tight_layout()
plt.savefig(str(b.HERE / "renders" / "sections.png"), dpi=110)
print("ok")
