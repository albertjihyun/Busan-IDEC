"""1단계 RR 을 준용 v14 검출기 출력으로 바꾼다.

data/interim/rr_jy/{sid}.npz (scripts/compare_detectors.py --no-lpf --fix-prev 가 만든 것: peaks, rr_at, rr, ok, gt)
에 우리 표의 labels 를 붙여 data/interim/rr/{sid}.npz 형식(peaks, rr, ok, gt, labels; rr[i]는 peaks[i+1]의 것)으로
저장한다. 기존 우리 검출기 출력은 data/interim/rr_ours/ 로 옮겨 둔다.

    .venv/Scripts/python.exe scripts/adopt_jy_rr.py
"""

import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RR, JY, OURS = (ROOT / "data" / "interim" / d for d in ("rr", "rr_jy", "rr_ours"))


def main():
    if not OURS.exists():
        shutil.copytree(RR, OURS)
        print(f"우리 검출기 출력 백업 → {OURS}")
    n = 0
    for p in sorted(JY.glob("*.npz")):
        z = np.load(p)
        ours = np.load(OURS / p.name)
        peaks, rr_at, rr, ok = z["peaks"], z["rr_at"], z["rr"], z["ok"]
        # 준용 골든은 첫 봉우리 뒤의 모든 봉우리에서 RR 행을 내므로 rr_at == peaks[1:] 이어야 한다
        assert len(rr) == len(peaks) - 1 and np.array_equal(rr_at, peaks[1:]), p.name
        np.savez(RR / p.name, peaks=peaks, rr=rr, ok=ok, gt=z["gt"], labels=ours["labels"])
        n += 1
    print(f"{n}명 교체 → {RR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
