# Brick enclosure (concept B)

Pi 5 with the Active Cooler lying flat, the IR camera on the front wall. Openings are only for
**USB-C power** and **air**: fan grille on the lid, vents on the sides and back. (A microSD slot exists as an option, `SD_SLOT` in `brick.py`, off by default.)

**Outer size: 108.8 × 85 × 30 mm** (W × D × H). The back 10 mm is empty space behind the Pi, so the camera ribbon has room to turn into the Pi's connector (the Pi's camera ports are on the back edge, the camera is at the front).

| Front | Back | Inside |
|---|---|---|
| ![front](renders/front.png) | ![back](renders/back.png) | ![exploded](renders/exploded.png) |

## Files

- `brick.py`: the parametric CadQuery model. `python brick.py` writes `out/` (STEP + STL per part);
  `--pi-model` also extracts the Pi 5 board model that `render.scad` uses.
- `out/shell.*`, `out/lid.*`, `out/camera_clip.*`: STEP to edit in Fusion 360 / Onshape, STL to slice.
- `render.scad`: preview renders with the real Pi 5 model inside (OpenSCAD).

## Where the numbers come from

Measured from the reference models in `../ref/` (see `../ref/SOURCES.md`):

- **Pi 5:** board height and the 4 mounting holes match the OpenPiCase STEP model. The USB stack is
  16.2 mm tall and sticks out 0.9 mm further than the standard footprint says. The interior was
  widened for that. **A clash check against the real Pi model gives 0 mm³ overlap**, and the USB-C
  hole lines up with the model's port.
- **Camera:** taken from the night-vision camera mount made for this camera type: Ø15 lens, Ø21 IR
  openings at ±27.5 mm, the two light-sensor notches, and 7 mm from the inside of the front face to
  the back of the IR boards.

## How the camera is held

Like the original mount, the camera is **clamped, not screwed**. Two identical clips (print 2) press
on the back of the IR boards and push the camera against the front wall. Its screw-hole spacing
doesn't matter. The pads are deliberately 0.5 mm too long, so each clip **bends slightly and keeps
pressing like a spring.** Tighten until the camera doesn't move; you don't need to go all the way
if it gets stiff. If it still rattles, stick 1 mm foam tape on the pads.

The light-sensor notches assume the camera is upright, with the left IR board's sensor at the top
(as in your photo). If the image comes out upside down, rotate it in software.

## Print

- **PLA** (the team's choice). 0.2 mm layers, **5 walls, 30 % infill**: thicker walls resist creep
  around the screw holes.
- **Light colour (white or light grey) if you can.** Black PLA in sun heats up far more.
- **Heat rule:** PLA softens at about 55–60 °C. **Don't leave the unit in a parked car in the sun.**
  Take it out, or at least use a windshield sunshade. Driving with the AC on is fine.
- Don't overtighten the screws. PLA cracks instead of stretching.
- Shell: open side up, no supports. Lid: outer face down. Clips: flat.
- For a car-ready unit later, reprint the same files in PETG or ASA.

## Hardware

**One size for everything: M2.5 × 6 mm (11 screws).** Any "Raspberry Pi M2.5 screw kit" has them.
Any length from 5–8 mm works. Countersunk heads sit flush in the lid; pan heads work too.

| Qty | Use |
|---|---|
| 4 | Pi → standoffs |
| 2 | camera clips → front bosses |
| 5 | lid → posts (4 corners + 1 behind the Pi) |

The screws cut their own thread into the printed holes. No nuts or inserts needed.

## Assembly

1. Put the camera into the front from inside, lens and IR lights through their holes.
2. Screw the two clips on over the IR boards.
3. Screw the Pi onto the standoffs (USB-C at the back) and connect the camera ribbon. **The ribbon
   path is not verified**: it must go back over the board, turn in the 10 mm gap behind the Pi and
   enter the connector pointing forward. Check it on the test print before closing the lid.
4. Close the lid. Power goes in through the back.

## Not verified yet

- **Nothing printed yet.** The camera clamp depth comes from the mount model, not your board. The
  foam-tape note covers small differences.
- **The Active Cooler isn't in the reference model.** The lid sits 4.7 mm above the USB stack, the
  tallest part, so the cooler has room. The ribbon crosses part of the grille.
- **No mount yet**, since placement in the car comes later.
