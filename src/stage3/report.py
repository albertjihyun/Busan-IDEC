"""3단계 결과를 표·그림으로 정리한다. 끝난 모델만 읽으므로 실행 중에도 돌릴 수 있다.

사용: python -m src.stage3.report  ->  docs/model-results.md, docs/figures/stage3_froc_{30,60}s.png

읽는 규칙(설계서 9절 A): 모델 비교는 같은 헛경보에서 한다. 상한별 표는 모델마다
예산을 쓰는 정도가 달라 비교에 쓰면 안 되고, "이 절차를 칩에 넣으면 실제로 이렇게 된다"로만 읽는다.
"""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import EPOCH_SEC, OUT_DIR, PROCESSED, ROOT
from .models import MODELS, ORDER
from .scoring import _overlap, alarm_clusters, events_of

DOCS = ROOT / "docs"
FIG = DOCS / "figures"
FA_POINTS = [1.0, 2.0, 4.0]
OP = 4.0        # 주 동작점 (사용자 결정 9/19)
OP2 = 2.0       # 보조 동작점
KO = {"rule": "규칙(특징1+문턱)", "dtree": "얕은 트리", "logreg": "로지스틱",
      "rf": "랜덤포레스트", "gboost": "부스팅 트리", "svm_rbf": "RBF SVM", "mlp": "소형 MLP"}


def variants():
    out = []
    for m in ORDER:
        for w in (30, 60):
            for suf in ("", "_bestset"):
                if (OUT_DIR / f"{m}_{w}s{suf}" / "summary.json").exists():
                    out.append((m, w, suf))
    return out


def load(m, w, suf=""):
    d = OUT_DIR / f"{m}_{w}s{suf}"
    return (json.loads((d / "summary.json").read_text(encoding="utf-8")),
            pd.read_csv(d / "froc.csv"), d)


def labels():
    return pd.read_csv(PROCESSED / "features_30s.csv")[["sid", "epoch", "label"]]


def at_threshold(preds, t):
    """문턱 하나에서 사건 민감도, 깊은 사건(피로2+) 민감도, 헛경보/시간, 경보 적중률."""
    ev = det = dn = dd = fa = tc = alert = 0
    win_pos = win_hit = 0
    cov = []
    for _, g in preds.sort_values(["sid", "epoch"]).groupby("sid"):
        y, v, L = g.y.values, g.valid.values, g.label.values
        a = ((g.score_pct >= t) & (g.valid == 1)).values
        cls = alarm_clusters(a)
        evs = events_of(y, v)
        allev = [(s, e) for s, e, _ in evs]
        for s, e, ok in evs:
            if not ok:
                continue
            hit = any(_overlap((s, e), c) for c in cls)
            ev += 1
            det += hit
            win_pos += int((v[s:e + 1] == 1).sum())
            win_hit += int(a[s:e + 1].sum())
            if hit:
                cov.append(a[s:e + 1].sum() / max((v[s:e + 1] == 1).sum(), 1))
            if L[s:e + 1].max() >= 2:
                dn += 1
                dd += hit
        for c in cls:
            if any(_overlap(c, e) for e in allev):
                tc += 1
            else:
                fa += 1
        alert += int(((v == 1) & (y == 0)).sum())
    h = alert * EPOCH_SEC / 3600
    return {"event_sens": det / ev if ev else np.nan, "deep_sens": dd / dn if dn else np.nan,
            "fa_per_hour": fa / h if h else np.nan, "ppv": tc / (tc + fa) if tc + fa else np.nan,
            "win_sens": win_hit / win_pos if win_pos else np.nan,
            "in_event_cov": float(np.median(cov)) if cov else np.nan}


def th_for_fa(froc, fa):
    """곡선 보간으로 대략의 문턱을 잡는다. 정확히 맞추려면 th_exact를 쓴다."""
    c = froc.sort_values("fa_per_hour")
    return float(np.interp(fa, c.fa_per_hour, c.threshold))


