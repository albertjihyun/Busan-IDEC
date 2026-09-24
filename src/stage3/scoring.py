"""사건 단위 채점. 모든 정의는 이 파일 한 곳에만 둔다.

용어
- 사건: 한 피험자 안에서 y==1 에폭이 연속된 구간 [s, e] (에폭 번호, 양끝 포함). 전체 행(무효 포함)으로 정의.
- 판정 가능 사건: 사건 에폭 중 valid==1이 하나라도 있는 것.
- 경보 덩어리: 경보가 켜진 유효 에폭들을, 사이에 경보 없는 에폭이 2개 이하(간격 90초 미만)면 하나로 합친 것.
- 검출: 판정 가능 사건이 경보 덩어리와 하나라도 겹침.
- 경보 덩어리는 5분(10에폭)을 넘으면 5분 단위로 쪼갠다(SzCORE 규칙). 안 쪼개면 "항상 켜짐"이 헛경보 0이 되는 빈틈이 생긴다.
- 헛경보: 어떤 사건과도 겹치지 않는 경보 덩어리.
- 헛경보/시간: 헛경보 수 / (유효 각성 에폭 수 * 30초 / 3600).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .data import EPOCH_SEC

MERGE_GAP = 2      # 경보 없는 에폭 이 개수 이하면 같은 덩어리
MAX_CLUSTER = 10   # 덩어리 최대 길이(에폭). 넘으면 이 길이로 쪼갠다


@dataclass
class SubjectCounts:
    sid: int
    n_events: int          # 판정 가능 사건 수
    n_unjudgeable: int     # 유효 에폭이 없는 사건 수
    detected: int
    false_alarms: int
    alert_hours: float     # 유효 각성 시간
    n_valid: int
    n_pos: int             # 유효 양성 에폭
    n_neg: int
    win_tp: int
    win_fp: int
    win_fn: int
    win_tn: int


def events_of(y: np.ndarray, valid: np.ndarray) -> list[tuple[int, int, bool]]:
    """(시작 idx, 끝 idx, 판정 가능 여부). 배열은 에폭 순, 연속(에폭 번호 0..n-1)이어야 한다."""
    out = []
    n = len(y)
    i = 0
    while i < n:
        if y[i] == 1:
            j = i
            while j + 1 < n and y[j + 1] == 1:
                j += 1
            out.append((i, j, bool(valid[i:j + 1].any())))
            i = j + 1
        else:
            i += 1
    return out


def alarm_clusters(alarm: np.ndarray) -> list[tuple[int, int]]:
    """경보 불리언 배열(에폭 순) → 덩어리 [(s, e)]."""
    idx = np.flatnonzero(alarm)
    if len(idx) == 0:
        return []
    out = []
    s = p = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - p <= MERGE_GAP + 1:
            p = i
        else:
            out.append((s, p))
            s = p = i
    out.append((s, p))
    split = []
    for s, e in out:
        while e - s + 1 > MAX_CLUSTER:
            split.append((s, s + MAX_CLUSTER - 1))
            s += MAX_CLUSTER
        split.append((s, e))
    return split


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def score_subject(sid: int, y: np.ndarray, valid: np.ndarray, alarm: np.ndarray) -> SubjectCounts:
    """한 피험자의 전체 에폭 열(무효 포함)에 대해 센다. alarm은 무효 에폭에서 반드시 False."""
    alarm = np.asarray(alarm, bool) & (valid == 1)
    evs = events_of(y, valid)
    cls = alarm_clusters(alarm)
    judge = [(s, e) for s, e, ok in evs if ok]
    all_ev = [(s, e) for s, e, _ in evs]
    detected = sum(any(_overlap(ev, c) for c in cls) for ev in judge)
    fa = sum(not any(_overlap(c, ev) for ev in all_ev) for c in cls)
    v = valid == 1
    pos = v & (y == 1)
    neg = v & (y == 0)
    return SubjectCounts(
        sid=int(sid),
        n_events=len(judge),
        n_unjudgeable=len(evs) - len(judge),
        detected=int(detected),
        false_alarms=int(fa),
        alert_hours=float(neg.sum() * EPOCH_SEC / 3600.0),
        n_valid=int(v.sum()),
        n_pos=int(pos.sum()),
        n_neg=int(neg.sum()),
        win_tp=int((pos & alarm).sum()),
        win_fp=int((neg & alarm).sum()),
        win_fn=int((pos & ~alarm).sum()),
        win_tn=int((neg & ~alarm).sum()),
    )


def score_table(df: pd.DataFrame, alarm_col: str) -> list[SubjectCounts]:
    """df: sid, epoch, y, valid, <alarm_col>. 피험자별로 센다."""
    out = []
    for sid, g in df.groupby("sid", sort=True):
        g = g.sort_values("epoch")
        assert (np.diff(g.epoch.values) == 1).all(), f"sid {sid} 에폭 불연속"
        out.append(score_subject(sid, g.y.values, g.valid.values, np.where(g[alarm_col].isna(), False, g[alarm_col]).astype(bool)))
    return out


def pooled(counts: list[SubjectCounts]) -> dict:
    """전 피험자 합산 후 한 번 계산(pooled)."""
    ev = sum(c.n_events for c in counts)
    det = sum(c.detected for c in counts)
    fa = sum(c.false_alarms for c in counts)
    hrs = sum(c.alert_hours for c in counts)
    tp = sum(c.win_tp for c in counts); fp = sum(c.win_fp for c in counts)
    fn = sum(c.win_fn for c in counts); tn = sum(c.win_tn for c in counts)
    return {
        "n_events": ev,
        "n_unjudgeable": sum(c.n_unjudgeable for c in counts),
        "detected": det,
        "event_sens": det / ev if ev else float("nan"),
        "false_alarms": fa,
        "alert_hours": hrs,
        "fa_per_hour": fa / hrs if hrs else float("nan"),
        "win_sens": tp / (tp + fn) if tp + fn else float("nan"),
        "win_spec": tn / (tn + fp) if tn + fp else float("nan"),
        "win_acc": (tp + tn) / (tp + tn + fp + fn) if tp + tn + fp + fn else float("nan"),
    }


def bootstrap_ci(counts: list[SubjectCounts], n_boot: int = 1000, seed: int = 0) -> dict:
    """피험자 단위 부트스트랩(복원추출)으로 사건 민감도·헛경보/시간의 95% 구간."""
    rng = np.random.default_rng(seed)
    ev = np.array([c.n_events for c in counts]); det = np.array([c.detected for c in counts])
    fa = np.array([c.false_alarms for c in counts]); hrs = np.array([c.alert_hours for c in counts])
    n = len(counts)
    sens, fah = [], []
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        e = ev[i].sum(); h = hrs[i].sum()
        sens.append(det[i].sum() / e if e else np.nan)
        fah.append(fa[i].sum() / h if h else np.nan)
    return {
        "event_sens_ci": [float(np.nanpercentile(sens, 2.5)), float(np.nanpercentile(sens, 97.5))],
        "fa_per_hour_ci": [float(np.nanpercentile(fah, 2.5)), float(np.nanpercentile(fah, 97.5))],
    }


def subject_auc(df: pd.DataFrame, score_col: str) -> pd.Series:
    """유효 행에서 피험자별 창 AUC. 양성·음성이 둘 다 있는 사람만."""
    out = {}
    v = df[df.valid == 1]
    for sid, g in v.groupby("sid"):
        if g.y.nunique() == 2:
            out[sid] = roc_auc_score(g.y, g[score_col])
    return pd.Series(out, name="win_auc")


def sweep(df: pd.DataFrame, score_col: str, n_grid: int = 200) -> pd.DataFrame:
    """문턱을 훑어 (threshold, fa_per_hour, event_sens, win_sens, win_spec)를 만든다. FROC 곡선과 문턱 선택에 공용.

    df: 전체 행(무효 포함). score는 유효 행에만 있어야 하며 무효 행은 NaN.
    """
    v = df.loc[df.valid == 1, score_col].values
    qs = np.unique(np.quantile(v, np.linspace(0, 1, n_grid)))
    ths = np.concatenate([qs, [np.inf]])
    rows = []
    for t in ths:
        alarm = (df[score_col] >= t) & (df.valid == 1)
        tmp = df[["sid", "epoch", "y", "valid"]].copy()
        tmp["alarm"] = alarm.values
        p = pooled(score_table(tmp, "alarm"))
        rows.append({"threshold": float(t), **p})
    return pd.DataFrame(rows)


def pick_thresholds(curve: pd.DataFrame, caps: list[float]) -> dict[float, float]:
    """헛경보/시간 <= cap을 지키는 문턱 중 사건 민감도 최대. 동률이면 문턱이 높은(헛경보 적은) 쪽."""
    out = {}
    for cap in caps:
        ok = curve[curve.fa_per_hour <= cap]
        if ok.empty:
            out[cap] = float("inf")
            continue
        best = ok.event_sens.max()
        cand = ok[ok.event_sens == best]
        out[cap] = float(cand.threshold.max())
    return out
