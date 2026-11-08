"""Recall / false alarms by SynDD appearance block (none / hat / sunglasses), det_v2d phone .40 drink .45."""
from _paths import DATA, EXP, PY, REPO  # noqa: E402,F401  (repo + data root)
import csv, hashlib, json, re
from collections import defaultdict
from pathlib import Path
import eval_simple as E
from rtdms_distraction import datasets as D
from rtdms_distraction.config import load_rules_config
split = json.load(open(str(REPO / "configs/syndd_split.json")))
A1 = Path(f"{DATA}/public/syndd/A1")
# appearance per (driver, block): the CSV's Appearance Block column on that video's rows
appear = {}
for c in A1.rglob("*.csv"):
    drv = "syndd_" + re.search(r"(\d{4,6})", c.stem).group(1)
    last = ""
    for r in csv.DictReader(open(c, encoding="utf-8-sig")):
        fn = (r.get("Filename") or "").strip() or last; last = fn
        nums = re.findall(r"\d+", fn)
        if len(nums) >= 2 and r.get("Appearance Block"):
            appear[(drv, int(nums[-1]))] = r["Appearance Block"].strip().lower() or "none"
segs = [s for s in D.syndd(str(A1)) if split.get(s.driver) in ("val", "test")]
videos = sorted({str(s.video) for s in segs})
w = Path(f"{DATA}/runs/det_v2d_ir_512/weights/best.pt"); st = w.stat()
key = hashlib.sha1(f"{w.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:10]
r = load_rules_config(); r.mode = "simple"
ev = {v: E.replay(Path(f"{DATA}/eval_cache/faces/fps10/{Path(v).stem}.npz"),
                  Path(f"{DATA}/eval_cache/dets/det_v2d_512_{key}/fps10/{Path(v).stem}.npy"),
                  {"phone": .40, "drink": .45, "food": .40}, r) for v in videos}
by = defaultdict(lambda: defaultdict(lambda: [0, 0]))
neg_s, fa = defaultdict(float), defaultdict(int)
for v in videos:
    vs = [s for s in segs if str(s.video) == v]
    blk = int(re.findall(r"\d+", Path(v).stem)[-1]); a = appear.get((vs[0].driver, blk), "?")
    a = "sunglasses" if "sun" in a else "hat" if "hat" in a else "none" if a in ("none", "") else a
    for s in vs:
        if s.label in E.ROWS:
            hit = any(e0 < s.end_s + 1 and e1 > s.start_s - 1 for e0, e1 in ev[v][E.ROWS[s.label]])
            by[a][s.label][1] += 1; by[a][s.label][0] += hit
        elif E.is_negative(s.label):
            neg_s[a] += s.end_s - s.start_s
    for e0, e1 in ev[v]["phone"]:
        if any(e0 < s.end_s + 1 and e1 > s.start_s - 1 for s in vs if E.ROWS.get(s.label) == "phone"):
            continue
        if any(E.is_negative(s.label) and s.start_s <= e0 < s.end_s for s in vs):
            fa[a] += 1
for a in sorted(by):
    cells = "  ".join(f"{k.replace('phone_', '')} {h}/{n}" for k, (h, n) in sorted(by[a].items()))
    print(f"{a:11s} {cells}  phoneFA {fa[a]} in {neg_s[a] / 3600:.2f} h")
