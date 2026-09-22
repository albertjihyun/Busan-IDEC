"""보드 ADC(MCP3421, 240 SPS 에서 12비트, ±2047 코드) 눈금에서 봉우리 검출이 버티는 진폭 하한.

    python scripts/quant_test.py            # 50명, 진폭 7단계
    python scripts/quant_test.py 02 05      # 일부

1단계와 같은 파형(MPD-DF 심전도에 AFE 대역 흉내, 240 Hz)을 쓰되, 봉우리 진폭(99퍼센타일)이 A 코드가 되도록
크기를 맞춘 뒤 정수로 반올림하고 ±2047 로 자른다. A 를 바꿔 가며 놓침·오검출을 잰다(정답은 data/interim/rr 의 gt).
검출기는 상대 문턱이라 이론상 크기에 무관하지만, 정수 반올림과 level >> 3 이 작은 숫자에서 뭉개지는지 본다.
A=2000 은 포화 근처(ADC 상한 2047) 시험이다. 결과 data/processed/stage1/quant12.csv.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.mpd_io import load_ecg_as_ppg_chain, subject_ids  # noqa: E402
from src.peak_simple import detect, FS  # noqa: E402
from src.peak_eval import summarize  # noqa: E402

RR_DIR = ROOT / "data" / "interim" / "rr"
OUT = ROOT / "data" / "processed" / "stage1" / "quant12.csv"
AMPS = (10, 15, 25, 50, 100, 200, 500, 1000, 2000)
ADC_MAX = 2047


def main(argv):
    sids = argv or subject_ids()
    rows = []
    t0 = time.time()
    for sid in sids:
        x = load_ecg_as_ppg_chain(sid, FS)
        gt = np.load(RR_DIR / f"{sid}.npz")["gt"]
        p99 = np.percentile(x, 99)
        for a in AMPS:
            codes = np.clip(np.round(x * (a / p99)), -ADC_MAX - 1, ADC_MAX).astype(np.int64)
            peaks, rr, ok = detect(codes)
            s = summarize(peaks, rr, ok, gt)
            rows.append(dict(sid=sid, amp=a, **s))
        print(f"{sid} {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, float_format="%.4g")
    g = df.groupby("amp")
    pooled = pd.DataFrame({
        "놓침%": 100 * g.miss.sum() / g.n_gt.sum(),
        "오검출%": 100 * g.fp.sum() / g.n_det.sum(),
        "놓침% 중앙값": g.miss_pct.median(),
        "놓침% 최악": g.miss_pct.max(),
        "오검출% 최악": g.fp_pct.max(),
        "SQI유효%": g.sqi_ok_pct.mean(),
    })
    print(pooled.round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
