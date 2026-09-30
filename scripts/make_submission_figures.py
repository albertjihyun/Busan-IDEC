"""설계설명서 3.4 그림을 만든다.

    python scripts/make_submission_figures.py

docs/figures/ 에 PNG를 쓴다. 본문 폭(451 pt ≈ 6.27 in)에 맞춰 그리고, 글자는 실제 크기 7~8 pt다.
시스템 구조도(3.1_sys_architecture)는 docs/figures/src/ 의 SVG를 브라우저로 렌더링한 것이라
이 스크립트가 만들지 않는다.

  3.4.4_signal_models.png   (a) 사람별 졸음 효과와 각성 중 흔들림, (b) 모델별 헛경보 대 구간 민감도
  3.4.5_baseline_alert.png  (a) 기준선 완성과 판정 보류, (b) 심박 경보 간격
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
PROC = ROOT / "data" / "processed"

INK = "#0b0b0b"
INK2 = "#52514e"
MUTE = "#a3a29c"
GRID = "#e5e5e2"
BLUE = "#2a78d6"      # 참조 팔레트 슬롯 1
ORANGE = "#eb6834"    # 참조 팔레트 슬롯 2
BLUE_BG = "#eaf2fc"
ORANGE_BG = "#fdeee7"
GRAY_BG = "#f2f2f0"

W = 6.27  # 본문 폭, 인치

plt.rcParams.update({
    "font.family": "Malgun Gothic",
    "axes.unicode_minus": False,
    "font.size": 7.5,
    "axes.titlesize": 8,
    "axes.labelsize": 7.5,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "axes.edgecolor": INK2,
    "axes.linewidth": 0.6,
    "axes.labelcolor": INK,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.dpi": 300,
    "savefig.facecolor": "white",
})


def panel_title(ax, tag, text):
    ax.set_title(f"({tag}) {text}", loc="left", color=INK, pad=6)


def subject_effects(window=60):
    """사람별 졸음 효과(피로 창 중앙값 − 각성 창 중앙값)와 각성 중 흔들림(각성 창 표준편차)."""
    d = pd.read_csv(PROC / f"features_{window}s.csv")
    v = d[(d.valid == 1) & d.mean_rb.notna() & (d.label >= 0)]
    eff, sd = [], []
    for _, x in v.groupby("sid"):
        a = x.loc[x.label == 0, "mean_rb"]
        f = x.loc[x.label >= 1, "mean_rb"]
        if len(a) >= 2 and len(f) >= 1:
            eff.append(f.median() - a.median())
            sd.append(a.std())
    return np.array(eff) * 100, np.array(sd) * 100


def froc(model, window=60):
    c = pd.read_csv(PROC / "stage3" / f"{model}_{window}s" / "froc.csv")
    return c.sort_values("fa_per_hour")


def signal_models():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 2.55), gridspec_kw={"width_ratios": [1, 1.12], "wspace": 0.32})

    # (a) 사람별 효과를 크기순으로 세우고, 각성 중 흔들림 폭을 뒤에 깐다
    eff, sd = subject_effects()
    band = np.median(sd)
    order = np.sort(eff)
    x = np.arange(1, len(order) + 1)
    pos = order > 0
    a1.axhspan(-band, band, color=GRAY_BG, zorder=0)
    a1.axhline(0, color=INK2, lw=0.6, zorder=1)
    a1.bar(x[pos], order[pos], width=0.72, color=ORANGE, zorder=2, label=f"졸릴 때 간격 증가 ({pos.sum()}명)")
    a1.bar(x[~pos], order[~pos], width=0.72, color=MUTE, zorder=2, label=f"반대 방향 ({(~pos).sum()}명)")
    med = np.median(eff)
    a1.axhline(med, color=INK, lw=0.9, ls=(0, (3, 2)), zorder=3)
    a1.text(1, med + 0.25, f"중앙값 {med:+.1f}%", ha="left", va="bottom", color=INK, fontsize=7)
    a1.text(len(order) + 0.5, -band + 0.25, f"각성 중 흔들림 ±{band:.1f}%", ha="right", va="bottom",
            color=INK2, fontsize=7)
    a1.set_xlim(0, len(order) + 1)
    a1.set_ylim(-8, np.ceil(order.max() / 2) * 2 + 1)
    a1.set_xticks([])
    a1.set_xlabel("피험자 (효과 크기순)")
    a1.set_ylabel("평소 대비 심박 간격의 변화 (%)")
    a1.legend(loc="upper left", frameon=False, handlelength=1.0, handletextpad=0.4, borderaxespad=0.2)
    panel_title(a1, "a", f"사람별 졸음 효과 ({len(eff)}명)")

    # (b) 모델별 헛경보 대 구간 민감도
    others = [("rule", "규칙", (0, (1, 0))), ("dtree", "얕은 트리", (0, (4, 2))),
              ("rf", "랜덤포레스트", (0, (1.2, 1.6))), ("gboost", "부스팅", (0, (5, 1.5, 1, 1.5)))]
    c = froc("logreg")
    a2.plot(c.fa_per_hour, c.event_sens, color=BLUE, lw=1.8, label="로지스틱 (특징 1개)", zorder=3)
    for m, name, ls in others:
        c = froc(m)
        a2.plot(c.fa_per_hour, c.event_sens, color=MUTE, lw=0.9, ls=ls, label=name, zorder=2)
    for fa, val in ((2, 0.265), (4, 0.413)):
        a2.axvline(fa, color=GRID, lw=0.8, zorder=0)
        a2.plot(fa, val, "o", ms=4.5, color=BLUE, mec="white", mew=0.8, zorder=4)
        a2.text(fa - 0.12, val + 0.03, f"{val:.3f}", ha="right", va="bottom", color=INK, fontsize=7)
    a2.set_xlim(0, 8)
    a2.set_ylim(0, 0.8)
    a2.set_xticks(range(0, 9, 2))
    a2.set_yticks(np.arange(0, 0.81, 0.2))
    a2.grid(axis="y", color=GRID, lw=0.6)
    a2.set_axisbelow(True)
    a2.set_xlabel("각성 시간당 헛경보 (회)")
    a2.set_ylabel("구간 민감도")
    a2.legend(loc="upper left", frameon=False, handlelength=2.6, borderaxespad=0.2)
    panel_title(a2, "b", "모델별 성능 (50명 사람 단위 교차검증)")

    fig.savefig(OUT / "3.4.4_signal_models.png", bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return eff, band


def baseline_alert():
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(W, 2.9), gridspec_kw={"height_ratios": [1, 1], "hspace": 0.95})

    # (a) 기준선: 서로 안 겹치는 1분 창, 좋은 창 3개면 완성
    for k, good in enumerate([True, False, True, True]):
        a1.add_patch(Rectangle((k + 0.03, 0.15), 0.94, 0.5,
                               facecolor=BLUE_BG if good else "white",
                               edgecolor=BLUE if good else MUTE, lw=0.8,
                               hatch=None if good else "//////"))
        a1.text(k + 0.5, 0.4, "좋은 창: 더함" if good else "나쁜 창: 건너뜀", ha="center", va="center",
                fontsize=7, color=INK if good else INK2,
                bbox=None if good else dict(facecolor="white", edgecolor="none", pad=1))
    a1.add_patch(Rectangle((0.03, 0.85), 3.94, 0.4, facecolor=GRAY_BG, edgecolor="none"))
    a1.text(2, 1.05, "판정 보류", ha="center", va="center", fontsize=7, color=INK2)
    a1.add_patch(Rectangle((4.03, 0.85), 1.94, 0.4, facecolor=ORANGE_BG, edgecolor="none"))
    a1.text(5, 1.05, "5초마다 판정", ha="center", va="center", fontsize=7, color=INK)
    a1.plot([4, 4], [0.0, 1.3], color=INK, lw=0.9)
    a1.text(4.06, 0.4, "좋은 창 3개\n기준선 완성", ha="left", va="center", fontsize=7, color=INK)
    a1.set_xlim(0, 6)
    a1.set_ylim(0, 1.3)
    a1.set_yticks([])
    a1.spines["left"].set_visible(False)
    a1.set_xticks(range(7), [f"{m}분" for m in range(7)])
    a1.set_xticks(np.arange(0, 6.01, 1 / 12), minor=True)
    a1.tick_params(axis="x", which="minor", length=1.5, width=0.4, color=MUTE)
    panel_title(a1, "a", "기준선과 판정 보류 (작은 눈금: 5초 블록)")

    # (b) 경보 간격: 첫 졸림 판정에서 즉시, 이어지면 30초마다
    t = np.arange(0, 125, 5)
    drowsy = ((t >= 10) & (t <= 80)) | ((t >= 100) & (t <= 110))
    alerts, last = [], -1e9
    for ti, d in zip(t, drowsy):
        if d and ti - last >= 30:
            alerts.append(ti)
            last = ti
    yj, ya = 1.0, 0.25
    a2.scatter(t[drowsy], np.full(drowsy.sum(), yj), s=11, color=ORANGE, zorder=3, label="졸림 판정")
    a2.scatter(t[~drowsy], np.full((~drowsy).sum(), yj), s=11, facecolor="white", edgecolor=MUTE,
               linewidth=0.7, zorder=3, label="각성 판정")
    a2.vlines(alerts, ya - 0.12, ya + 0.12, color=INK, lw=1.6, zorder=3)
    a2.plot([], [], color=INK, lw=1.6, marker="|", ms=6, ls="none", label="경보")
    for x0, x1 in zip(alerts[:-1], alerts[1:]):
        a2.annotate("", (x0 + 1, 0.62), (x1 - 1, 0.62),
                    arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.6, shrinkA=0, shrinkB=0))
        a2.text((x0 + x1) / 2, 0.68, "30초", ha="center", va="bottom", fontsize=7, color=INK2)
    a2.set_xlim(-3, 123)
    a2.set_ylim(0, 1.3)
    a2.set_yticks([yj, ya], ["5초 판정", "경보"])
    a2.tick_params(axis="y", length=0)
    a2.spines["left"].set_visible(False)
    a2.set_xticks(range(0, 121, 20), [f"{s}초" for s in range(0, 121, 20)])
    a2.legend(loc="lower right", bbox_to_anchor=(1, 1.0), frameon=False, ncol=3,
              handletextpad=0.4, columnspacing=1.4, borderaxespad=0)
    panel_title(a2, "b", "심박 경보 간격")

    fig.savefig(OUT / "3.4.5_baseline_alert.png", bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


if __name__ == "__main__":
    eff, band = signal_models()
    baseline_alert()
    print(f"사람 {len(eff)}명, 효과 중앙값 {np.median(eff):+.2f}%, 흔들림 {band:.2f}%")
    print("docs/figures 에 2개 저장")
