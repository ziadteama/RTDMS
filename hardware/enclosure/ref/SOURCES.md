# Reference models

Used for dimensions and fit checks only. The printable enclosure is our own design.

## openpicase/
- Source: https://github.com/marceloeatworld/OpenPiCase, commit `7df3ef46a04c869ec1b20068f85155c5487c69f2`
- License: MIT (see `README.md`)
- Pi 5 case + Camera Module 3 pod. `files/RPi Camera Case.step` is a full assembly (665 solids)
  that includes a detailed **Raspberry Pi 5 board model**, solids 1–591. It holds no Active Cooler, despite the README.
- Measured from it: board 85 × 56 × 1.5 mm. Above the board's top face, the USB stacks stand 16.2 mm and Ethernet 13.5 mm.
  The 17 mm posts + plate in the assembly are the optional AI HAT (we have none).

## night-vision-camera-mount/
- Source: "Raspberry Pi Night Vision Camera Mount (incl. Infrared spots)" by Bravehartk2, Printables
  (see the included PDF). Uploaded to this project by the team.
- Mount for the same camera type we use (OV5647 night-vision module with two IR spot boards).
- Measured from `head_front.stl`: Ø15 mm lens hole, two Ø21 mm IR openings centred ±26.4 mm from
  the lens, two light-sensor notches. The head is 80 × 25 mm overall.
