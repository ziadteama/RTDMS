// Preview only: Brick parts + the real Pi 5 model (from OpenPiCase STEP) + a simple camera stand-in.
view = "assembly";   // assembly | exploded | section
ex = view == "exploded" ? 1 : 0;
CAM_ZC = 15;

module pi5() // STEP frame -> box frame: rotate 90 about z, move (see brick.py pb())
  color("#2f7d4f") translate([52.5, 43, 0]) rotate([0, 0, 90]) import("ref_derived/pi5_board.stl");
module cooler_standin()  // Active Cooler is not in the STEP; rough block for reference
  color("#b9c0c8") translate([-28, 24, 6.7]) cube([56, 42, 10]);
module camera() {
  color("#111") translate([-12.5, 8.5, CAM_ZC - 12]) cube([25, 1.6, 24]);              // camera board
  color("#1d2a36") translate([0, -0.4, CAM_ZC]) rotate([-90, 0, 0]) cylinder(d = 14.6, h = 9, $fn = 48); // lens
  for (s = [-1, 1]) {
    color("#222") translate([s * 27.5, 7.8, CAM_ZC]) rotate([-90, 0, 0]) cylinder(d = 24, h = 1.6, $fn = 48); // IR board
    color("#e6dfd3") translate([s * 27.5, 0.6, CAM_ZC]) rotate([-90, 0, 0]) cylinder(d = 18, h = 7.2, $fn = 48); // IR dome
  }
}
module all() {
  color("#34373d") import("out/shell.stl");
  translate([0, 0, ex * 35]) color("#44484f") import("out/lid.stl");
  translate([0, ex * 20, 0]) { color("#6b7078") import("out/camera_clip.stl");
                               color("#6b7078") rotate([0, 180, 0]) translate([0, 0, -2 * CAM_ZC]) import("out/camera_clip.stl"); }
  translate([0, 0, ex * 14]) { pi5(); cooler_standin(); }
  translate([0, -ex * 25, 0]) camera();
}
if (view == "section") difference() { all(); translate([27.5, -50, -50]) cube([100, 200, 200]); }
else all();