def th_exact(preds, target, iters=30):
    """헛경보가 정확히 target이 되는 문턱을 이분법으로 찾는다.

    표 1(곡선 보간)과 표 3(문턱 적용)이 어긋나 보이던 문제를 없앤다.
    모든 표가 같은 방식으로 계산되도록 이 함수만 쓴다.
    """
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if at_threshold(preds, mid)["fa_per_hour"] > target:
            lo = mid
        else:
            hi = mid
    return hi


def sens_at(froc, fa):
    """FROC 곡선 위 보간값. 그림 설명용이며 표에는 쓰지 않는다(th_exact를 쓴다)."""
    c = froc.sort_values("fa_per_hour")
    return float(np.interp(fa, c.fa_per_hour, c.event_sens))


_CACHE: dict = {}


def metrics_at(m, w, suf, lab, target):
    """헛경보를 정확히 맞춘 뒤의 전 지표. 표 1·3·5가 공유한다."""
    k = (m, w, suf, target)
    if k not in _CACHE:
        _, _, d = load(m, w, suf)
        p = pd.read_csv(d / "preds.csv").merge(lab, on=["sid", "epoch"])
        _CACHE[k] = at_threshold(p, th_exact(p, target))
    return _CACHE[k]


def name(m, w, suf):
    return f"{KO.get(m, m)} {w}초" + (" (최고세트)" if suf else "")


def _auc(s):
    return s.get("win_auc_pooled_pct", float("nan"))


def table_main(vs, lab):
    r = ["| 모델 | 칩 | " + " | ".join(f"헛경보 {x:g}회/h" for x in FA_POINTS) +
         " | 전원 AUC | 특징 | 파라미터 | 곱셈 |",
         "|---|---|" + "---|" * (len(FA_POINTS) + 4)]
    for m, w, suf in vs:
        s, f, _ = load(m, w, suf)
        nf = 1 if m == "rule" else s["n_feats_median"]
        r.append(f"| {name(m, w, suf)} | {'○' if MODELS[m].chip else '비교선'} | " +
                 " | ".join(f"{metrics_at(m, w, suf, lab, x)['event_sens']:.3f}" for x in FA_POINTS) +
                 f" | {_auc(s):.3f} | {nf:.0f} |"
                 f" {s['cost_median']['param_bytes']:,.0f} B | {s['cost_median']['mults']:.0f} |")
    return "\n".join(r)


def table_op(vs, lab, op=OP):
    r = ["| 모델 | 사건 민감도 | 창 민감도 | 잡은 사건 안 커버율 | 깊은 사건(피로2+) | 실제 헛경보/h | 경보 적중률 |",
         "|---|---|---|---|---|---|---|"]
    for m, w, suf in vs:
        a = metrics_at(m, w, suf, lab, op)
        r.append(f"| {name(m, w, suf)} | {a['event_sens']:.3f} | {a['win_sens']:.3f} |"
                 f" {a['in_event_cov']:.2f} | {a['deep_sens']:.3f} |"
                 f" {a['fa_per_hour']:.2f} | {a['ppv']:.2f} |")
    return "\n".join(r)


def table_caps(vs):
    r = ["| 모델 | 상한 1회/h | 상한 2회/h | 상한 4회/h |", "|---|---|---|---|"]
    for m, w, suf in vs:
        s, _, _ = load(m, w, suf)
        cells = []
        for c in ("1", "2", "4"):
            x = s[f"cap_{c}"]
            lo, hi = x["event_sens_ci"]
            cells.append(f"{x['event_sens']:.3f} [{lo:.2f}-{hi:.2f}], 실제 {x['fa_per_hour']:.2f}")
        r.append(f"| {name(m, w, suf)} | " + " | ".join(cells) + " |")
    return "\n".join(r)


