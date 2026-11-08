"""python sweep_model.py <split> <name> <weights> <imgsz> <phone thr,...> <drink thr,...>"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib, json, sys
from pathlib import Path
import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
split_name, name, w, sz = sys.argv[1], sys.argv[2], Path(sys.argv[3]), int(sys.argv[4])
pts, dts = [float(x) for x in sys.argv[5].split(",")], [float(x) for x in sys.argv[6].split(",")]
split = json.load(open(str(REPO / "configs/syndd_split.json")))
segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
videos = sorted({str(s.video) for s in segs})
st = w.stat(); key = hashlib.sha1(f"{w.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
d = f"{DATA}/eval_cache/dets/{name}_{sz}_{key}/fps10"
out = {}
for pt in pts:
    for dt in dts:
        r = load_rules_config(); r.mode = "simple"
        ev = {v: E.replay(Path(f"{DATA}/eval_cache/faces/fps10/{Path(v).stem}.npz"), Path(f"{d}/{Path(v).stem}.npy"), {"phone": pt, "drink": dt, "food": 0.40}, r) for v in videos}
        res = E.summarise(E.score(segs, ev)); out[f"phone {pt} drink {dt}"] = res
        print(f"{name} {split_name} phone>={pt} drink>={dt}: R {res['phone_right_ear']['recall']:.2f} {[round(x, 2) for x in res['phone_right_ear']['recall_range']]} "
              f"L {res['phone_left_ear']['recall']:.2f} hand {res['phone_in_hand']['recall']:.2f} phoneFA/h {res['phone_right_ear']['fa_per_h']:.1f} {[round(x, 1) for x in res['phone_right_ear']['fa_per_h_range']]} "
              f"drink {res['drinking']['recall']:.2f} drinkFA/h {res['drinking']['fa_per_h']:.1f} TTA-R {res['phone_right_ear']['tta_median_s']}", flush=True)
json.dump(out, open(f"{DATA}/runs/overnight/sweep_{name}_{split_name}.json", "w"), indent=1)
