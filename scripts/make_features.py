"""2단계. data/interim/rr/*.npz → data/processed/features_{30,60}s.csv

규칙은 docs/feature-table-design.md. 요약:
  - 행 = 30초 에폭 하나. 정답 = 그 에폭 라벨 하나 (창 길이 무관)
  - 재료 5개는 src.window_acc.WindowAcc 로 5초 블록 누산 (회로와 같은 절차)
  - 1차 특징은 src.features.primary, median은 RR 배열에서 (비교용)
  - 기준선 = 첫 3분 창 특징값 평균 (라벨 무관). 첫 3분은 판정 보류
  - 직전 창 대비 = 30초 전 창과의 차
  - 무효: no_window(60초 표 에폭 0) > baseline(에폭 0~5) > low_n(N30<15, N60<30) > artifact(라벨 −1)

    python scripts/make_features.py            # 전원, 우리 봉우리
    python scripts/make_features.py --gt       # 정답 봉우리(neurokit)로 같은 표 → *_gt.csv (비교용)
    python scripts/make_features.py 02 05      # 일부
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.window_acc import WindowAcc, BLOCK, W30, W60  # noqa: E402
from src.features import primary, NAMES  # noqa: E402
from src.peak_simple import SQI  # noqa: E402

IN = ROOT / "data" / "interim" / "rr"
OUT = ROOT / "data" / "processed"

EPOCH_BLOCKS = 6                       # 30초 = 5초 블록 6개
BASELINE_EPOCHS = 6                    # 첫 3분
MIN_N = {30: 15, 60: 30}               # 유효 박동 하한
BASE_FEATS = ("mean_nn", "sdnn", "rmssd")
MATERIALS = ("n", "sum_rr", "sum_rr2", "sum_d", "sum_d2")


def load(sid, use_gt):
    z = np.load(IN / f"{sid}.npz")
    labels = z["labels"].astype(int)
    if use_gt:
        # 정답 봉우리에 우리 SQI만 적용. 봉우리 검출 오차의 영향을 보기 위한 비교용
        peaks = z["gt"]
        sqi = SQI()
        rr, ok = [], []
        for p in peaks:
            r, o = sqi.push(int(p))
            if r is not None:
                rr.append(r); ok.append(o)
        rr, ok = np.array(rr), np.array(ok, dtype=bool)
    else:
        peaks, rr, ok = z["peaks"], z["rr"], z["ok"]
    return peaks, rr, ok, labels


def windows(peaks, rr, ok, n_epochs):
    """에폭마다 (win30 재료, win60 재료 또는 None, 30초 RR 목록, 60초 RR 목록)."""
    nblk = n_epochs * EPOCH_BLOCKS
    blk = peaks[1:] // BLOCK                 # RR i 는 봉우리 i+1 의 것. 봉우리 위치 기준 블록
    per_blk = {}
    for b, r, o in zip(blk, rr, ok):
        if b < nblk:
            per_blk.setdefault(int(b), []).append((int(r), bool(o)))
    acc = WindowAcc()
    valid_rr_by_blk = {}
    out = []
    for b in range(nblk):
        rrs = per_blk.get(b, [])
        for r, o in rrs:
            acc.push_rr(r, o)
        valid_rr_by_blk[b] = [r for r, o in rrs if o]
        acc.sample = (b + 1) * BLOCK - 1
        acc.push_sample()
        if (b + 1) % EPOCH_BLOCKS == 0:
            rr30 = sum((valid_rr_by_blk[j] for j in range(b + 1 - W30, b + 1)), [])
            if b + 1 >= W60:
                w60 = dict(acc.win60)
                rr60 = sum((valid_rr_by_blk[j] for j in range(b + 1 - W60, b + 1)), [])
            else:
                w60, rr60 = None, []
            out.append((dict(acc.win30), w60, rr30, rr60))
    return out


def subject_rows(sid, wlen, wins, labels):
    rows = []
    for k, (w30, w60, rr30, rr60) in enumerate(wins):
        m, rrl = (w30, rr30) if wlen == 30 else (w60, rr60)
        label = int(labels[k])
        row = dict(sid=sid, epoch=k, t_end_s=(k + 1) * 30, label=label,
                   y=-1 if label < 0 else int(label >= 1),
                   in_baseline=int(k < BASELINE_EPOCHS))
        if m is None:
            row.update({c: 0 for c in MATERIALS}, **dict.fromkeys(NAMES, np.nan),
                       median_nn=np.nan, sd2_clipped=False, reason="no_window")
        else:
            f = primary(m)
            row.update({c: int(m[c]) for c in MATERIALS}, **f,
                       median_nn=float(np.median(rrl)) if rrl else np.nan)
            if k < BASELINE_EPOCHS:
                row["reason"] = "baseline"
            elif m["n"] < MIN_N[wlen]:
                row["reason"] = "low_n"
            elif label < 0:
                row["reason"] = "artifact"
            else:
                row["reason"] = "ok"
        rows.append(row)
    df = pd.DataFrame(rows)

    # 칩이 판정을 내는 행 (라벨과 무관) / 채점 가능한 행
    computed = ~df.reason.isin(["no_window"]) & (df.n >= MIN_N[wlen])
    df["judged"] = (computed & (df.epoch >= BASELINE_EPOCHS)).astype(int)
    df["valid"] = ((df.judged == 1) & (df.y >= 0)).astype(int)

    # 기준선: 첫 3분 창 중 특징이 계산된 것(N 충분)의 평균. 라벨은 보지 않는다
    bwin = df[(df.epoch < BASELINE_EPOCHS) & computed]
    n_possible = BASELINE_EPOCHS - (1 if wlen == 60 else 0)
    base_ok = len(bwin) * 2 >= n_possible
    base = {f: (bwin[f].mean() if base_ok else np.nan) for f in BASE_FEATS}
    if base_ok and any(not (base[f] > 0) for f in BASE_FEATS):
        base_ok = False
    df["base_ok"] = int(base_ok)
    for f in BASE_FEATS:
        short = f.split("_")[0]
        if base_ok:
            df[f"{short}_rb"] = df[f] / base[f]
            df[f"{short}_db"] = df[f] - base[f]
        else:
            df[f"{short}_rb"] = 1.0
            df[f"{short}_db"] = 0.0
        # 직전 창(30초 전) 대비. 직전 창이 계산되지 않았으면 0
        prev = df[f].shift(1)
        prev_ok = computed.shift(1, fill_value=False)
        df[f"{short}_dp"] = np.where(prev_ok & computed, df[f] - prev, 0.0)
    # 기준선 구간·계산 불가 행의 파생 열은 중립값
    neutral = ~computed
    for f in BASE_FEATS:
        short = f.split("_")[0]
        df.loc[neutral, [f"{short}_rb"]] = 1.0
        df.loc[neutral, [f"{short}_db", f"{short}_dp"]] = 0.0
    return df


COLS = (["sid", "epoch", "t_end_s", "label", "y", "valid", "judged", "reason", "in_baseline", "base_ok"]
        + list(MATERIALS) + list(NAMES) + ["median_nn", "sd2_clipped"]
        + [f"{s}_{k}" for k in ("rb", "db", "dp") for s in ("mean", "sdnn", "rmssd")])


def summarize(df, wlen):
    lab = df[df.y >= 0]
    val = df[df.valid == 1]
    print(f"\n[{wlen}초] 행 {len(df)}  라벨 있음 {len(lab)}  칩 판정 {df.judged.sum()} ({100 * df.judged.mean():.1f}%)"
          f"  유효(학습·채점) {len(val)} ({100 * len(val) / max(len(lab), 1):.1f}% of 라벨 있음)")
    print("  무효 사유:", dict(df[df.valid == 0].reason.value_counts()))
    print(f"  유효 행 각성:피로 = {(val.y == 0).sum()}:{(val.y == 1).sum()} ({(val.y == 0).sum() / max((val.y == 1).sum(), 1):.2f}:1)")
    print(f"  base_ok=0 피험자: {sorted(df[df.base_ok == 0].sid.unique().tolist())}")
    print(f"  sd2 절단 행: {int(df.sd2_clipped.sum())}")


def main(argv):
    use_gt = "--gt" in argv
    sids = [a for a in argv if not a.startswith("--")] or sorted(p.stem for p in IN.glob("*.npz"))
    t0 = time.time()
    tables = {30: [], 60: []}
    for sid in sids:
        peaks, rr, ok, labels = load(sid, use_gt)
        wins = windows(peaks, rr, ok, len(labels))
        for wlen in (30, 60):
            tables[wlen].append(subject_rows(sid, wlen, wins, labels))
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "_gt" if use_gt else ""
    for wlen in (30, 60):
        df = pd.concat(tables[wlen], ignore_index=True)[COLS]
        path = OUT / f"features_{wlen}s{suffix}.csv"
        df.to_csv(path, index=False, float_format="%.6g")
        summarize(df, wlen)
        print(f"  → {path.relative_to(ROOT)}")
    print(f"\n{len(sids)}명 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
