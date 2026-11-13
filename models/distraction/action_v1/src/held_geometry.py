"""Phase A geometry correction from cached keypoints only; no inference or crop build.

Fits the pose-mouth fallback on SynDD train only, evaluates h x K, and selects only from
SynDD-val plus 3MDAD/EBDD train. Original audit files remain unchanged.
"""
# ruff: noqa: E402
import bisect
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True

import cv2
import numpy as np
from held_wrist import CONF, OUT, load_cache, log, read_frame

ROOT = OUT / "geometry_v2"
HS = (0.0, .35, .5)
KS = (1.0, 1.25, 1.5)
LIMITS = {("syndd", "val"): .02, ("3mdad", "train"): .05, ("ebdd", "train"): .05}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf8")


def valid(kp, i):
    return bool(np.isfinite(kp[i]).all() and kp[i, 2] >= CONF)


def head(kp):
    if not all(valid(kp, i) for i in (0, 1, 2)):
        return None
    nose, eyes = kp[0, :2], (kp[1, :2] + kp[2, :2]) / 2
    scales = {"inter_eye": float(np.linalg.norm(kp[1, :2] - kp[2, :2]))}
    eye_ear = [np.linalg.norm(kp[e, :2] - kp[a, :2])
               for e, a in ((1, 3), (2, 4)) if valid(kp, a)]
    scales["eye_ear"] = float(np.mean(eye_ear)) if eye_ear else float("nan")
    return nose, nose - eyes, scales


def fit_fallback(paths):
    log("Geometry: fitting c and g using SynDD-TRAIN mesh/pose pairs only")
    samples, coverage = [], defaultdict(int)
    for p in paths:
        data = read(p)
        job = data["job"]
        if job["dataset"] != "syndd" or job["split"] != "train":
            continue
        for r in data["records"]:
            coverage["train_frames"] += 1
            kp = np.asarray(r["kp"], float)
            if kp.shape != (17, 3):
                raise ValueError(f"Cache lacks full elbows/head keypoints: {p}")
            h = head(kp)
            if not r["face"] or h is None:
                continue
            nose, vector, scales = h
            fh = r["face_height"]
            samples.append((job["driver"], vector / fh,
                            (np.asarray(r["mouth"]) - nose) / fh,
                            [scales[s] / fh for s in ("inter_eye", "eye_ear")]))
    drivers = sorted({r[0] for r in samples})
    held_drivers = set(drivers[::5])
    v = np.array([r[1] for r in samples])
    y = np.array([r[2] for r in samples])
    scales = np.array([r[3] for r in samples])
    held = np.array([r[0] in held_drivers for r in samples])
    if len(samples) < 100 or not held.any() or held.all():
        raise ValueError("Not enough SynDD-train driver-separated head/mesh pairs")

    def coefficients(mask):
        c = float(np.sum(v[mask] * y[mask]) / np.sum(v[mask] ** 2))
        gs = {}
        for i, name in enumerate(("inter_eye", "eye_ear")):
            x = scales[mask, i]
            x = x[np.isfinite(x) & (x > 0)]
            gs[name] = float(np.sum(x) / np.sum(x * x))
        return c, gs

    def errors(mask, c, gs):
        mouth = np.linalg.norm(c * v[mask] - y[mask], axis=1)
        result = {"frames": int(mask.sum()), "mouth_mean_fh": float(mouth.mean()),
                  "mouth_median_fh": float(np.median(mouth)),
                  "mouth_p90_fh": float(np.percentile(mouth, 90)), "height": {}}
        for i, name in enumerate(("inter_eye", "eye_ear")):
            x = scales[mask, i]
            x = x[np.isfinite(x) & (x > 0)]
            error = np.abs(gs[name] * x - 1)
            result["height"][name] = dict(frames=len(x), mean_fh=float(error.mean()),
                                           p90_fh=float(np.percentile(error, 90)))
        return result

    c0, g0 = coefficients(~held)
    holdout_error = errors(held, c0, g0)
    preferred = min(g0, key=lambda name: holdout_error["height"][name]["mean_fh"])
    c, gs = coefficients(np.ones(len(samples), bool))
    fit = dict(c=c, g=gs, preferred_height=preferred, head_confidence=CONF,
               formula="mouth=nose+c*(nose-eye_mid); height=g*scale; no intercept",
               loss="least squares in mesh-face-height-normalized coordinates",
               fit_frames=len(samples), fit_drivers=len(drivers),
               internal_holdout_drivers=sorted(held_drivers),
               internal_holdout=holdout_error,
               final_train_errors=errors(np.ones(len(samples), bool), c, gs),
               coverage=dict(coverage), inference_calls=0)
    save(ROOT / "mouth_fit.json", fit)
    saved = read(ROOT / "mouth_fit.json")
    log("Read mouth_fit.json: " + json.dumps({k: saved[k] for k in
        ("c", "g", "preferred_height", "fit_frames", "fit_drivers", "internal_holdout")}))
    return fit


