"""설계설명서 초안용 그림을 만든다. 숫자는 전부 docs/ 설계서에 적힌 값이다.

    python scripts/make_submission_figures.py

docs/figures/ 에 PNG를 쓴다. 구조도(sys_architecture, infer_top)는 같은 폴더의
SVG를 브라우저로 렌더링한 것이라 이 스크립트가 만들지 않는다.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"

INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e5e5e2"
MUTE = "#a3a29c"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"

plt.rcParams.update({
    "font.family": "Malgun Gothic",
    "axes.unicode_minus": False,
    "font.size": 10,
    "axes.edgecolor": INK2,
    "axes.labelcolor": INK,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def model_size():
    """모델 크기 대 사건 민감도 (LOSO, 60초 창, 헛경보 4회/h)."""
    rows = [  # 이름, 파라미터 바이트, 사건 민감도, 라벨 위치
        ("로지스틱 (특징 1개)", 2, 0.413, (8, 4)),
        ("규칙 (특징 1개)", 2, 0.361, (8, -12)),
        ("얕은 트리", 69, 0.313, (8, -4)),
        ("부스팅", 6975, 0.306, (8, -12)),
        ("랜덤포레스트", 44168, 0.340, (-8, 8)),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.axvline(4096, color=MUTE, lw=1, ls=(0, (4, 3)))
    ax.text(4096 * 1.08, 0.425, "파라미터 예산 4 KB", color=INK2, fontsize=9, va="top")
    for name, b, s, off in rows:
        hi = name.startswith("로지스틱")
        ax.scatter(b, s, s=70 if hi else 50, color=BLUE if hi else MUTE,
                   edgecolor="white", linewidth=1.5, zorder=3)
        ax.annotate(f"{name}  {s:.3f}", (b, s), xytext=off, textcoords="offset points",
                    ha="right" if off[0] < 0 else "left", va="center",
                    fontsize=9.5, color=INK, fontweight="bold" if hi else "normal")
    ax.set_xscale("log")
    ax.set_xlim(1, 2e5)
    ax.set_ylim(0.28, 0.44)
    ax.set_xlabel("칩에 올릴 파라미터 크기 (바이트, 로그 눈금)")
    ax.set_ylabel("사건 민감도")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title("처음 보는 사람에 대한 성능 (50명 LOSO, 60초 창, 헛경보 시간당 4회)",
                 fontsize=10, color=INK, loc="left")
    fig.savefig(OUT / "model_size.png")
    plt.close(fig)


def ppg_transfer():
    """이마 PPG와 흉골 ECG의 mean_rb 차이 (WildPPG 15명)."""
    labels = ["박동 수 조건만", "기준선 규칙만", "좋은 창 + 기준선 규칙"]
    sd = [7.4, 5.8, 1.7]
    fig, ax = plt.subplots(figsize=(6.4, 2.5))
    y = np.arange(len(labels))[::-1]
    colors = [MUTE, MUTE, BLUE]
    ax.barh(y, sd, height=0.55, color=colors, edgecolor="white", linewidth=2)
    for yi, v in zip(y, sd):
        ax.text(v + 0.12, yi, f"{v:.1f}%", va="center", fontsize=10, color=INK)
    ax.axvline(4.0, color=ORANGE, lw=1.5)
    ax.text(4.08, 2.42, "각성 중 사람 안 흔들림 4.0%", color=INK, fontsize=9, va="center")
    ax.axvline(1.3, color=INK2, lw=1, ls=(0, (3, 3)))
    ax.text(1.38, -0.55, "졸음 효과 1.3%", color=INK2, fontsize=9, va="center")
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 8.5)
    ax.set_ylim(-0.8, 2.7)
    ax.set_xlabel("PPG와 ECG의 mean_rb 차이, 표준편차 (%)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    fig.savefig(OUT / "ppg_transfer.png")
    plt.close(fig)


def timeline():
    """기준선 완성과 경보 간격을 시간축으로."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4.4), gridspec_kw={"height_ratios": [1, 1.15]})

    # 위: 기준선
    for k, good in enumerate([True, False, True, True]):
        a1.add_patch(Rectangle((k, 0.55), 0.96, 0.5, facecolor=("#EAF2FC" if good else "#F2F3F2"),
                               edgecolor=(BLUE if good else MUTE), lw=1.2,
                               hatch=None if good else "////"))
        a1.text(k + 0.48, 0.8, "좋은 창: 더함" if good else "나쁜 창: 건너뜀",
                ha="center", va="center", fontsize=9, color=INK)
    for b in range(0, 72):
        a1.plot([b / 12, b / 12], [0.42, 0.5], color=MUTE, lw=0.6)
    a1.text(0, 0.28, "5초 블록", fontsize=8.5, color=INK2)
    a1.add_patch(Rectangle((0, 1.25), 4, 0.3, facecolor="#F2F3F2", edgecolor=MUTE, lw=1))
    a1.text(2, 1.4, "보류 (기준선 준비 중)", ha="center", va="center", fontsize=9, color=INK2)
    a1.add_patch(Rectangle((4, 1.25), 2, 0.3, facecolor="#FDEEE7", edgecolor=ORANGE, lw=1))
    a1.text(5, 1.4, "5초마다 판정", ha="center", va="center", fontsize=9, color=INK)
    a1.annotate("좋은 창 3개 → 기준선 완성", (4, 1.05), xytext=(4.25, 0.25), fontsize=9, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=1))
    a1.set_xlim(0, 6)
    a1.set_ylim(0.1, 1.7)
    a1.set_yticks([])
    a1.spines["left"].set_visible(False)
    a1.set_xticks(range(7), [f"{m}분" for m in range(7)])
    a1.set_title("기준선: 서로 안 겹치는 1분 창 중 좋은 창 3개", fontsize=10, loc="left", color=INK)

    # 아래: 경보 간격
    t = np.arange(0, 125, 5)
    drowsy = ((t >= 10) & (t <= 80)) | ((t >= 100) & (t <= 110))
    alerts, last = [], -1e9
    for ti, d in zip(t, drowsy):
        if d and ti - last >= 30:
            alerts.append(ti)
            last = ti
    a2.scatter(t[drowsy], np.full(drowsy.sum(), 1.0), s=26, color=ORANGE, zorder=3, label="졸림 판정")
    a2.scatter(t[~drowsy], np.full((~drowsy).sum(), 1.0), s=26, facecolor="white", edgecolor=MUTE,
               zorder=3, label="각성 판정")
    for ai in alerts:
        a2.plot([ai, ai], [0.35, 0.8], color=INK, lw=2)
        a2.plot(ai, 0.8, marker="v", color=INK, ms=6)
    a2.text(0, 0.18, "경보", fontsize=9, color=INK)
    a2.text(0, 1.2, "5초 판정", fontsize=9, color=INK2)
    for x0, x1, txt in [(10, 40, "30초"), (40, 70, "30초"), (70, 100, "30초")]:
        a2.annotate("", (x0, 0.5), (x1, 0.5), arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.9))
        a2.text((x0 + x1) / 2, 0.56, txt, ha="center", fontsize=8.5, color=INK2)
    a2.text(100, 0.03, "끊겼다 다시 와도 마지막 경보부터 30초", fontsize=8.5, color=INK2,
            ha="center", va="bottom")
    a2.set_xlim(-2, 124)
    a2.set_ylim(0, 1.45)
    a2.set_yticks([])
    a2.spines["left"].set_visible(False)
    a2.set_xticks(range(0, 125, 20), [f"{s}초" for s in range(0, 125, 20)])
    a2.legend(loc="upper right", frameon=False, fontsize=8.5, ncol=2)
    a2.set_title("경보 간격: 첫 졸림 판정에서 즉시, 이어지면 30초마다", fontsize=10, loc="left", color=INK)
    fig.tight_layout(h_pad=1.6)
    fig.savefig(OUT / "baseline_alert_timeline.png")
    plt.close(fig)


