"""2단계. 특징 표를 모델에 넣기 전에 눈으로 확인.

  1. 계산 검증: 특징별 히스토그램 (각성 vs 피로), 30초·60초
  2. 집계표: 행 수, 무효 사유, 클래스 비율
  3. 방향 재현: 사람 안 짝 비교 (피험자마다 피로 중앙값 − 각성 중앙값), Wilcoxon 부호순위
  4. 상관 행렬: |r| ≥ 0.95 쌍 표시
  5. 정답 봉우리(gt) 표와의 차이 (둘 다 유효한 행만)

그림은 png 파일로, 표는 stdout에 마크다운으로.

    python scripts/plot_features.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.stats import wilcoxon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "processed"
FIG = ROOT / "docs" / "figures"
MS = 1000 / 240                                     # 샘플 → ms

C_AWAKE, C_FATIGUE = "#2a78d6", "#eb6834"          # 참조 팔레트 슬롯 1·2
PRIMARY = ["mean_nn", "sdnn", "rmssd", "sdsd", "cvnn", "cvsd", "sd2", "sd12", "median_nn"]
DERIVED = ["mean_rb", "sdnn_rb", "rmssd_rb", "mean_dp", "sdnn_dp", "rmssd_dp"]
COMPARE = ["mean_db", "sdnn_db", "rmssd_db"]
FEATS14 = PRIMARY[:8] + DERIVED
ALL = PRIMARY + DERIVED + COMPARE
IN_MS = {"mean_nn", "sdnn", "rmssd", "sdsd", "sd2", "median_nn",
         "mean_dp", "sdnn_dp", "rmssd_dp", "mean_db", "sdnn_db", "rmssd_db"}
LABEL = {
    "mean_nn": "mean NN", "sdnn": "SDNN", "rmssd": "RMSSD", "sdsd": "SDSD", "cvnn": "CVNN",
    "cvsd": "CVSD", "sd2": "SD2", "sd12": "SD1/SD2", "median_nn": "median NN (비교용)",
    "mean_rb": "mean / 기준선", "sdnn_rb": "SDNN / 기준선", "rmssd_rb": "RMSSD / 기준선",
    "mean_dp": "Δmean (30초 전 대비)", "sdnn_dp": "ΔSDNN (30초 전 대비)", "rmssd_dp": "ΔRMSSD (30초 전 대비)",
    "mean_db": "mean - 기준선 (비교용)", "sdnn_db": "SDNN - 기준선 (비교용)", "rmssd_db": "RMSSD - 기준선 (비교용)",
}

plt.rcParams.update({
    "font.family": ["Malgun Gothic", "DejaVu Sans"], "axes.unicode_minus": False,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e6e6e6", "grid.linewidth": 0.6,
    "axes.edgecolor": "#999999", "axes.labelcolor": "#333333", "xtick.color": "#555555",
    "ytick.color": "#555555", "font.size": 9,
})


def unit(f):
    return f"{LABEL[f]} [ms]" if f in IN_MS else LABEL[f]


def scale(df, f):
    return df[f] * MS if f in IN_MS else df[f]


def load(wlen, suffix=""):
    df = pd.read_csv(IN / f"features_{wlen}s{suffix}.csv", dtype={"sid": str})
    return df


# ---------- 1. 히스토그램 ----------

def fig_hist(df, wlen):
    v = df[df.valid == 1]
    fig, axes = plt.subplots(4, 5, figsize=(15, 10.5))
    for ax, f in zip(axes.flat, ALL):
        a, b = scale(v[v.y == 0], f).dropna(), scale(v[v.y == 1], f).dropna()
        lo, hi = np.percentile(pd.concat([a, b]), [0.5, 99.5])
        bins = np.linspace(lo, hi, 50)
        ax.hist(a, bins, density=True, histtype="step", lw=1.6, color=C_AWAKE, label="각성")
        ax.hist(b, bins, density=True, histtype="step", lw=1.6, color=C_FATIGUE, label="피로")
        ax.set_title(unit(f), fontsize=9)
        ax.set_yticks([])
    for ax in axes.flat[len(ALL):]:
        ax.axis("off")
    axes.flat[0].legend(frameon=False, loc="upper right")
    fig.suptitle(f"{wlen}초 창 · 유효 행 {len(v):,}개 (각성 {int((v.y == 0).sum()):,} / 피로 {int((v.y == 1).sum()):,}) · 전체 풀 분포", y=0.995)
    fig.tight_layout()
    fig.savefig(FIG / f"feat_hist_{wlen}s.png", dpi=130)
    plt.close(fig)


# ---------- 3. 사람 안 짝 비교 ----------

def paired(df):
    """피험자마다 피로 중앙값 − 각성 중앙값. 길이 단위 특징은 각성 중앙값 대비 %로도."""
    v = df[df.valid == 1]
    rows = []
    for sid, g in v.groupby("sid"):
        a, b = g[g.y == 0], g[g.y == 1]
        if len(a) < 5 or len(b) < 5:
            continue
        r = dict(sid=sid, n_awake=len(a), n_fatigue=len(b))
        for f in ALL:
            ma, mb = a[f].median(), b[f].median()
            r[f] = mb - ma
            r[f + "_pct"] = 100 * (mb - ma) / ma if (f in PRIMARY and ma > 0) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def _strip(ax, P, feats, xform, xlabel, title):
    for i, f in enumerate(feats):
        x = xform(P, f).dropna()
        y = np.full(len(x), i) + np.random.default_rng(i).uniform(-0.18, 0.18, len(x))
        ax.scatter(x, y, s=14, color=C_FATIGUE, alpha=0.55, edgecolor="white", lw=0.4)
        ax.plot([x.median()] * 2, [i - 0.3, i + 0.3], color="#222222", lw=2)
    ax.axvline(0, color="#999999", lw=1)
    ax.set_yticks(range(len(feats)), [LABEL[f] for f in feats])
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=10)
    allx = np.concatenate([xform(P, f).dropna().values for f in feats])
    lim = np.nanpercentile(np.abs(allx), 97)
    ax.set_xlim(-lim, lim)


def fig_paired(P, wlen):
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), gridspec_kw=dict(width_ratios=[1.2, 1, 1]))
    _strip(axes[0], P, PRIMARY, lambda P, f: P[f + "_pct"],
           "각성 중앙값 대비 %", "1차 특징: 사람 안에서 졸릴 때 얼마나 달라지나")
    _strip(axes[1], P, ["mean_rb", "sdnn_rb", "rmssd_rb"], lambda P, f: P[f] * 100,
           "비의 차이, %p", "기준선 대비 (비)")
    _strip(axes[2], P, ["mean_dp", "sdnn_dp", "rmssd_dp"] + COMPARE, lambda P, f: P[f] * MS,
           "ms", "30초 전 대비 (차), 기준선 대비 (차, 비교용)")
    fig.suptitle(f"{wlen}초 창 · 피험자 {len(P)}명 (각성·피로 각 5창 이상) · 점 = 피험자의 피로 중앙값 - 각성 중앙값, 막대 = 45명 중앙값", y=0.995)
    fig.tight_layout()
    fig.savefig(FIG / f"feat_paired_{wlen}s.png", dpi=130)
    plt.close(fig)


def table_paired(P):
    print("\n| 특징 | 중앙값 변화 | 증가한 사람 | Wilcoxon p |")
    print("|---|---|---|---|")
    for f in ALL:
        d = P[f].dropna()
        if len(d) < 6:
            continue
        p = wilcoxon(d).pvalue if (d != 0).any() else 1.0
        up = int((d > 0).sum())
        if f in PRIMARY:
            med = f"{P[f + '_pct'].median():+.1f}%"
        elif f in IN_MS:
            med = f"{d.median() * MS:+.2f} ms"
        else:
            med = f"{d.median():+.3f}"
        print(f"| {LABEL[f]} | {med} | {up}/{len(d)} | {p:.2g} |")


# ---------- 4. 상관 ----------

def fig_corr(df, wlen):
    v = df[df.valid == 1]
    cols = FEATS14 + ["median_nn"]
    C = v[cols].corr()
    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    im = ax.imshow(C.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), [LABEL[c] for c in cols], rotation=60, ha="right")
    ax.set_yticks(range(len(cols)), [LABEL[c] for c in cols])
    ax.grid(False)
    for i in range(len(cols)):
        for j in range(len(cols)):
            r = C.values[i, j]
            if abs(r) >= 0.5 and i != j:
                ax.text(j, i, f"{r:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(r) > 0.7 else "#222222")
    fig.colorbar(im, ax=ax, shrink=0.7, label="Pearson r (유효 행)")
    ax.set_title(f"{wlen}초 창 · 특징 상관")
    fig.tight_layout()
    fig.savefig(FIG / f"feat_corr_{wlen}s.png", dpi=130)
    plt.close(fig)
    pairs = [(cols[i], cols[j], C.values[i, j]) for i in range(len(cols)) for j in range(i + 1, len(cols))
             if abs(C.values[i, j]) >= 0.95]
    return sorted(pairs, key=lambda t: -abs(t[2]))


# ---------- 2·5. 표 ----------

def table_counts(df, wlen):
    lab = df[df.y >= 0]
    val = df[df.valid == 1]
    reasons = df[df.valid == 0].reason.value_counts()
    print(f"| {wlen}초 | {len(df):,} | {len(lab):,} | {int(df.judged.sum()):,} ({100 * df.judged.mean():.1f}%) | "
          f"{len(val):,} | {int((val.y == 0).sum()):,} : {int((val.y == 1).sum()):,} "
          f"({(val.y == 0).sum() / (val.y == 1).sum():.2f}:1) | "
          + ", ".join(f"{k} {int(n)}" for k, n in reasons.items()) + " |")


def table_gt(df, dg, wlen):
    m = df.merge(dg, on=["sid", "epoch"], suffixes=("", "_gt"))
    m = m[(m.valid == 1) & (m.valid_gt == 1)]
    print(f"\n{wlen}초 창, 둘 다 유효한 행 {len(m):,}개. |우리 − 정답| / 정답 의 중앙값과 95 분위:\n")
    print("| 특징 | 중앙값 | 95% |")
    print("|---|---|---|")
    for f in PRIMARY[:8]:
        rel = (m[f] - m[f + "_gt"]).abs() / m[f + "_gt"].abs().clip(lower=1e-9)
        print(f"| {LABEL[f]} | {100 * rel.median():.2f}% | {100 * rel.quantile(0.95):.1f}% |")
    same = (m.n == m.n_gt).mean()
    print(f"\n창의 유효 박동 수가 정답과 같은 행: {100 * same:.1f}%")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    dfs = {w: load(w) for w in (30, 60)}
    print("## 집계\n")
    print("| 창 | 행 | 라벨 있음 | 칩 판정 (커버리지) | 유효(학습·채점) | 각성 : 피로 | 무효 사유 |")
    print("|---|---|---|---|---|---|---|")
    for w, df in dfs.items():
        table_counts(df, w)
    for w, df in dfs.items():
        print(f"\nsd2 절단 행 ({w}초): {int(df.sd2_clipped.sum())} / 유효 {int(df.valid.sum())}"
              f"  base_ok=0: {sorted(df[df.base_ok == 0].sid.unique().tolist())}")

    for w, df in dfs.items():
        fig_hist(df, w)
        P = paired(df)
        fig_paired(P, w)
        print(f"\n## 사람 안 짝 비교 ({w}초, {len(P)}명)")
        table_paired(P)
        pairs = fig_corr(df, w)
        print(f"\n## |r| ≥ 0.95 쌍 ({w}초)\n")
        for a, b, r in pairs:
            print(f"- {LABEL[a]} – {LABEL[b]}: {r:.3f}")

    print("\n## 정답 봉우리(gt) 표와 비교")
    for w, df in dfs.items():
        p = IN / f"features_{w}s_gt.csv"
        if p.exists():
            table_gt(df, load(w, "_gt"), w)
    print(f"\n그림: {FIG.relative_to(ROOT)}/feat_{{hist,paired,corr}}_{{30,60}}s.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