def pose_mouth(kp, fit):
    h = head(kp)
    if h is None:
        return None
    nose, vector, scales = h
    order = [fit["preferred_height"]] + [s for s in scales if s != fit["preferred_height"]]
    for name in order:
        fh = scales[name] * fit["g"][name]
        if np.isfinite(fh) and fh > 1:
            return nose + fit["c"] * vector, float(fh)
    return None


def mesh_history(job, records):
    kind, cache = load_cache(job)
    scale = None
    for r in records:
        entry = cache.get(round(r["t"], 1 if job["dataset"] == "syndd" else 3))
        if r["face"] and entry is not None and entry[0]:
            fh = np.linalg.norm(entry[1][10] - entry[1][152])
            if fh > 1:
                scale = r["face_height"] / fh
                break
    history = {}
    if cache:
        if scale is None:
            caps = {}
            gray = read_frame(records[0]["source"], caps)
            for cap in caps.values():
                cap.release()
            if gray is None:
                raise OSError("Cannot establish cache coordinate scale")
            scale = gray.shape[1] / 640.0
        for t, (ok, lm, _) in cache.items():
            if ok:
                mouth = (lm[13] + lm[14]) / 2 * scale
                fh = float(np.linalg.norm(lm[10] - lm[152]) * scale)
                if np.isfinite([*mouth, fh]).all() and fh > 1:
                    history[t] = (mouth, fh)
    for r in records:
        if r["face"]:
            history[r["t"]] = (np.asarray(r["mouth"]), r["face_height"])
    return sorted(history), history, kind


def hand_geometry(kp, mouth, fh, h):
    candidates = []
    for elbow, wrist in ((7, 9), (8, 10)):
        if valid(kp, wrist):
            extended = valid(kp, elbow)
            point = kp[wrist, :2].copy()
            if extended:
                point += h * (kp[wrist, :2] - kp[elbow, :2])
            distance = float(np.linalg.norm(point - mouth) / fh) if mouth is not None else None
            candidates.append(dict(hand=point.tolist(), wrist=kp[wrist, :2].tolist(),
                                   wrist_id=wrist, elbow_usable=extended, distance=distance))
    if not candidates:
        return dict(hand=None, wrist=None, distance=None, crop=None)
    nearest = min(candidates, key=lambda c: c["distance"] if c["distance"] is not None else 0)
    crop = None
    if mouth is not None:
        point = np.asarray(nearest["hand"])
        center = (mouth + point) / 2
        side = max(2 * fh, 1.3 * np.linalg.norm(mouth - point))
        crop = dict(center=center.tolist(), side=float(side),
                    xyxy=[*(center - side / 2).tolist(), *(center + side / 2).tolist()])
    return dict(**nearest, crop=crop)


