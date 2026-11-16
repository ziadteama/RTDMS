"""Overnight S4.1: label queue v2 for label_food_v2.html — all 1,161 food crops, CLIP food_visible
first (most confident first), then uncertain, then CLIP empty_hand. Writes food_items_v2.js and
label_food_v2.html next to the v1 page (v1 files untouched; separate localStorage key).

DAD eating crops: none — DAD's 3 drivers are all TEST drivers (H5), so none can be queued.

python food_queue_v2.py
"""

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "_held_data"
rows = [r for r in csv.DictReader(open(OUT / "held_object_v2/manifest.csv", encoding="utf8"))
        if r["old_label"] == "food"]
order = {"food_visible": 0, "uncertain": 1, "empty_hand": 2}


def conf(r):
    try:
        return float(r["confidence"])
    except ValueError:
        return 0.0


rows.sort(key=lambda r: (order[r["new_label"]], -conf(r)))
items = [dict(p="crops_loose_h035_k125/" + r["path"].replace("\\", "/").split("crops_loose_h035_k125/")[-1],
              ds=r["source_dataset"], sp=r["split"], dr=r["driver_id"], t=r["t"], tight=r["tight"],
              clip_label=r["new_label"], clip_conf=round(conf(r), 3)) for r in rows]
assert all((OUT / i["p"]).exists() for i in items), "missing crop"
(OUT / "food_items_v2.js").write_text("const ITEMS=" + json.dumps(items) + ";", encoding="utf8")
page = (OUT / "label_food.html").read_text(encoding="utf8")
page = page.replace("food_items.js", "food_items_v2.js").replace("held_food_labels_v1",
                                                                 "held_food_labels_v2")
page = page.replace("${it.tight === '1' ? 'tight' : 'loose'}",
                    "${it.tight === '1' ? 'tight' : 'loose'} · CLIP ${it.clip_label} ${it.clip_conf}")
page = page.replace("a.download = 'food_labels.csv'", "a.download = 'food_labels_v2.csv'")
(OUT / "label_food_v2.html").write_text(page, encoding="utf8")
counts = {k: sum(i["clip_label"] == k for i in items) for k in order}
print(len(items), counts)