def tilt_plane():
    """앞축·세로축 가속도 평면에서 숙임과 급제동."""
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    ax.add_patch(Rectangle((np.sin(np.radians(35)), -0.05), 1.2, np.cos(np.radians(35)) + 0.05,
                           facecolor="#FDEEE7", edgecolor=ORANGE, lw=1.2))
    ax.text(1.02, 0.08, "떨굼으로 판정\n앞축 ≥ sin35°\n|세로축| ≤ cos35°", fontsize=9, color=INK, va="bottom")
    th = np.radians(np.linspace(0, 70, 200))
    ax.plot(np.sin(th), np.cos(th), color=BLUE, lw=2)
    for d in (20, 35, 45, 60):
        r = np.radians(d)
        ax.plot(np.sin(r), np.cos(r), "o", color=BLUE, ms=6, mec="white", mew=1.2, zorder=3)
        ax.text(np.sin(r) - 0.03, np.cos(r) - 0.02, f"{d}° 숙임", fontsize=9, color=INK, ha="right", va="top")
    ax.text(0.02, 0.42, "머리만 숙이면\n원호를 따라 이동", fontsize=9, color=BLUE)
    for a in (0.5, 0.7):
        ax.plot(a, 1.0, "s", color=INK2, ms=6, zorder=3)
    ax.text(0.6, 1.04, "급제동 0.5 g, 0.7 g (세로축 그대로)", fontsize=9, color=INK2,
            ha="center", va="bottom")
    ax.annotate("", (0.7, 1.0), (0.0, 1.0), arrowprops=dict(arrowstyle="->", color=INK2, lw=1))
    x, y = np.sin(np.radians(20)) + 0.5, np.cos(np.radians(20))
    ax.plot(x, y, "D", color=INK2, ms=5, zorder=3)
    ax.text(x + 0.03, y + 0.02, "20° 보며 0.5 g 제동", fontsize=9, color=INK2, va="bottom")
    ax.set_xlim(-0.02, 1.45)
    ax.set_ylim(-0.05, 1.18)
    ax.set_aspect("equal")
    ax.set_xlabel("앞축 가속도 (g)")
    ax.set_ylabel("세로축 가속도 (g)")
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    fig.savefig(OUT / "tilt_plane.png")
    plt.close(fig)


if __name__ == "__main__":
    model_size()
    ppg_transfer()
    timeline()
    tilt_plane()
    print("docs/figures 에 4개 저장")