def table_window(vs, lab):
    """창 길이 비교. 표 1·3과 같은 방식(정확 문턱)으로 계산한다."""
    r = ["| 모델 | 목표 헛경보 | 창 | 사건 민감도 | 창 민감도 | 잡은 사건 안 커버율 | 깊은 사건 |",
         "|---|---|---|---|---|---|---|"]
    for m in ORDER:
        if len({w for a, w, c in vs if a == m and not c}) < 2:
            continue
        for x in FA_POINTS:
            for w in (30, 60):
                a = metrics_at(m, w, "", lab, x)
                r.append(f"| {KO.get(m, m) if w == 30 else ''} | {x:g}회/h | {w}초 |"
                         f" {a['event_sens']:.3f} | {a['win_sens']:.3f} |"
                         f" {a['in_event_cov']:.2f} | {a['deep_sens']:.3f} |")
    return "\n".join(r) if len(r) > 2 else "(두 창이 모두 끝난 모델 없음)"


def table_ladder(vs):
    r = ["| 모델 | 크기 | 헛경보 2회/h 민감도 | 전원 AUC | 파라미터 |", "|---|---|---|---|---|"]
    for m, w, suf in vs:
        if suf:
            continue
        p = OUT_DIR / f"{m}_{w}s" / "ladder.csv"
        if not p.exists():
            continue
        lad = pd.read_csv(p)
        for k in sorted(lad.ladder.unique()):
            sub = OUT_DIR / f"{m}_{w}s" / f"ladder_{k}"
            if not (sub / "froc.csv").exists():
                continue
            s2 = json.loads((sub / "summary.json").read_text(encoding="utf-8"))
            f2 = pd.read_csv(sub / "froc.csv")
            ov = str(lad[lad.ladder == k].iloc[0].override).replace("est__", "")
            r.append(f"| {KO.get(m, m)} {w}초 | {ov} | {sens_at(f2, 2.0):.3f} |"
                     f" {_auc(s2):.3f} | {s2['cost_median']['param_bytes']:,.0f} B |")
        s, f, _ = load(m, w)
        r.append(f"| {KO.get(m, m)} {w}초 | **제약 없음(탐색 최고)** | {sens_at(f, 2.0):.3f} |"
                 f" {_auc(s):.3f} | {s['cost_median']['param_bytes']:,.0f} B |")
    return "\n".join(r) if len(r) > 2 else "(아직 없음)"


def table_feats(vs):
    fs = list(load(*vs[0])[0]["feat_freq"])
    r = ["| 모델 | " + " | ".join(fs) + " |", "|---|" + "---|" * len(fs)]
    for m, w, suf in vs:
        if m == "rule" or suf:
            continue
        s, _, _ = load(m, w, suf)
        r.append(f"| {KO.get(m, m)} {w}초 | " +
                 " | ".join(str(s["feat_freq"][f]) if s["feat_freq"][f] else "." for f in fs) + " |")
    for m, w, suf in vs:
        if m != "rule" or suf:
            continue
        fo = json.loads((OUT_DIR / f"rule_{w}s" / "folds.json").read_text(encoding="utf-8"))
        c = pd.Series([x["rule_feature"] for x in fo]).value_counts()
        r.append(f"| 규칙 {w}초 (고른 특징) | " +
                 " | ".join(str(c.get(f, 0)) if c.get(f, 0) else "." for f in fs) + " |")
    return "\n".join(r)


def table_subject(vs):
    sids = (5, 26, 47, 22, 42, 49)
    r = ["| 모델 | " + " | ".join(f"{s}번" for s in sids) + " | AUC<0.5인 사람 |",
         "|---|" + "---|" * (len(sids) + 1)]
    for m, w, suf in vs:
        if suf:
            continue
        ps = pd.read_csv(OUT_DIR / f"{m}_{w}s" / "per_subject.csv", index_col=0)
        r.append(f"| {KO.get(m, m)} {w}초 | " +
                 " | ".join(f"{ps.win_auc.get(s, float('nan')):.2f}" for s in sids) +
                 f" | {(ps.win_auc < 0.5).sum()}/{ps.win_auc.notna().sum()} |")
    return "\n".join(r)


