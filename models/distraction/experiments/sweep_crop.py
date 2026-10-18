"""python sweep_crop.py <split> <out.json> <phone thresholds,...>  : det_v2d full frame (+ crop pass)"""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib, json, sys
from pathlib import Path
import numpy as np
import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
split_name, out_p = sys.argv[1], sys.argv[2]
ths = [float(x) for x in sys.argv[3].split(",")]
split = json.load(open(str(REPO / "configs/syndd_split.json")))
segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
videos = sorted({str(s.video) for s in segs})
w = Path(f"{DATA}/runs/det_v2d_ir_512/weights/best.pt"); st = w.stat()
key = hashlib.sha1(f"{w.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
full = f"{DATA}/eval_cache/dets/det_v2d_512_" + key + "/fps10"
crop = f"{DATA}/eval_cache/dets/det_v2d_crop_s3.5_416/fps10"
merged = Path(f"{DATA}/eval_cache/dets/det_v2d_full_plus_crop/fps10"); merged.mkdir(parents=True, exist_ok=True)
for v in videos:
    a = np.load(f"{full}/{Path(v).stem}.npy"); b = np.load(f"{crop}/{Path(v).stem}.npy")
    np.save(merged / f"{Path(v).stem}.npy", np.concatenate([a, b]) if len(b) else a)
out = {}
for mode, d in (("full only", full), ("full + crop", str(merged))):
    for th in ths:
        r = load_rules_config(); r.mode = "simple"
        conf = {"phone": th, "drink": .45, "food": .40}
        ev = {v: E.replay(Path(f"{DATA}/eval_cache/faces/fps10/{Path(v).stem}.npz"), Path(f"{d}/{Path(v).stem}.npy"), conf, r) for v in videos}
        res = E.summarise(E.score(segs, ev)); name = f"{mode} phone>={th}"; out[name] = res
        print(f"{name:24s} R {res['phone_right_ear']['recall']:.2f} L {res['phone_left_ear']['recall']:.2f} hand {res['phone_in_hand']['recall']:.2f} "
              f"phoneFA/h {res['phone_right_ear']['fa_per_h']:.1f} drink {res['drinking']['recall']:.2f} drinkFA/h {res['drinking']['fa_per_h']:.1f}", flush=True)
json.dump(out, open(out_p, "w"), indent=1)
