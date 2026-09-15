"""1단계. MPD-DF 50명 ECG → 240 Hz → 단순 규칙 봉우리 → RR 배열.

정답은 1024 Hz 원본에서 neurokit2로 뽑아 240 Hz 인덱스로 환산한다.
사람마다 data/interim/rr/{sid}.npz 에 저장:
  peaks   단순 규칙 봉우리 인덱스 (240 Hz)
  rr      봉우리 간격 (샘플 수). peaks[1:] - peaks[:-1]
  ok      SQI 통과 여부
  gt      정답 봉우리 인덱스 (240 Hz)
  labels  30초 에폭 라벨 (int, 아티팩트는 -1)

    python scripts/extract_rr.py            # 전원
    python scripts/extract_rr.py 02 05      # 일부
"""

import sys
import time
from pathlib import Path

import numpy as np
import neurokit2 as nk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mpd_io import load_ecg, load_labels, load_ecg_as_ppg_chain, subject_ids, EPOCH_SEC  # noqa: E402
from src.peak_simple import detect, FS  # noqa: E402
from src.peak_eval import summarize  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "interim" / "rr"


def reference_peaks(x1k, fs):
    """정답. neurokit 기본 방법이 일부 파일에서 봉우리를 수십 개만 내놓는 식으로 깨지므로
    (20·21·24·42번), 개수가 2시간치로 말이 안 되면 elgendi2010으로 대체한다."""
    _, info = nk.ecg_peaks(x1k, sampling_rate=fs)
    pk = info["ECG_R_Peaks"]
    expected = len(x1k) / fs / 60 * 40          # 분당 40회를 하한으로
    method = "neurokit"
    if len(pk) < expected:
        _, info = nk.ecg_peaks(x1k, sampling_rate=fs, method="elgendi2010")
        pk = info["ECG_R_Peaks"]; method = "elgendi2010"
    return pk, method


def run(sid):
    x1k, fs = load_ecg(sid)
    gt1k, method = reference_peaks(x1k, fs)
    gt = np.round(gt1k * FS / fs).astype(int)
    x = load_ecg_as_ppg_chain(sid, FS)          # AFE 대역(0.16~16 Hz) 흉내 후 240 Hz
    peaks, rr, ok = detect(x)
    n_epochs = len(x) // (FS * EPOCH_SEC)
    labels = np.array([-1 if l is None else l for l in load_labels(sid, n_epochs)], dtype=np.int8)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez(OUT / f"{sid}.npz", peaks=peaks, rr=rr, ok=ok, gt=gt, labels=labels)
    s = summarize(peaks, rr, ok, gt); s["ref"] = method
    return s


def main(argv):
    sids = argv or subject_ids()
    rows = []
    t0 = time.time()
    print(f"{'sid':>4} {'정답':>6} {'검출':>6} {'놓침%':>6} {'오검출%':>7} {'SQI%':>6}  정답방법")
    for sid in sids:
        s = run(sid)
        rows.append((sid, s))
        print(f"{sid:>4} {s['n_gt']:6d} {s['n_det']:6d} {s['miss_pct']:6.2f} {s['fp_pct']:7.2f} {s['sqi_ok_pct']:6.1f}  {s['ref']}")
    miss = np.array([s["miss_pct"] for _, s in rows]); fp = np.array([s["fp_pct"] for _, s in rows])
    sqi = np.array([s["sqi_ok_pct"] for _, s in rows])
    tot_gt = sum(s["n_gt"] for _, s in rows); tot_miss = sum(s["miss"] for _, s in rows)
    tot_det = sum(s["n_det"] for _, s in rows); tot_fp = sum(s["fp"] for _, s in rows)
    print(f"\n{len(rows)}명 {time.time() - t0:.0f}s")
    print(f"pooled 놓침 {100 * tot_miss / tot_gt:.2f}%  오검출 {100 * tot_fp / tot_det:.2f}%")
    print(f"사람별 놓침 중앙값 {np.median(miss):.2f}% 최대 {miss.max():.2f}% ({rows[miss.argmax()][0]}번)")
    print(f"사람별 오검출 중앙값 {np.median(fp):.2f}% 최대 {fp.max():.2f}% ({rows[fp.argmax()][0]}번)")
    print(f"SQI 유효 중앙값 {np.median(sqi):.1f}% 최소 {sqi.min():.1f}% ({rows[sqi.argmin()][0]}번)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
