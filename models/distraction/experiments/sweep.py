from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib, json, sys
from pathlib import Path
import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
split_name = sys.argv[1]
models = {"det_v2b": (f"{DATA}/runs/det_v2b_416/weights/best.pt", 416),
          "det_v2d": (f"{DATA}/runs/det_v2d_ir_512/weights/best.pt", 512)}
confs = [float(c) for c in sys.argv[2].split(",")]
split = json.load(open(str(REPO / "configs/syndd_split.json")))
segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == split_name]
videos = sorted({str(s.video) for s in segs})
r = load_rules_config(); r.mode = "simple"
out = {}
for name, (w, sz) in models.items():
    st = Path(w).stat()
    key = hashlib.sha1(f"{Path(w).resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
    for c in confs:
        conf = {"phone": c, "drink": c, "food": c}
        ev = {v: E.replay(Path(f"{DATA}/eval_cache/faces/fps10/{Path(v).stem}.npz"),
                          Path(f"{DATA}/eval_cache/dets/{name}_{sz}_{key}/fps10/{Path(v).stem}.npy"), conf, r) for v in videos}
        res = E.summarise(E.score(segs, ev), n_boot=300)
        out[f"{name}@{c}"] = res
        print(f"{name} conf {c:.2f}: R-ear {res['phone_right_ear']['recall']:.2f} L-ear {res['phone_left_ear']['recall']:.2f} "
              f"hand {res['phone_in_hand']['recall']:.2f} phoneFA/h {res['phone_right_ear']['fa_per_h']:.1f} "
              f"drink {res['drinking']['recall']:.2f} drinkFA/h {res['drinking']['fa_per_h']:.1f}", flush=True)
json.dump(out, open(f"{DATA}/runs/overnight/sweep_{split_name}.json", "w"), indent=1)
