"""IR step 3: fusion-stage changes for the eating head, ONE at a time, each kept only on IR
validation (untrimmed SynDD-val): eating recall may drop by <= 1 event and eating FA/h (all
non-eating clips) may not rise. The event rule (thr, m) is re-picked on validation per variant.

Changes, in order: E-2 phone veto (no eating while the v2 phone call/texting alert is on or was
on in the last 2 s — phone models only read); E-3 yawn veto (lip gap / face width > thr, thr on
val); E-4 no eating while the product drinking alert is on (cup model + rule, IR-3 params).
Test (SynDD-test) scored once for the final kept set, report only.

python ir_eat_fusion.py
"""

import importlib
import json

import ir_eat_train as E
import numpy as np
import overnight_fusion as F
import torch

GRID = [(t, m) for t in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98) for m in (1, 2, 3, 5)]


def pick(vids, probs):
    best = None
    for thr, m in GRID:
        r = E.score(vids, probs, thr, m)
        obj = r["caught"][0] / r["caught"][1] - 0.02 * r["fa_per_h"]
        if best is None or obj > best[0]:
            best = (obj, thr, m, r)
    return best


def masked(vids, probs, masks):
    return [np.where(mk, 0.0, p) for p, mk in zip(probs, masks, strict=True)]


def phone_mask(vids, rows):
    return [np.array(F.veto_mask([{"t": t} for t in v["t"]], rows.get(v["clip"], []), True, None))
            for v in vids]


def yawn_mask(vids, rows, thr):
    return [np.array(F.veto_mask([{"t": t} for t in v["t"]], rows.get(v["clip"], []), False, thr))
            for v in vids]


def drink_mask(vids, split):
    """Drinking alert of the product model (IR-3) from its saved predictions (val and test)."""
    b = importlib.import_module("phase_b")
    b.DrinkingRule = importlib.import_module("held_alerts").DrinkingRule
    res = json.loads((F.OUT / f"ir/{E.MODEL_DIR}/results.json").read_text())
    params = res["candidate_val"]["params"]
    out = []
    for v in vids:
        p = F.OUT / f"ir/{E.MODEL_DIR}/predictions" / f"syndd_{v['clip']}.json"
        on_t = []
        if p.exists():
            sc = json.loads(p.read_text())
            rule = b.DrinkingRule(**params)
            for f in sc["frames"]:
                on, _ = rule.update(f["t"], f["near"]["nano"], f["probs"].get("nano|nano/pt"), f["pitch"])
                if on:
                    on_t.append(f["t"])
        on_t = np.array(on_t)
        out.append(np.array([bool(len(on_t)) and np.min(np.abs(on_t - t)) <= 1.0 for t in v["t"]]))
    return out


def keep(cur, cand):
    return (cand["caught"][0] >= cur["caught"][0] - 1 and cand["fa_per_h"] <= cur["fa_per_h"] + 1e-9)


def main():
    fz = E.Featurizer()
    data = {s: E.load_split(s, fz) for s in ("val", "test")}
    dim = next(v["feats"].shape[1] for v in data["val"] if len(v["feats"]))
    head = E.Head(dim)
    import os

    head.load_state_dict(torch.load(F.OUT / f"ir/{os.environ.get('EAT_HEAD_OUT', 'eat_head')}.pt"))
    head = head.to(E.DEV).eval()
    probs = {s: [E.eat_probs(head, v, dim) for v in vids] for s, vids in data.items()}
    rows = {"val": F.phone_rows("syndd", "val"), "test": F.phone_rows("syndd", "test")}
    masks = {s: [np.zeros(len(v["t"]), bool) for v in vids] for s, vids in data.items()}
    _, thr, m, cur = pick(data["val"], probs["val"])
    log = [dict(change="E-1 gated head (baseline)", params=(thr, m), val=cur, kept=True)]
    F.log(f"Eat fusion E-1 baseline thr={thr} m={m}: val {cur['caught']} {cur['fa_per_h']}/h {cur['false_by_type']}")
    final = (thr, m)

    def trial(name, extra):
        nonlocal cur, final
        cand_masks = {s: [a | b_ for a, b_ in zip(masks[s], extra[s], strict=True)] for s in masks}
        _, t2, m2, r = pick(data["val"], masked(data["val"], probs["val"], cand_masks["val"]))
        k = keep(cur, r)
        F.log(f"Eat fusion {name} thr={t2} m={m2}: val {r['caught']} {r['fa_per_h']}/h {r['false_by_type']} vs "
              f"{cur['caught']} {cur['fa_per_h']}/h -> {'KEPT' if k else 'REVERTED'}")
        log.append(dict(change=name, params=(t2, m2), val=r, kept=k))
        if k:
            masks.update(cand_masks)
            cur, final = r, (t2, m2)

    trial("E-2 phone veto", {s: phone_mask(data[s], rows[s]) for s in data})
    best_y = None
    for ythr in (0.10, 0.15, 0.20, 0.25, 0.30):
        ym = {s: yawn_mask(data[s], rows[s], ythr) for s in data}
        cm = {s: [a | b_ for a, b_ in zip(masks[s], ym[s], strict=True)] for s in masks}
        o = pick(data["val"], masked(data["val"], probs["val"], cm["val"]))
        if best_y is None or o[0] > best_y[0]:
            best_y = (o[0], ythr, ym)
    trial(f"E-3 yawn veto (lip/face width > {best_y[1]})", best_y[2])
    trial("E-4 no eating while drinking alert", {s: drink_mask(data[s], s) for s in data})
    thr, m = final
    test = E.score(data["test"], masked(data["test"], probs["test"], masks["test"]), thr, m)
    F.log(f"Eat fusion FINAL thr={thr} m={m}: IR test (report only) {test['caught']} {test['fa_per_h']}/h "
          f"{test['false_by_type']}")
    out = dict(log=log, final_params=final, test_report_only=test)
    (F.OUT / f"ir/{os.environ.get('EAT_HEAD_OUT', 'eat_head')}_fusion.json").write_text(json.dumps(
        out, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    F.log("JOB eat_fusion DONE")


if __name__ == "__main__":
    main()
