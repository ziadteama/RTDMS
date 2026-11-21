// RTDMS dash-cam enclosure — Raspberry Pi 5 (+ Active Cooler) + IR camera, opposite-side layout.
//
//   FRONT (faces the driver): camera plate with lens + 2 IR LED windows, 4 corner screws.
//   BACK  (lid):              Pi 5 hangs on the lid, cooler facing a slotted grille (fan intake).
//   TOP:                      USB-C power cut-out (+ vents).   SIDES / BOTTOM: exhaust vents.
//   BOTTOM:                   captive 1/4"-20 nut -> any tripod / suction / ball-head mount.
//
// Parts (set `part`, or use the Makefile):  "shell" | "lid" | "camera_plate" | "assembly"
// Units: mm.  Print in PETG or ASA — PLA softens in a parked car.
//
// !! Every value marked MEASURE was not available from a datasheet (no-name HBV camera).
// !! Measure with calipers and edit before printing. Print `camera_plate` first as a test fit.

part = "assembly";

/* ---------- print tolerances ---------- */
clr  = 0.3;    // general fit clearance
wall = 2.4;    // side walls (6 perimeters @ 0.4)

/* ---------- Raspberry Pi 5 (standard mechanical footprint) ---------- */
pi_w      = 85;     // board length (USB-C end -> USB/Eth end)
pi_h      = 56;     // board width  (HDMI/USB-C edge -> GPIO edge)
pi_pcb    = 1.6;
pi_hole   = [[3.5,3.5],[61.5,3.5],[3.5,52.5],[61.5,52.5]];  // native coords, component side up
pi_overhang = 3;    // USB/Ethernet jacks stick out past the board edge
pi_tallest  = 16.5; // USB stack height above PCB (taller than the Active Cooler)
usbc_x      = 11.2; // USB-C centre along the HDMI edge, from the USB-C end
sd_y        = 28;   // microSD centre along the USB-C-end edge (on PCB underside)

/* ---------- camera module  (MEASURE all of these) ---------- */
cam_pcb      = [32, 32];  // MEASURE camera board W x H
cam_pcb_t    = 1.6;
cam_holes    = [28, 28];  // MEASURE mounting-hole spacing (centre to centre) X, Y
cam_screw_d  = 2.0;       // M2 screws (pilot hole printed smaller)
lens_d       = 15;        // MEASURE widest diameter of lens barrel / front glass
lens_h       = 12;        // MEASURE lens tip height above camera board front face
cam_back     = 4.5;       // connector + ribbon bend behind camera board
led_d        = 15;        // MEASURE IR LED dome diameter
led_dx       = 27;        // MEASURE LED centre distance from lens centre (each side)
led_dy       = 0;         // MEASURE LED vertical offset from lens centre
ir_env       = [76, 36];  // MEASURE full camera+IR-board envelope W x H (must pass the aperture)
cam_offset_y = 0;         // shift camera up(+)/down(-) from box centre

/* ---------- options ---------- */
open_usb_eth = false;   // cut-out for USB-A + Ethernet (only power is needed by default)
sd_slot      = true;    // microSD access slot (also vents)
tripod_mount = true;    // captive 1/4"-20 nut in the bottom

/* ---------- derived layout ---------- */
// Box frame viewed from the BACK: x right, y up, z = 0 at the front face, +z towards the lid.
// The Pi is rotated 180 deg so the USB-C edge is at the top and the USB/Eth end on the left.
post_d   = 7;                              // lid screw posts in the 4 inner corners
side_gap = post_d - 0.5;                   // room beside the Pi for the posts
bot_gap  = 9;                              // room under the Pi for the tripod-nut boss
top_gap  = 2;                              // USB-C edge to top wall (plug + ribbon wrap)
W  = side_gap + pi_overhang + pi_w + side_gap;   // interior width
H  = bot_gap + pi_h + top_gap;                   // interior height
X0 = side_gap + pi_overhang;                     // Pi native x=85 edge sits here (box x)
Y0 = bot_gap;                                    // Pi GPIO edge (native y=56) sits here

