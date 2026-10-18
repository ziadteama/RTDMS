"""python sweep_track.py <split> <out.json> [low,gap ...]  (det_v2d, high phone .40 drink .45 food .40)"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib, json, sys
from pathlib import Path
import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
split_name, out_p = sys.argv[1], sys.argv[2]
combos = [tuple(map(float, c.split(","))) for c in sys.argv[3:]] or [(0, 0)]
split = json.load(open(str(REPO / "configs/syndd_split.json")))
segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
videos = sorted({str(s.video) for s in segs})
w = Path(f"{DATA}/runs/det_v2d_ir_512/weights/best.pt"); st = w.stat()
key = hashlib.sha1(f"{w.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
high = {"phone": .40, "drink": .45, "food": .40}
out = {}
for low, gap in combos:
    r = load_rules_config(); r.mode = "simple"
    if low > 0:
        r.simple.high, r.simple.track_low, r.simple.track_gap_s = high, low, gap
        conf = dict.fromkeys(high, low)
    else:
        conf = high
    ev = {v: E.replay(Path(f"{DATA}/eval_cache/faces/fps10/{Path(v).stem}.npz"),
                      Path(f"{DATA}/eval_cache/dets/det_v2d_512_{key}/fps10/{Path(v).stem}.npy"), conf, r)
          for v in videos}
    res = E.summarise(E.score(segs, ev)); name = "no tracking" if low == 0 else f"track low {low} gap {gap}"
    out[name] = res
    print(f"{name:26s} R {res['phone_right_ear']['recall']:.2f} L {res['phone_left_ear']['recall']:.2f} "
          f"hand {res['phone_in_hand']['recall']:.2f} phoneFA/h {res['phone_right_ear']['fa_per_h']:.1f} "
          f"drink {res['drinking']['recall']:.2f} drinkFA/h {res['drinking']['fa_per_h']:.1f} "
          f"TTA-R {res['phone_right_ear']['tta_median_s']}", flush=True)
json.dump(out, open(out_p, "w"), indent=1)
