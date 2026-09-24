"""배포용 실수 문턱 T 를 50명 전체 표에서 다시 잡는다.

    .venv/Scripts/python.exe scripts/calib_t_float.py

features_60s.csv 의 mean_rb_chip(칩 방식 기준선)에 src.stage3.scoring.sweep + pick_thresholds 를
한 번 적용해 헛경보 4회/h·2회/h 문턱을 낸다. 학습=시험이라 검증값이 아니고 배포 상수용이다.
결과 T 를 make_infer_vectors.py 의 T_FLOAT_4 / T_FLOAT_2 에 옮긴 뒤 --calib 로 T_FIX 를 잡는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.stage3.data import load_table  # noqa: E402
from src.stage3.scoring import sweep, pick_thresholds  # noqa: E402


def main():
    df = load_table(60, chip_baseline=True)
    curve = sweep(df, "mean_rb", n_grid=2000)
    th = pick_thresholds(curve, [4.0, 2.0])
    print(f"유효 행 {int((df.valid == 1).sum())} / 전체 {len(df)}, 피험자 {df.sid.nunique()}")
    for cap in (4.0, 2.0):
        t = th[cap]
        r = curve[curve.threshold == t].iloc[0]
        print(f"헛경보 {cap:.0f}회/h: T = {t:.16g}  실측 {r.fa_per_hour:.2f}/h  사건 {r.event_sens:.3f}  창 {r.win_sens:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
