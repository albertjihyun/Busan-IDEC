"""3단계 입력: 2단계 특징 표를 읽고 학습/채점용 배열을 만든다."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT_DIR = PROCESSED / "stage3"

# 특징 후보 14개. 순서 = 상관 정리 때 우선순위(앞이 살아남음).
FEATURES = [
    "mean_nn", "sdnn", "rmssd", "sdsd", "cvnn", "cvsd", "sd2", "sd12",   # 1차 8
    "mean_rb", "sdnn_rb", "rmssd_rb",                                    # 기준선 비 3
    "mean_dp", "sdnn_dp", "rmssd_dp",                                    # 직전 창 차 3
]

EPOCH_SEC = 30.0
CORR_LIMIT = 0.95


def load_table(win: int, chip_baseline: bool = False) -> pd.DataFrame:
    """창 길이(30/60)의 표 전체를 (sid, epoch) 순으로 읽는다. valid==0 행도 포함한다(사건 정의에 필요).

    chip_baseline=True 이면 mean_rb 를 칩 방식 기준선(첫 3분 ΣRR÷N)으로 만든 mean_rb_chip 으로 바꿔 넣는다.
    4단계 정수 구현과 표를 일치시키는 확인용. 나머지 열은 그대로.
    """
    df = pd.read_csv(PROCESSED / f"features_{win}s.csv")
    df = df.sort_values(["sid", "epoch"]).reset_index(drop=True)
    if chip_baseline:
        df["mean_rb"] = df["mean_rb_chip"]
    # 무효 행의 특징값은 학습에 안 쓰므로 NaN이어도 상관없다. valid==1 행은 NaN이 없어야 한다.
    v = df[df.valid == 1]
    assert not v[FEATURES].isna().any().any(), "valid 행에 NaN 특징"
    return df


def corr_prune(X: pd.DataFrame, feats: list[str], limit: float = CORR_LIMIT) -> list[str]:
    """|상관| >= limit인 쌍에서 우선순위(목록 순서)가 낮은 쪽을 뺀다. 학습 폴드 데이터로만 계산."""
    c = X[feats].corr().abs().values
    keep: list[str] = []
    for i, f in enumerate(feats):
        drop = any(c[i, feats.index(k)] >= limit for k in keep)
        if not drop:
            keep.append(f)
    return keep