def write_table(path, rows):
    with open(path, "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def choose(totals):
    candidates = []
    for h in HS:
        for k in KS:
            rows = [r for r in totals if r["h"] == h and r["K"] == k]
            normals = {}
            for ds_sp, limit in LIMITS.items():
                row = next(r for r in rows if (r["dataset"], r["split"]) == ds_sp
                           and r["cls"] == "normal")
                normals["/".join(ds_sp)] = dict(rate=row["pass_rate"], limit=limit)
            positives = {}
            for cls in ("drinking", "eating"):
                selected = [r for r in rows if (r["dataset"], r["split"]) in LIMITS
                            and r["cls"] == cls]
                positives[cls] = sum(r["passed"] for r in selected) / sum(
                    r["frames"] for r in selected)
            violation = max(v["rate"] / v["limit"] for v in normals.values())
            candidates.append(dict(h=h, K=k, normal_constraints=normals,
                                   positive_rates=positives,
                                   objective=float(np.mean(list(positives.values()))),
                                   max_constraint_ratio=violation, feasible=violation <= 1))
    feasible = [c for c in candidates if c["feasible"]]
    def rank(c):
        return -c["objective"], c["K"], c["h"]
    chosen = min(feasible, key=rank) if feasible else None
    illustration = chosen or min(candidates, key=lambda c: (c["max_constraint_ratio"], *rank(c)))
    selection = dict(chosen=chosen, sheet_parameters=illustration, candidates=candidates,
                     objective="mean of drinking and eating pass rates; each class pooled over "
                     "SynDD-val + 3MDAD-train + EBDD-train; all frames in denominator",
                     tie_break="smaller K, then smaller h", test_used_for_selection=False,
                     build_ready=False,
                     status="selected_for_review" if chosen else "no_feasible_grid",
                     note="No constraints relaxed; infeasible parameters are illustration only.")
    save(ROOT / "selection.json", selection)
    saved = read(ROOT / "selection.json")
    log("Read geometry selection.json: " + json.dumps(saved))
    return selection


def make_sheets(paths, setting, approved):
    rng, pools = random.Random(26), defaultdict(list)
    for p in paths:
        data = read(p)
        job = data["job"]
        groups = defaultdict(list)
        for r in data["records"]:
            group = "lost_drinking" if r["cls"] == "drinking" and not r["mesh_face"] else r["cls"]
            groups[group].append(r)
        for cls, records in groups.items():
            pools[(job["dataset"], cls)] += [(job, r) for r in rng.sample(
                records, min(16, len(records)))]
    for ds in ("syndd", "3mdad", "ebdd", "dad"):
        selected = []
        for cls, count in (("lost_drinking", 6), ("drinking", 6), ("eating", 6), ("normal", 6)):
            pool = pools[(ds, cls)]
            selected += rng.sample(pool, min(count, len(pool)))
        used = {(j["clip"], r["t"]) for j, r in selected}
        extra = [(j, r) for (dataset, _), pool in pools.items() if dataset == ds for j, r in pool
                 if (j["clip"], r["t"]) not in used]
        selected += rng.sample(extra, min(24 - len(selected), len(extra)))
        canvas = np.zeros((math.ceil(len(selected) / 2) * 448 + 36, 1024, 3), np.uint8)
        title = f"{ds}: h={setting['h']} K={setting['K']} " + (
            "FOR REVIEW" if approved else "ILLUSTRATION ONLY: NO FEASIBLE GRID")
        cv2.putText(canvas, title, (5, 25), 0, .6, (255, 255, 255), 1)
        caps, index = {}, []
        for i, (job, r) in enumerate(selected):
            gray = read_frame(r["source"], caps)
            if gray is None:
                raise OSError(r["source"])
            image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            kp = np.asarray(r["kp"])
            for e, w in ((7, 9), (8, 10)):
                if valid(kp, w):
                    wrist = kp[w, :2]
                    point = wrist + setting["h"] * (wrist - kp[e, :2]) if valid(kp, e) else wrist
                    cv2.circle(image, tuple(np.rint(wrist).astype(int)), 4, (0, 255, 0), -1)
                    cv2.circle(image, tuple(np.rint(point).astype(int)), 4, (0, 255, 255), -1)
            if r["mouth"] is not None:
                mouth = tuple(np.rint(r["mouth"]).astype(int))
                color = {"mesh": (0, 0, 255), "held": (255, 0, 255),
                         "pose-fallback": (255, 255, 0)}[r["face_source"]]
                cv2.circle(image, mouth, round(setting["K"] * r["face_height"]), (200, 120, 0), 2)
                cv2.circle(image, mouth, 4, color, -1)
                if r["crop"]:
                    x1, y1, x2, y2 = np.rint(r["crop"]["xyxy"]).astype(int)
                    cv2.rectangle(image, (x1, y1), (x2, y2), (255, 255, 255), 2)
            scale = min(512 / image.shape[1], 400 / image.shape[0])
            view = cv2.resize(image, (round(image.shape[1] * scale), round(image.shape[0] * scale)))
            tile = np.zeros((448, 512, 3), np.uint8)
            tile[:view.shape[0], :view.shape[1]] = view
            text = f"{job['clip']} t={r['t']:.2f} {r['cls']} {job['split']}"
            cv2.putText(tile, text[:66], (3, 417), 0, .38, (255, 255, 255), 1)
            text = f"mouth={r['face_source']} mesh_lost={not r['mesh_face']} d={r['distance']}"
            cv2.putText(tile, text[:65], (3, 435), 0, .38, (255, 255, 255), 1)
            y, x = divmod(i, 2)
            canvas[36+y*448:36+(y+1)*448, x*512:(x+1)*512] = tile
            index.append(dict(clip=job["clip"], split=job["split"], record=r))
        for cap in caps.values():
            cap.release()
        dest = OUT / "sheets" / f"wrist_{ds}.jpg"
        if not cv2.imwrite(str(dest), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85]):
            raise OSError(dest)
        save(dest.with_suffix(".json"), index)
        lost = sum(not x["record"]["mesh_face"] and x["record"]["cls"] == "drinking"
                   for x in index)
        log(f"Geometry sheet {ds}: {len(index)} tiles, 512 px wide; includes {lost} "
            "mesh-lost drinking frames; red=mesh, magenta=held, cyan=pose mouth")