plate_t   = 2;
front_t   = plate_t + 2.5;                 // front wall incl. plate recess
cam_z     = lens_h - 1;                    // camera board front face (lens tip 1 mm proud)
pi_z0     = cam_z + cam_pcb_t + cam_back;  // Pi PCB underside
pi_z1     = pi_z0 + pi_pcb;                // Pi component side
D         = pi_z1 + pi_tallest + 1.5;      // shell depth = lid inner face
lid_t     = 2.5;
R         = 4;                             // outer corner radius

OW = W + 2*wall;  OH = H + 2*wall;
cx = W/2;  cy = H/2 + cam_offset_y;        // camera centre (box frame)
plate = [ir_env[0] + 12, ir_env[1] + 12];  // camera plate outline
plate_screw = [plate[0]/2 - 3.5, plate[1]/2 - 3.5];

// native Pi coords -> box coords (180 deg rotation)
function pbx(px) = X0 + pi_w - px;         // native x -> box x
function pby(py) = Y0 + pi_h - py;         // native y -> box y

$fn = 48;
e = 0.01;

/* ---------- helpers ---------- */
module rrect(s, r, h) {               // rounded rectangle, origin at corner
    linear_extrude(h) offset(r) offset(-r) square(s);
}
module rrect_c(s, r, h) { translate([-s[0]/2, -s[1]/2, 0]) rrect(s, r, h); }
module slots(n, len, w, pitch) {      // n slots along y, each `len` long in x
    for (i = [0:n-1]) translate([0, i*pitch, 0]) hull() {
        translate([w/2, w/2]) circle(d=w); translate([len - w/2, w/2]) circle(d=w);
    }
}
module hex_pocket(af, h) { cylinder(d = af / cos(30), h = h, $fn = 6); }

/* ---------- SHELL (front + walls, open at the back) ---------- */
module shell() {
    difference() {
        union() {
            // outer body
            translate([-wall, -wall, 0]) rrect([OW, OH], R, D);
            // plate screw bosses behind the front wall
            for (sx = [-1, 1], sy = [-1, 1])
                translate([cx + sx*plate_screw[0], cy + sy*plate_screw[1], 0])
                    cylinder(d = 6, h = front_t + 4);
            // tripod nut boss
            if (tripod_mount) translate([cx - 9, 0, D/2 - 9]) cube([18, 8, 18]);
        }
        // hollow interior
        translate([0, 0, front_t]) cube([W, H, D]);
        // camera plate recess + aperture
        translate([cx, cy, -e]) rrect_c([plate[0] + 2*clr, plate[1] + 2*clr], 2, plate_t + e);
        translate([cx, cy, -e]) rrect_c([ir_env[0] + 2*clr, ir_env[1] + 2*clr], 2, D);
        // plate screw pilots (M2.5 self-tapping)
        for (sx = [-1, 1], sy = [-1, 1])
            translate([cx + sx*plate_screw[0], cy + sy*plate_screw[1], -e])
                cylinder(d = 2.1, h = front_t + 4 - 0.8);
        // lid screw pilots in corner posts (M3 self-tapping)
        for (p = post_xy()) translate([p[0], p[1], D - 12]) cylinder(d = 2.5, h = 12 + e);
        // USB-C power cut-out in the top wall (fits an overmoulded plug)
        translate([pbx(usbc_x), H - e, pi_z1 + 1.6])
            rotate([-90, 0, 0]) rrect_c([14, 8.5], 3, wall + 2*e);
        // vents: top (left of USB-C), sides, bottom (either side of nut boss)
        vent_z0 = front_t + 4;  vent_len = D - vent_z0 - 4;
        // side walls
        for (x = [-wall - e, W - e]) translate([x, 0, 0])
            translate([0, 12, vent_z0]) rotate([0, 90, 0]) translate([-vent_len, 0, 0])
                linear_extrude(wall + 2*e) slots(6, vent_len, 3, (H - 24) / 5.5);
        // top wall: slots away from USB-C
        translate([10, H - e, vent_z0]) rotate([-90, 0, 0]) translate([0, -vent_len, 0])
            linear_extrude(wall + 2*e) rotate(90) translate([0, -pbx(usbc_x) + 20, 0])
                slots(floor((pbx(usbc_x) - 20) / 6), vent_len, 3, 6);
        // bottom wall
        for (x0 = [8, cx + 12]) translate([x0, wall + e, vent_z0]) rotate([90, 0, 0])
            linear_extrude(wall + 2*e) rotate(90) translate([0, -(cx - 20 - 8), 0])
                slots(floor((cx - 20 - 8) / 6) + 1, vent_len, 3, 6);
        // tripod: 1/4"-20 nut pocket (opens upward) + bolt hole + 1 mm outside spot-face
        if (tripod_mount) translate([cx, 0, D/2]) rotate([-90, 0, 0]) {
            translate([0, 0, 0]) rotate([0, 0, 30]) hex_pocket(11.11 + 0.25, 8 + e);
            translate([0, 0, -wall - e]) cylinder(d = 6.8, h = wall + 2*e);
            translate([0, 0, -wall - e]) cylinder(d = 16, h = 1 + e);
        }
        // microSD access (right wall, just under the Pi PCB)
        if (sd_slot) translate([W - e, pby(sd_y) - 8, pi_z0 - 3.5]) cube([wall + 2*e, 16, 5]);
        // optional USB-A + Ethernet (left wall)
        if (open_usb_eth) translate([-wall - e, pby(54), pi_z1 - 0.5]) cube([wall + 2*e, 52, pi_tallest + 0.5]);
    }
    // corner posts for lid screws
    for (p = post_xy()) translate([p[0], p[1], front_t])
        difference() {
            cylinder(d = post_d, h = D - front_t);
            translate([0, 0, D - front_t - 12]) cylinder(d = 2.5, h = 12 + e);
        }
}
function post_xy() = [[post_d/2 - 1, post_d/2 - 1], [W - post_d/2 + 1, post_d/2 - 1],
                      [post_d/2 - 1, H - post_d/2 + 1], [W - post_d/2 + 1, H - post_d/2 + 1]];

