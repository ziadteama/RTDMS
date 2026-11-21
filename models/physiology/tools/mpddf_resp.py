"""MPD-DF breathing features: breaths/min and breath-interval CV per 60 s window, from the PSG
thoracic channel ("Thor", 32 Hz), aligned to data/mpddf_windows.csv. Exploratory: written
2026-11-20, features extracted, NOT yet evaluated (run stopped). See docs/MPDDF.md.

    cd models/physiology && python tools/mpddf_resp.py   # -> data/mpddf_resp.csv

Dataset prep only; nothing here enters the runtime path.
"""

from concurrent.futures import ProcessPoolExecutor

import mne
import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfiltfilt


def resp(sid: int) -> list[tuple[int, int, int, float]]:
    r = mne.io.read_raw_edf(f"data/mpddf/MPDDF_raw_{sid:02d}_PSG.edf", include=["Thor"],
                            preload=True, verbose=False)
    fs = r.info["sfreq"]
    x = sosfiltfilt(butter(2, [0.08, 0.8], "band", fs=fs, output="sos"), r.get_data()[0])
    pk, _ = find_peaks(x, distance=int(fs * 1.5), prominence=np.std(x) * 0.3)
    tpk = pk / fs
    w = pd.read_csv("data/mpddf_windows.csv", usecols=["subject", "t_s"])
    out = []
    for t in w[w.subject == sid].t_s:
        b = tpk[(tpk > t - 60) & (tpk <= t)]
        ib = np.diff(b)
        out.append((sid, int(t), len(b), float(np.std(ib) / np.mean(ib)) if len(ib) > 2 else np.nan))
    return out


if __name__ == "__main__":
    ids = sorted(pd.read_csv("data/mpddf_windows.csv", usecols=["subject"]).subject.unique())
    with ProcessPoolExecutor(8) as ex:
        rows = [row for res in ex.map(resp, ids) for row in res]
    pd.DataFrame(rows, columns=["subject", "t_s", "resp_rate_bpm", "resp_cv"]).to_csv(
        "data/mpddf_resp.csv", index=False)
    print("ok", len(rows))
