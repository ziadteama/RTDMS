"""Step 8: export the classifiers to ONNX and NCNN (FP16 and INT8), check the accuracy cost of each
format on SynDD-test frames, and time them on this PC's CPU (4 threads, like the Pi 5's 4 cores).

Pi 5 estimate: the release detector (det_v2d INT8 NCNN, 512 px) was measured on the Pi at ~45 ms
per run and face mesh at ~4.4 ms per frame. Each new model is timed here next to det_v2d with the
same runtime and thread count, and its Pi time is estimated as 45 ms x (its PC time / det_v2d PC
time).

python bench.py <action best.pt> <phone best.pt>
"""
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
A = Path("D:/rtdms-data/action_v1")
REPO = Path(r"C:\Users\youss\projects\RTDMS\models\distraction")
PI_DET_MS, PI_FACE_MS = 45.0, 4.4
DET_NCNN = REPO / "models" / "det_v2d_ir_512_det_aciq_mixed_ncnn_model"
TOOLS = Path(r"C:\Users\youss\rtdms-tools\ncnn")


def ncnn_time(model_dir, size, threads=4, n=200):
    import ncnn

    net = ncnn.Net()
    net.opt.num_threads = threads
    net.opt.use_vulkan_compute = False
    d = Path(model_dir)
    net.load_param(str(d / "model.ncnn.param"))
    net.load_model(str(d / "model.ncnn.bin"))
    x = np.random.rand(3, size, size).astype(np.float32)
    ins, outs = net.input_names(), net.output_names()
    ts = []
    for k in range(n + 20):
        t = time.perf_counter()
        ex = net.create_extractor()
        ex.input(ins[0], ncnn.Mat(x))
        ex.extract(outs[0])
        if k >= 20:
            ts.append((time.perf_counter() - t) * 1000)
    return round(float(np.median(ts)), 2)


def onnx_time(path, size, threads=4, n=200):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    s = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    x = np.random.rand(1, 3, size, size).astype(np.float32)
    name = s.get_inputs()[0].name
    ts = []
    for k in range(n + 20):
        t = time.perf_counter()
        s.run(None, {name: x})
        if k >= 20:
            ts.append((time.perf_counter() - t) * 1000)
    return round(float(np.median(ts)), 2)


def int8(fp32_dir, size, calib_dir, method="kl", n=600):
    """ncnnoptimize -> ncnn2table (calibration crops, same /255 RGB input as Ultralytics) ->
    ncnn2int8, with the official ncnn tools (as in scripts/quantize_int8.py)."""
    import random
    import subprocess

    src = Path(fp32_dir)
    out = src.parent / (src.name.replace("_ncnn_model", "") + f"_int8{method}_ncnn_model")
    work = out.parent / (out.name + "_work")
    work.mkdir(parents=True, exist_ok=True)
    files = sorted(str(p) for p in Path(calib_dir).rglob("*.jpg"))
    random.Random(0).shuffle(files)
    (work / "calib.txt").write_text("\n".join(files[:n]) + "\n", encoding="utf8")
    subprocess.run([str(TOOLS / "ncnnoptimize.exe"), str(src / "model.ncnn.param"),
                    str(src / "model.ncnn.bin"), str(work / "opt.param"), str(work / "opt.bin"),
                    "0"], check=True, capture_output=True)
    subprocess.run([str(TOOLS / "ncnn2table.exe"), str(work / "opt.param"), str(work / "opt.bin"),
                    str(work / "calib.txt"), str(work / "t.table"), "mean=[0,0,0]",
                    "norm=[0.003922,0.003922,0.003922]", f"shape=[{size},{size},3]",
                    "pixel=RGB", "thread=8", f"method={method}"], check=True, capture_output=True)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(TOOLS / "ncnn2int8.exe"), str(work / "opt.param"), str(work / "opt.bin"),
                    str(out / "model.ncnn.param"), str(out / "model.ncnn.bin"),
                    str(work / "t.table")], check=True, capture_output=True)
    shutil.copy(src / "metadata.yaml", out / "metadata.yaml")
    shutil.rmtree(work, ignore_errors=True)
    return str(out)