/* ---------- LID (back): fan grille + Pi standoffs ---------- */
// Modelled in box frame; print it flipped (outer face down) — the Makefile does this.
module lid() {
    standoff_h = D - pi_z1;
    difference() {
        union() {
            translate([-wall, -wall, D]) rrect([OW, OH], R, lid_t);
            // locating lip inside the shell
            translate([clr, clr, D - 1.5]) difference() {
                cube([W - 2*clr, H - 2*clr, 1.5 + e]);
                translate([1.6, 1.6, -e]) cube([W - 2*clr - 3.2, H - 2*clr - 3.2, 2]);
            }
            // Pi standoffs (M2.5 self-tapping from the PCB side)
            for (h = pi_hole) translate([pbx(h[0]), pby(h[1]), pi_z1]) cylinder(d = 5.5, h = standoff_h + e);
        }
        for (h = pi_hole) translate([pbx(h[0]), pby(h[1]), pi_z1 - e]) cylinder(d = 2.1, h = standoff_h - 0.8);
        // clear the lip around the corner posts
        for (p = post_xy()) translate([p[0], p[1], D - 2]) cylinder(d = post_d + 2*clr, h = 2 + e);
        // M3 screw holes + counterbores
        for (p = post_xy()) translate([p[0], p[1], D - 2]) {
            cylinder(d = 3.4, h = lid_t + 3);
            translate([0, 0, 2 + lid_t - 1.8]) cylinder(d = 6.2, h = 2);
        }
        // grille over the Active Cooler / fan intake (whole Pi area minus the standoffs)
        translate([0, 0, D - 2]) linear_extrude(lid_t + 3) difference() {
            translate([pbx(pi_w) + 4, Y0 + 5]) slots(9, pi_w - 8, 3, (pi_h - 13) / 8);
            for (h = pi_hole) translate([pbx(h[0]), pby(h[1])]) circle(d = 9);   // solid pads under standoffs
        }
        // engraved label
        translate([W/2, 3.2, D + lid_t - 0.6]) linear_extrude(1)
            text("RTDMS", size = 4, halign = "center", font = "Liberation Sans:style=Bold");
    }
}

