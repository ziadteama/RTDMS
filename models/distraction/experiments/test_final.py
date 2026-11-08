from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import hashlib, json, sys
from pathlib import Path
import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
split = json.load(open(str(REPO / "configs/syndd_split.json")))
segs = [s for s in D.syndd(f"{DATA}/public/syndd/A1") if split.get(s.driver) == "test"]
videos = sorted({str(s.video) for s in segs})
r = load_rules_config(); r.mode = "simple"
B = f"{DATA}/runs/det_v2b_416/weights/best.pt"; V = f"{DATA}/runs/det_v2d_ir_512/weights/best.pt"
runs = {"BEFORE det_v2b @0.25": ("det_v2b", B, 416, {"phone": .25, "drink": .25, "food": .25}),
        "det_v2b tuned @0.35": ("det_v2b", B, 416, {"phone": .35, "drink": .35, "food": .35}),
        "det_v2d @0.25": ("det_v2d", V, 512, {"phone": .25, "drink": .25, "food": .25}),
        "AFTER det_v2d phone .40 drink .45": ("det_v2d", V, 512, {"phone": .40, "drink": .45, "food": .40})}
out = {}
for label, (name, w, sz, conf) in runs.items():
    st = Path(w).stat()
    key = hashlib.sha1(f"{Path(w).resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
    ev = {v: E.replay(Path(f"{DATA}/eval_cache/faces/fps10/{Path(v).stem}.npz"),
                      Path(f"{DATA}/eval_cache/dets/{name}_{sz}_{key}/fps10/{Path(v).stem}.npy"), conf, r)
          for v in videos}
    res = E.summarise(E.score(segs, ev)); out[label] = res
    print("==", label, f"({res['_neg_hours']:.2f} h negatives)")
    for row in E.ROWS:
        x = res[row]; rr = x["recall_range"] or [0, 0]; fr = x["fa_per_h_range"] or [0, 0]
        tta = "-" if x["tta_median_s"] is None else f"{x['tta_median_s']:.1f}"
        print(f"  {row:16s} recall {x['recall']:.2f} [{rr[0]:.2f}-{rr[1]:.2f}]  FA/h {x['fa_per_h']:.1f} [{fr[0]:.1f}-{fr[1]:.1f}]  TTA {tta} s")
json.dump(out, open(sys.argv[1], "w"), indent=1)
