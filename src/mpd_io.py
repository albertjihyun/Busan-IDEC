"""MPD-DF 읽기. ECG 한 채널과 30초 에폭 라벨.

    from src.mpd_io import load_ecg, load_labels, resample_to
    x, fs = load_ecg("02")           # 1024 Hz float 배열
    x240 = resample_to(x, fs, 240)   # 보드 ADC 조건
"""

import csv
from pathlib import Path

import numpy as np
import pyedflib
from scipy.signal import resample_poly, butter, sosfiltfilt

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


# 보드 아날로그 프론트엔드를 ECG에 흉내 낸 대역.
# 실제 회로: AC 결합 C4 10µF + R7 100k → 0.16 Hz 고역통과. 출력 R15 100k + C2 100nF → 16 Hz 저역통과.
# FPGA 안 FIR은 노치만 넣으므로 여기서는 흉내 내지 않는다.
#
# 고역통과 0.16 Hz는 그대로 쓴다. DC 제거가 봉우리 검출의 전제라서다.
# 저역통과는 16이 아니라 40 Hz를 쓴다. 16 Hz는 PPG 봉우리(성분 10 Hz 이하)에는 여유롭지만
# ECG R파(성분 ~40 Hz)는 깎아 버린다. 16번 피험자는 R파가 작고 T파가 커서 16 Hz를 걸면 R이 T보다
# 낮아지고 검출기가 T파에 붙었다(놓침·오검출 53%). PPG에서는 안 생기는 ECG 고유 왜곡이므로,
# "봉우리 성분 대비 여유로운 차단"이라는 조건을 맞추려면 ECG에는 40 Hz가 맞다. 25 Hz만 돼도 해결된다.
AFE_HP_HZ = 0.16
AFE_LP_HZ = 40.0


def afe_filter(x, fs):
    """아날로그 프론트엔드 흉내(ECG용 대역). 1차 RC 두 개를 영위상으로 건다.

    실제 회로는 위상 지연이 있지만 봉우리 간격에는 영향이 없으므로 filtfilt로 충분하다.
    """
    sos_hp = butter(1, AFE_HP_HZ, btype="high", fs=fs, output="sos")
    sos_lp = butter(1, AFE_LP_HZ, btype="low", fs=fs, output="sos")
    return sosfiltfilt(sos_lp, sosfiltfilt(sos_hp, x))


def load_ecg_as_ppg_chain(sid, fs_out=240):
    """ECG를 하드웨어 팀 신호 체인 조건으로: AFE 대역 → 240 Hz. 봉우리 규칙 평가용."""
    x, fs = load_ecg(sid)
    return resample_to(afe_filter(x, fs), fs, fs_out)


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