def main():
    cv2.setNumThreads(1)
    for p in (ROOT, ROOT / "base", ROOT / "selected"):
        p.mkdir(parents=True, exist_ok=True)
    log("Geometry job starting: cached data only, no inference, no build, no training")
    complete = read(OUT / "audit_complete.json")
    paths = [OUT / p for p in complete["geometry"]]
    fit = fit_fallback(paths)
    counts, totals, sources = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0, 0]), []
    availability = defaultdict(int)
    for i, p in enumerate(paths, 1):
        data = read(p)
        job, records = data["job"], data["records"]
        if not records:
            continue
        times, history, _ = mesh_history(job, records)
        corrected = []
        for original in records:
            kp = np.asarray(original["kp"], float)
            if kp.shape != (17, 3):
                raise ValueError(f"Cache lacks elbow/nose fields: {p}")
            availability["frames"] += 1
            availability["confident_head"] += head(kp) is not None
            availability["confident_elbow_wrists"] += sum(
                valid(kp, e) and valid(kp, w) for e, w in ((7, 9), (8, 10)))
            mouth, fh, source, age = None, None, "unavailable", None
            if original["face"]:
                mouth, fh, source = np.asarray(original["mouth"]), original["face_height"], "mesh"
            else:
                idx = bisect.bisect_right(times, original["t"]) - 1
                if idx >= 0 and 0 <= original["t"] - times[idx] <= 1:
                    mouth, fh = history[times[idx]]
                    source, age = "held", original["t"] - times[idx]
                else:
                    predicted = pose_mouth(kp, fit)
                    if predicted is not None:
                        mouth, fh = predicted
                        source = "pose-fallback"
            r = dict(original, mesh_face=original["face"],
                     mesh_cache_source=original["face_source"])
            r.update(mouth=None if mouth is None else mouth.tolist(), face_height=fh,
                     face_source=source, face=mouth is not None, hold_age_s=age)
            corrected.append(r)
            for h in HS:
                geo = hand_geometry(kp, mouth, fh, h)
                for k in KS:
                    key = (h, k, job["dataset"], job["split"], r["cls"])
                    passed = geo["distance"] is not None and geo["distance"] <= k
                    for row in (totals[key], counts[(*key, source)]):
                        row[0] += 1
                        row[1] += geo["hand"] is not None
                        row[2] += passed
        dest = ROOT / "base" / p.name
        save(dest, dict(job=job, records=corrected))
        sources.append(dest)
        if i % 20 == 0:
            log(f"Geometry grid progress: {i}/{len(paths)} clips; {availability['frames']} frames")
    def table(counter, with_source):
        rows = []
        for key, (n, usable, passed) in sorted(counter.items()):
            h, k, ds, sp, cls = key[:5]
            row = dict(h=h, K=k, dataset=ds, split=sp, cls=cls)
            if with_source:
                row["face_source"] = key[5]
            rows.append(dict(**row, frames=n, hand_usable=usable, passed=passed,
                             pass_rate=passed/n, pass_percent=100*passed/n))
        return rows
    rows = table(totals, False)
    write_table(ROOT / "proximity_totals.csv", rows)
    write_table(ROOT / "proximity_grid.csv", table(counts, True))
    save(ROOT / "cache_availability.json", dict(availability, inference_calls=0))
    log("Read cache_availability.json: " + json.dumps(read(ROOT / "cache_availability.json")))
    selection = choose(rows)
    setting = selection["sheet_parameters"]
    selected_paths = []
    for p in sources:
        data = read(p)
        for r in data["records"]:
            mouth = None if r["mouth"] is None else np.asarray(r["mouth"])
            r.update(hand_geometry(np.asarray(r["kp"]), mouth, r["face_height"], setting["h"]))
        dest = ROOT / "selected" / p.name
        save(dest, data)
        selected_paths.append(dest)
    with open(ROOT / "proximity_totals.csv", encoding="utf8") as f:
        for r in csv.DictReader(f):
            if float(r["h"]) == setting["h"] and float(r["K"]) == setting["K"]:
                if r["cls"] in ("normal", "drinking", "eating"):
                    log("Read geometry result (sheet parameters): " + json.dumps(r))
    make_sheets(selected_paths, setting, selection["chosen"] is not None)
    save(ROOT / "geometry_complete.json", dict(
        datasets=complete["datasets"], geometry=[str(p.relative_to(OUT)) for p in selected_paths],
        selection=selection, inference_calls=0, build_ready=False))
    log("Geometry analysis and larger sheets complete; crop build remains on hold for review")


if __name__ == "__main__":
    main()
