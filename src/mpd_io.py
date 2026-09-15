"""MPD-DF 읽기. ECG 한 채널과 30초 에폭 라벨.

    from src.mpd_io import load_ecg, load_labels, resample_to
    x, fs = load_ecg("02")           # 1024 Hz float 배열
    x240 = resample_to(x, fs, 240)   # 우리 ADC 조건
"""

import csv
from pathlib import Path

import numpy as np
import pyedflib
from scipy.signal import resample_poly

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "mpd_df"
EPOCH_SEC = 30
EXCLUDE = {"Severe Artifacts", "Signal Abnormality"}


def subject_ids():
    return sorted(p.name.split("_")[2] for p in RAW.glob("MPDDF_raw_*_PSG.edf"))


def load_ecg(sid):
    """ECG 채널을 float64로. 반환 (신호, 샘플링 주파수)."""
    f = pyedflib.EdfReader(str(RAW / f"MPDDF_raw_{sid}_PSG.edf"))
    try:
        labels = f.getSignalLabels()
        ch = labels.index("ECG")
        x = f.readSignal(ch).astype(np.float64)
        fs = int(round(f.getSampleFrequency(ch)))
    finally:
        f.close()
    return x, fs


def resample_to(x, fs_in, fs_out):
    """정수비 리샘플. 1024→240은 15/64."""
    from math import gcd
    g = gcd(fs_in, fs_out)
    return resample_poly(x, fs_out // g, fs_in // g)


def load_labels(sid, n_epochs=None):
    """에폭별 라벨 배열. int(0~4) 또는 None(아티팩트). 전이 목록을 펼친다."""
    rows = [r for r in csv.reader((RAW / f"MPDDF_raw_{sid}_Annotation.txt").open(encoding="utf-8")) if len(r) >= 3]
    marks = []
    for r in rows:
        v = r[2].strip()
        marks.append((int(r[1]), int(v) if v.isdigit() else None))
    if n_epochs is None:
        n_epochs = marks[-1][0] + 1
    out = [None] * (n_epochs + 1)
    for (start, lvl), (nxt, _) in zip(marks, marks[1:] + [(n_epochs + 1, None)]):
        for e in range(start, min(nxt, n_epochs + 1)):
            out[e] = lvl
    return out[1:]