/* ---------- CAMERA PLATE (front bezel holding the camera) ---------- */
// Modelled with its front face at z=0, centre at origin. Prints face down as-is.
module camera_plate() {
    so_h = cam_z - plate_t;   // standoff height from plate back to camera board
    difference() {
        union() {
            rrect_c(plate, 2, plate_t);
            for (sx = [-1, 1], sy = [-1, 1])
                translate([sx*cam_holes[0]/2, sy*cam_holes[1]/2, plate_t - e]) cylinder(d = 4.5, h = so_h + e);
        }
        translate([0, 0, -e]) cylinder(d = lens_d + 1, h = 50);                       // lens
        for (sx = [-1, 1]) translate([sx*led_dx, led_dy, -e]) cylinder(d = led_d + 1, h = plate_t + 2*e);  // IR LEDs
        for (sx = [-1, 1], sy = [-1, 1]) {
            translate([sx*cam_holes[0]/2, sy*cam_holes[1]/2, 0.8]) cylinder(d = 1.7, h = 50);  // M2 pilots (blind)
            translate([sx*plate_screw[0], sy*plate_screw[1], -e]) {                        // M2.5 to shell
                cylinder(d = 2.8, h = plate_t + 2*e);
                cylinder(d1 = 5.2, d2 = 2.8, h = 1.2);                                     // countersink
            }
        }
    }
}

/* ---------- dummy parts for the assembly preview ---------- */
module pi_dummy() {
    color("green") translate([X0, Y0, pi_z0]) cube([pi_w, pi_h, pi_pcb]);
    color("silver") translate([X0 - pi_overhang, Y0 + 2, pi_z1]) cube([21, 52, pi_tallest]);      // USB/Eth
    color("silver") translate([X0 + 10, Y0 + 4, pi_z1]) cube([56, 48, 10]);                       // cooler
    color("dimgray") translate([pbx(usbc_x) - 4.5, Y0 + pi_h - 7.5, pi_z1]) cube([9, 7.5, 3.3]);  // USB-C
}
module cam_dummy() {
    translate([cx, cy, 0]) {
        color("black") translate([0, 0, cam_z]) rrect_c(cam_pcb, 1, cam_pcb_t);
        color("dimgray") translate([0, 0, -1]) cylinder(d = lens_d, h = cam_z + 1);
        for (sx = [-1, 1]) color("white") translate([sx*led_dx, led_dy, plate_t]) cylinder(d = led_d, h = cam_z - plate_t);
    }
}

/* ---------- output ---------- */
if (part == "shell") shell();
else if (part == "lid") translate([0, 0, D + lid_t]) mirror([0, 0, 1]) lid();
else if (part == "camera_plate") camera_plate();
else if (part == "assembly") assembly(explode = 0);
else if (part == "exploded") assembly(explode = 35);
else if (part == "section") difference() {   // cut through the right-hand Pi standoffs, view from -x
    assembly(explode = 0); translate([-50, -100, -50]) cube([pbx(3.5) + 50, 200, 200]); }

// Preview: rotated so the box stands upright (world z = up), camera facing world +y.
module assembly(explode) rotate([90, 0, 0]) {
    color("#2b2b2b") shell();
    translate([0, 0, explode]) { color("#3a3a3a") lid(); pi_dummy(); }
    translate([0, 0, -explode]) { color("#555") translate([cx, cy, 0]) camera_plate(); cam_dummy(); }
}

echo(str("OUTER SIZE (W x H x D incl. lid): ", OW, " x ", OH, " x ", D + lid_t, " mm"));
echo(str("Pi standoff height on lid: ", D - pi_z1, " mm   camera standoffs: ", cam_z - plate_t, " mm"));
