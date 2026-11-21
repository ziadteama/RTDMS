#!/usr/bin/env bash
# Re-export STLs + preview PNGs after editing parameters in rtdms_enclosure.scad.
# Needs OpenSCAD (and xvfb-run on a headless Linux box for the PNGs).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p stl renders
for p in shell lid camera_plate; do openscad -q -o "stl/$p.stl" -D "part=\"$p\"" rtdms_enclosure.scad; done
X=""; command -v xvfb-run >/dev/null && X="xvfb-run -a"
r() { $X openscad -q -o "renders/$1.png" --imgsize=1400,1000 --colorscheme=Tomorrow --projection="$4" --camera="$3" -D "part=\"$2\"" rtdms_enclosure.scad; }
r front    assembly -60,180,90,50,-20,35    p
r back     assembly 200,-220,110,50,-20,35  p
r exploded exploded -150,170,110,50,-20,35  p
r section  section  -300,-20,35,50,-20,35   o
openscad -o /dev/null --export-format stl rtdms_enclosure.scad 2>&1 | grep ECHO || true
