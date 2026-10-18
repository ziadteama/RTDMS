#!/usr/bin/env python3
"""INT8 NCNN model for the Pi: ACIQ calibration on infrared frames, with the first layer and the
detection head kept in FP32 (mixed precision). Plain INT8 (KL, every layer) lost too much phone
recall (0.63 -> 0.39); this recipe matches FP32 (phone AP50 0.772 vs 0.771) and is ~20 % faster.

    python scripts/quantize_int8.py --tools <folder with ncnnoptimize / ncnn2table / ncnn2int8> \
        --images "<data root>/det_v2/syndd/images/train/*.jpg" --n 1000

Tools: the official ncnn release (github.com/Tencent/ncnn/releases, e.g.
ncnn-20260526-windows-vs2022.zip -> x64/bin, or the ubuntu / macos zips). Calibration images are
letterboxed to the model size (gray, pad 114) exactly like detector.py does at run time.
Output: models/<name>_det_aciq_mixed_ncnn_model (param / bin / metadata.yaml).
"""

from __future__ import annotations

import argparse
import glob
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rtdms_distraction.detector import letterbox  # noqa: E402

# Layers kept in FP32 for det_v2d (YOLO26n @512 NCNN export): the stem conv and the whole
# detection head. Names are the ncnnoptimize'd graph's.
DEFAULT_FP32 = ["conv_0"] + [f"conv_{i}" for i in range(71, 94)] + \
    [f"convdw_{i}" for i in range(211, 218)]


def tool(tools: Path | None, name: str) -> str:
    for cand in ([tools / name, tools / f"{name}.exe"] if tools else []):
        if cand.is_file():
            return str(cand)
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} not found (pass --tools <ncnn bin folder>)")
    return found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model", default=str(ROOT / "models" / "det_v2d_ir_512_ncnn_model"))
    p.add_argument("--imgsz", type=int, default=512)
    p.add_argument("--images", help="glob of training frames to calibrate on (IR / gray)")
    p.add_argument("--calib-dir", help="folder of ready letterboxed calibration images instead")
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--tools", type=Path, help="folder with the ncnn command-line tools")
    p.add_argument("--fp32-layers", default=",".join(DEFAULT_FP32))
    p.add_argument("--out", help="output folder (default models/<model>_det_aciq_mixed_ncnn_model)")
    a = p.parse_args()

    src = Path(a.model)
    out = Path(a.out) if a.out else src.with_name(
        src.name.removesuffix("_ncnn_model") + "_det_aciq_mixed_ncnn_model")
    work = Path(tempfile.mkdtemp(prefix="int8_"))
    # 1. calibration images, letterboxed like the run-time detector
    if a.calib_dir:
        files = sorted(str(f) for f in Path(a.calib_dir).glob("*.png"))
    else:
        if not a.images:
            raise SystemExit("pass --images <glob> or --calib-dir <folder>")
        pool = sorted(glob.glob(a.images))
        random.Random(0).shuffle(pool)
        (work / "calib").mkdir()
        files = []
        for k, f in enumerate(pool[: a.n]):
            g = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY)
            lb = letterbox(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), a.imgsz)[0]
            dst = work / "calib" / f"{k:04d}.png"
            cv2.imwrite(str(dst), lb)
            files.append(str(dst))
    (work / "calib.txt").write_text("\n".join(files) + "\n", encoding="utf8")
    print(f"{len(files)} calibration images", flush=True)

    # 2. optimise, 3. calibrate (ACIQ), 4. drop the FP32 layers from the table, 5. quantise
    subprocess.run([tool(a.tools, "ncnnoptimize"), str(src / "model.ncnn.param"),
                    str(src / "model.ncnn.bin"), str(work / "opt.param"), str(work / "opt.bin"),
                    "0"], check=True)
    s = a.imgsz
    subprocess.run([tool(a.tools, "ncnn2table"), str(work / "opt.param"), str(work / "opt.bin"),
                    str(work / "calib.txt"), str(work / "aciq.table"), "mean=[0,0,0]",
                    "norm=[0.003922,0.003922,0.003922]", f"shape=[{s},{s},3]", "pixel=RGB",
                    "thread=8", "method=aciq"], check=True)
    keep = set(filter(None, a.fp32_layers.split(",")))
    lines = (work / "aciq.table").read_text(encoding="utf8").splitlines()
    mixed = [ln for ln in lines if re.sub(r"_param_\d+$", "", ln.split()[0]) not in keep]
    (work / "mixed.table").write_text("\n".join(mixed) + "\n", encoding="utf8")
    print(f"table: {len(lines)} lines, {len(lines) - len(mixed)} removed (kept FP32)", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([tool(a.tools, "ncnn2int8"), str(work / "opt.param"), str(work / "opt.bin"),
                    str(out / "model.ncnn.param"), str(out / "model.ncnn.bin"),
                    str(work / "mixed.table")], check=True)
    shutil.copy(src / "metadata.yaml", out / "metadata.yaml")
    shutil.rmtree(work, ignore_errors=True)
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