def export(w, size, calib):
    from ultralytics import YOLO

    out = {}
    out["onnx"] = YOLO(str(w)).export(format="onnx", imgsz=size, simplify=True)
    out["ncnn_fp32"] = YOLO(str(w)).export(format="ncnn", imgsz=size, half=False)
    for method in ("kl", "aciq"):
        try:
            out[f"ncnn_int8{method}"] = int8(out["ncnn_fp32"], size, calib, method)
        except Exception as e:  # noqa: BLE001
            out[f"ncnn_int8{method}_error"] = repr(e)[:300]
    return out


def frame_acc(weights, ds_rows, col, names, size, labels):
    from evaluate import predict

    p = predict(weights, [str(A / "data" / r[col]) for r in ds_rows], names, size)
    return round(float(np.mean(p.argmax(1) == labels)), 4)


def main():
    from alerts import CLASSES
    from evaluate import rows

    act_w, phone_w = Path(sys.argv[1]), Path(sys.argv[2])
    res = {"pi_reference_ms": {"det_v2d_int8_512": PI_DET_MS, "face_mesh": PI_FACE_MS}}
    ex_a = export(act_w, 224, str(A / "data" / "cls" / "train"))
    ex_p = export(phone_w, 128, str(A / "data" / "phone" / "train"))
    res["exports"] = {"action": {k: str(v) for k, v in ex_a.items()},
                      "phone": {k: str(v) for k, v in ex_p.items()}}
    # accuracy per format (SynDD test, a 3000-frame sample to keep it quick)
    rs = rows("syndd", "test")
    rng = np.random.default_rng(0)
    rs = [rs[i] for i in sorted(rng.choice(len(rs), min(3000, len(rs)), replace=False))]
    lab = np.array([CLASSES.index(r["cls"]) for r in rs])
    acc = {"pt": frame_acc(act_w, rs, "up", CLASSES, 224, lab)}
    for k, v in ex_a.items():
        if not k.endswith("error"):
            try:
                acc[k] = frame_acc(v, rs, "up", CLASSES, 224, lab)
            except Exception as e:  # noqa: BLE001
                acc[k] = repr(e)[:200]
    res["action_frame_acc_syndd_test_sample"] = acc
    # timings, 4 threads and 1 thread
    t = {"det_v2d_int8_ncnn_512": {th: ncnn_time(DET_NCNN, 512, th) for th in (1, 4)}}
    for nm, ex, sz in (("action", ex_a, 224), ("phone", ex_p, 128)):
        for k, v in ex.items():
            if k.endswith("error"):
                continue
            f = onnx_time if k == "onnx" else ncnn_time
            try:
                t[f"{nm}_{k}_{sz}"] = {th: f(v, sz, th) for th in (1, 4)}
            except Exception as e:  # noqa: BLE001
                t[f"{nm}_{k}_{sz}"] = repr(e)[:200]
    res["pc_cpu_ms_median"] = t
    det4 = t["det_v2d_int8_ncnn_512"][4]
    est = {}
    for k, v in t.items():
        if isinstance(v, dict) and k.startswith(("action_ncnn", "phone_ncnn")):
            est[k] = round(PI_DET_MS * v[4] / det4, 1)
    res["pi5_est_ms"] = est
    res["note"] = ("Pi estimate = 45 ms x (PC time / det_v2d PC time), same runtime and threads. "
                   "Pipeline per frame = face mesh + action classifier + 2 ear crops (phone "
                   "classifier); the phone classifier only needs to run when the action "
                   "classifier says call.")
    (A / "runs" / "bench.json").write_text(json.dumps(res, indent=1), encoding="utf8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