def froc_figure(vs, w):
    items = [m for m, ww, suf in vs if ww == w and not suf]
    if not items:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 5))
    for m in items:
        _, f, _ = load(m, w)
        c = f.sort_values("fa_per_hour")
        ax.plot(c.fa_per_hour, c.event_sens, lw=1.8, label=m, ls="-" if MODELS[m].chip else "--")
    ax.axvline(OP, color="0.4", lw=1, ls=":")
    ax.axvline(OP2, color="0.7", lw=1, ls=":")
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 1)
    ax.set_xlabel("false alarms per hour of alert time")
    ax.set_ylabel("event sensitivity")
    ax.set_title(f"{w}s window, pooled LOSO (50 subjects, 443 events)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    FIG.mkdir(parents=True, exist_ok=True)
    p = FIG / f"stage3_froc_{w}s.png"
    fig.tight_layout()
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def main():
    vs = variants()
    if not vs:
        print("no results yet")
        return
    lab = labels()
    done = sorted({f"{m}_{w}s" for m, w, suf in vs if not suf})
    P = [
        "# 3단계 결과 (자동 생성)", "",
        f"`python -m src.stage3.report` 출력. 끝난 모델·창 {len(done)}개: {', '.join(done)}.",
        "설계는 [model-comparison-design.md](./model-comparison-design.md), 근거 문헌은 "
        "[stage3-literature.md](./stage3-literature.md).", "",
        "## 읽는 법", "",
        "- 평가는 피험자 50명을 한 명씩 빼는 교차검증(LOSO)이고, 모든 선택(손잡이·특징·문턱)은 학습 49명 안에서만 한다.",
        "- 주 지표는 사건 단위 민감도다. 졸음 사건 443건 중 사건 구간 안에 경보가 한 번이라도 켜진 비율.",
        "- 짝 지표는 각성 시간당 헛경보 횟수다. 민감도는 문턱을 내리면 얼마든지 오르므로 반드시 짝으로 읽는다.",
        "- 모든 표는 헛경보가 정확히 그 값이 되는 문턱을 이분법으로 찾아 계산한다. 곡선 보간값과 섞으면 표끼리 어긋난다(9/19 수정).",
        "- 모델 비교는 같은 헛경보에서 한다. 모델마다 헛경보 예산을 쓰는 정도가 달라 상한별 표로 비교하면 왜곡된다(설계서 9절 A).",
        "- 정확도는 싣지 않는다. 경보를 한 번도 안 켜면 76.3%가 나오는 데이터라 뜻이 없다.",
        "- **확정(9/19)**: 모델 로지스틱 특징 1개(`mean_rb`), 창 60초, 주 동작점 헛경보 4회/h, 보조 2회/h. 근거는 설계서 11절.", "",
        "## 1. 한눈에 보기 (같은 헛경보에서의 사건 민감도)", "", table_main(vs, lab), "",
        "'전원 AUC'는 모두에게 같은 문턱 하나를 쓸 때의 판별력이다. 칩이 하는 일이 그것이라 사람별 평균 AUC보다 이 값이 맞다.", "",
        "## 2. FROC 곡선", "",
    ]
    for w in (30, 60):
        p = froc_figure(vs, w)
        if p:
            P += [f"**{w}초 창**", "", f"![{w}s]({p.relative_to(DOCS).as_posix()})", ""]
    P += [
        f"## 3. 주 동작점: 헛경보 {OP:g}회/시간 ({60 / OP:.0f}분에 한 번)", "",
        table_op(vs, lab, OP), "",
        "사용자 결정(9/19). 계획서의 원칙 '놓침 방지 우선'을 따른다. 4회/h 문턱은 폴드 간에 안정적이고(규칙 모델 원값 기준 중앙값 +9.8%, 사분위 +9.4~+10.3%), "
        "2회/h는 문턱이 튀는 폴드가 있다. 법정 비교(EU 2021/1341: KSS 8 이상 경보, 평균 민감도 40%·신뢰구간 하한 20%)는 '깊은 사건' 칸으로 한다. "
        "우리 라벨에서 KSS 8에 대응하는 것은 피로2 이상이며, 이 대응은 등가 증명이 아니라 정성적 정합성 논증이다. "
        "경보 적중률은 이 동작점에서 0.44로 인간공학 권고선 0.5를 밑돈다. 다만 그 적중률은 MPD-DF의 높은 사건 빈도(시간당 4.5건) 덕에 나온 값이고 "
        "실차(0.044건)에서는 어느 동작점이든 훨씬 낮아지므로 동작점을 가르는 기준으로는 약하다.", "",
        f"## 3b. 보조 동작점: 헛경보 {OP2:g}회/시간 ({60 / OP2:.0f}분에 한 번)", "",
        table_op(vs, lab, OP2), "",
        "법정 민감도 기준과 적중률 0.5 권고를 동시에 만족하는 유일한 지점. 보수적 선택지로 남긴다.", "",
        "**사건 단위는 관대한 채점이다.** 사건 안에 경보가 한 번이라도 겹치면 검출로 센다(NEDC any-overlap). "
        "졸음은 발작과 달리 연속 상태이고 우리 사건은 30초 해상도로 자르며 생긴 덩어리이므로, 이 관대함을 "
        "숨기지 않으려고 창 민감도(졸음 칸 중 경보가 켜진 비율)와 잡은 사건 안 커버율을 같은 표에 싣는다. "
        "긴 사건일수록 커버율이 낮아진다. 30초 창에서 3분 초과 사건은 잡았다고 세어도 절반 가까이 조용했고, 60초 창에서는 커버율 1.00이다.", "",
        "## 4. 상한별 결과 (칩에 이 절차를 그대로 넣었을 때)", "", table_caps(vs), "",
        "괄호는 피험자 단위 부트스트랩 95% 신뢰구간. '실제'는 시험 피험자에서 실제로 나온 헛경보다. "
        "상한과 실제가 벌어지는 정도가 모델마다 달라 이 표로 모델을 비교하면 안 된다.", "",
        "## 5. 창 길이 30초 대 60초", "", table_window(vs, lab), "",
        "## 6. 크기 사다리 (특징·손잡이는 고정, 크기만 변경)", "", table_ladder(vs), "",
        "## 7. 특징 선택 빈도 (50폴드 중 최종 세트에 남은 횟수)", "", table_feats(vs), "",
        "## 8. 사람별 창 AUC (예외 후보와 특이 피험자)", "", table_subject(vs), "",
        "5·47번은 아티팩트가 절반, 26번은 SQI 탈락 19%. 22번은 각성 에폭이 없고 42·49번은 사건이 없어 AUC가 정의되지 않는다.", "",
        "## 9. 한계", "",
        "- 학습 데이터 MPD-DF는 오후 1~4시, 수면 박탈 없음, 시속 35 km 시뮬레이터다. 단조로움에서 오는 피로이고 밤샘 졸음이 아니다.",
        "- 사건 기저율이 시간당 4.5건으로 실차 운송 보고값(0.044건)의 100배다. 경보 적중률은 실차에서 더 낮아진다.",
        "- 라벨은 의사 1명의 뇌파 판독이고 판독자 간 일치도 보고가 없다.",
        "- 헛경보는 30초 판정 기준이다. 칩은 5초마다 판정하므로 5단계에서 다시 잰다.",
        "- 이 문서의 모든 숫자는 MPD-DF 안의 값이다. 외부 검증(AdVitam)은 하지 않았다.", "",
    ]
    (DOCS / "model-results.md").write_text("\n".join(P), encoding="utf-8")
    print("wrote docs/model-results.md,", len(vs), "variants")


if __name__ == "__main__":
    main()
