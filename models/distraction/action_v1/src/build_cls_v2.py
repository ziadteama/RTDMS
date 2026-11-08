"""v2 step 4: action-classifier folders with an extra hard-negative class "smoking" (3MDAD AC16,
which v1 maps to "other"). Same drivers / splits / 3x balancing as build_cls.py. SynDD-val has no
smoking, so the AC16 clips of 4 training subjects (seed 0) form the smoking part of val and are
left out of train.

python build_cls_v2.py -> data/cls_v2/{train,val}/<class>/*.jpg (hard links) + runs/balance_v2.md
"""
import random
from collections import Counter

import build_cls as B

B.OUT = B.A / "data" / "cls_v2"
B.CLASSES = B.CLASSES + ["smoking"]


def main():
    rng = random.Random(0)

    def relabel(rs):
        for r in rs:
            if r["dataset"] == "3mdad" and r["label"] == "AC16":
                r["cls"] = "smoking"
        return rs

    train = relabel([r for ds in ("syndd", "3mdad", "ebdd") for r in B.rows(ds)
                     if r["split"] == "train"]) + B.rows("syndd_fish")
    smk_drivers = sorted({r["driver"] for r in train if r["cls"] == "smoking"})
    val_smk = set(rng.sample(smk_drivers, 4))
    val = [r for r in B.rows("syndd") if r["split"] == "val"]
    val += [r for r in train if r["cls"] == "smoking" and r["driver"] in val_smk]
    train = [r for r in train if not (r["cls"] == "smoking" and r["driver"] in val_smk)]
    report = [f"smoking val drivers: {sorted(val_smk)}"]
    for split, rs in (("train", train), ("val", val)):
        bal, smallest, cap = B.balance(rs, 3, rng)
        B.link(bal, split)
        report.append(B.table(f"### {split} (smallest main class {smallest}, cap {cap})",
                              Counter(r["cls"] for r in rs), Counter(r["cls"] for r in bal)))
    text = "\n\n".join(report)
    (B.A / "runs" / "balance_v2.md").write_text(text, encoding="utf8")
    print(text)


if __name__ == "__main__":
    main()
