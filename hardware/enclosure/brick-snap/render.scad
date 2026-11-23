// Preview only: Brick Snap parts (assembled position) + the real Pi 5 board + a camera stand-in.
// xvfb-run -a openscad -o renders/x.png --imgsize=1400,1000 --colorscheme=Tomorrow -D 'view="assembly"' render.scad
view = "assembly";   // assembly | exploded
ex = view == "exploded" ? 1 : 0;
CAM_ZC = 15;

module pi5() color("#2f7d4f") translate([52.5, 43, 0]) rotate([0, 0, 90]) import("../brick/ref_derived/pi5_board.stl");
module camera() {
  color("#111") translate([-12.5, 8.5, CAM_ZC - 12]) cube([25, 1.6, 24]);
  color("#1d2a36") translate([0, -0.4, CAM_ZC]) rotate([-90, 0, 0]) cylinder(d = 14.6, h = 9, $fn = 48);
  for (s = [-1, 1]) {
    color("#222") translate([s * 27.5, 7.8, CAM_ZC]) rotate([-90, 0, 0]) cylinder(d = 24, h = 1.6, $fn = 48);
    color("#e6dfd3") translate([s * 27.5, 0.6, CAM_ZC]) rotate([-90, 0, 0]) cylinder(d = 18, h = 7.2, $fn = 48);
  }
}
module all() {
  color("#34373d") import("out/assembled/shell.stl");
  translate([0, 0, ex * 40]) color("#6f8fb5") import("out/assembled/lid.stl");
  translate([0, ex * 25, 0]) { color("#d9a441") import("out/assembled/camera_clip.stl");
                               color("#d9a441") rotate([0, 180, 0]) translate([0, 0, -2 * CAM_ZC]) import("out/assembled/camera_clip.stl"); }
  translate([0, 0, ex * 14]) pi5();
  translate([0, -ex * 25, 0]) camera();
}
if (view == "section") difference() { all(); translate([-100, 14, -50]) cube([200, 100, 200]); }
else if (view == "section2") difference() { all(); translate([-100, -50, 60]) cube([200, 200, 200]); }
else all();
