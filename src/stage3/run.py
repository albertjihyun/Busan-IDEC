"""3단계 실행기: 겹친 LOSO로 모델을 돌리고 결과를 저장한다. 설계서 2·3·7절.

사용: python -m src.stage3.run --models rule dtree --wins 30 60 [--n-jobs 8] [--sids 1 2 3]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, ParameterSampler, cross_val_predict

from .data import FEATURES, OUT_DIR, corr_prune, load_table
from .models import MODELS, ORDER, SEED, ModelSpec
from .scoring import bootstrap_ci, pick_thresholds, pooled, score_table, subject_auc, sweep

CAPS = [0.5, 1.0, 2.0, 4.0, 8.0]      # 헛경보/시간 상한 격자 (설계서 3절 4)
N_INNER = 5
PERM_REPEATS = 3


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def get_scores(est, X) -> np.ndarray:
    if hasattr(est, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    return est.decision_function(X)


def _method(est) -> str:
    return "predict_proba" if hasattr(est, "predict_proba") else "decision_function"


def inner_eval(spec: ModelSpec, params: dict, feats: list[str], X: pd.DataFrame, y: np.ndarray,
               splits: list, rng: np.random.Generator, perm: bool):
    """안쪽 묶음으로 AUC 평균·표준오차와 순열 중요도."""
    aucs = []
    imp = np.zeros(len(feats))
    for tr, va in splits:
        if len(np.unique(y[va])) < 2:
            continue
        est = spec.make().set_params(**params).fit(X.iloc[tr][feats], y[tr])
        Xv = X.iloc[va][feats]
        a = roc_auc_score(y[va], get_scores(est, Xv))
        aucs.append(a)
        if perm and len(feats) > 1:
            for j, f in enumerate(feats):
                for _ in range(PERM_REPEATS):
                    Xp = Xv.copy()
                    Xp[f] = rng.permutation(Xp[f].values)
                    imp[j] += a - roc_auc_score(y[va], get_scores(est, Xp))
    aucs = np.array(aucs)
    return float(aucs.mean()), float(aucs.std(ddof=1) / np.sqrt(len(aucs))), imp / (len(aucs) * PERM_REPEATS)


def search_params(spec: ModelSpec, feats, X, y, splits) -> tuple[dict, list]:
    """RandomizedSearch와 같은 절차를 직접 돈다(재현성·로그 때문). 안쪽 AUC 평균 최대 후보."""
    if not spec.param_dist:
        return {}, []
    cands = list(ParameterSampler(spec.param_dist, n_iter=spec.n_iter, random_state=SEED))
    rows = []
    for p in cands:
        m, se, _ = inner_eval(spec, p, feats, X, y, splits, np.random.default_rng(SEED), perm=False)
        rows.append({"params": p, "auc": m, "se": se})
    best = max(rows, key=lambda r: r["auc"])
    return best["params"], rows


def eliminate(spec: ModelSpec, params, feats, X, y, splits):
    """순열 중요도 최저 특징을 하나씩 빼며 재평가. 1-SE 규칙으로 세트 선택."""
    rng = np.random.default_rng(SEED)
    cur = list(feats)
    hist = []
    while True:
        m, se, imp = inner_eval(spec, params, cur, X, y, splits, rng, perm=len(cur) > 1)
        hist.append({"feats": list(cur), "auc": m, "se": se, "imp": {f: float(v) for f, v in zip(cur, imp)}})
        if len(cur) == 1:
            break
        cur.pop(int(np.argmin(imp)))
    best = max(hist, key=lambda h: h["auc"])
    ok = [h for h in hist if h["auc"] >= best["auc"] - best["se"]]
    chosen = min(ok, key=lambda h: len(h["feats"]))
    return chosen["feats"], hist


def oof_thresholds(spec, params, feats, X, y, groups, splits, full_train: pd.DataFrame, valid_index):
    """안쪽 교차 예측 점수로 헛경보 상한별 문턱을 고른다. full_train: 학습 피험자의 전체 행(무효 포함)."""
    est = spec.make().set_params(**params)
    oof = cross_val_predict(est, X[feats], y, groups=groups, cv=splits, method=_method(est))
    if oof.ndim == 2:
        oof = oof[:, 1]
    tmp = full_train[["sid", "epoch", "y", "valid"]].copy()
    tmp["score"] = np.nan
    tmp.loc[valid_index, "score"] = oof
    curve = sweep(tmp, "score")
    return pick_thresholds(curve, CAPS), oof


def run_fold(model: str, win: int, test_sid: int, df: pd.DataFrame, overrides: dict | None = None,
             fixed: dict | None = None) -> dict:
    """바깥 폴드 하나. fixed가 있으면(사다리) 손잡이·특징 탐색 없이 그 값을 쓴다."""
    t0 = time.time()
    spec = MODELS[model]
    full_train = df[df.sid != test_sid]
    train = full_train[full_train.valid == 1]
    test = df[(df.sid == test_sid) & (df.valid == 1)]
    X, y, g = train[FEATURES], train.y.values, train.sid.values
    splits = list(GroupKFold(N_INNER).split(X, y, g))

    if fixed is None:
        feats0 = corr_prune(X, FEATURES)
        params, search_rows = search_params(spec, feats0, X, y, splits)
        if spec.select_features:
            feats, hist = eliminate(spec, params, feats0, X, y, splits)
        else:
            feats, hist = feats0, []
    else:
        feats, params, feats0, search_rows, hist = fixed["feats"], dict(fixed["params"]), fixed["feats0"], [], []
    if overrides:
        params = {**params, **overrides}

    ths, oof = oof_thresholds(spec, params, feats, X, y, g, splits, full_train, train.index)
    est = spec.make().set_params(**params).fit(X[feats], y)
    score = get_scores(est, test[feats]) if len(test) else np.array([])
    # 폴드마다 점수 단위가 다르므로(규칙=특징 원값, SVM=결정함수) pooled 곡선·AUC용으로
    # 학습 피험자 OOF 분포 기준 백분위(0~1)를 함께 저장한다. 문턱은 원점수 위에서 고른다.
    oof_sorted = np.sort(oof)
    score_pct = np.searchsorted(oof_sorted, score, side="right") / len(oof_sorted)
    preds = pd.DataFrame({"sid": test_sid, "epoch": test.epoch.values, "score": score, "score_pct": score_pct})
    for cap in CAPS:
        preds[f"alarm_{cap:g}"] = score >= ths[cap]
    final = est.steps[-1][1]
    info = {
        "sid": int(test_sid), "feats0": feats0, "feats": feats, "params": {k: _js(v) for k, v in params.items()},
        "thresholds": {f"{c:g}": (ths[c] if np.isfinite(ths[c]) else None) for c in CAPS}, "cost": spec.cost(est, len(feats)),
        "search": [{"params": {k: _js(v) for k, v in r["params"].items()}, "auc": r["auc"]} for r in search_rows],
        "elimination": [{"feats": h["feats"], "auc": h["auc"], "se": h["se"]} for h in hist],
        "rule_feature": feats[getattr(final, "feature_", 0)] if model == "rule" else None,
        "seconds": time.time() - t0,
    }
    return {"preds": preds, "info": info}


def _js(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, tuple):
        return list(v)
    return v


def summarize(df: pd.DataFrame, preds: pd.DataFrame, infos: list[dict], out: Path, label: str) -> dict:
    """pooled 지표, 신뢰구간, 사람별 표, FROC 곡선을 저장."""
    df = df[df.sid.isin(preds.sid.unique())]   # 부분 실행(--sids) 때 예측 없는 사람은 뺀다
    full = df[["sid", "epoch", "y", "valid"]].merge(preds, on=["sid", "epoch"], how="left")
    summ = {"label": label, "n_folds": len(infos)}
    per_subject = None
    for cap in CAPS:
        col = f"alarm_{cap:g}"
        counts = score_table(full, col)
        p = pooled(counts)
        p.update(bootstrap_ci(counts))
        summ[f"cap_{cap:g}"] = p
        ps = pd.DataFrame([c.__dict__ for c in counts]).set_index("sid")
        ps.columns = [f"{c}@{cap:g}" if c not in ("n_events", "n_unjudgeable", "alert_hours", "n_valid", "n_pos", "n_neg") else c
                      for c in ps.columns]
        per_subject = ps if per_subject is None else per_subject.join(ps[[c for c in ps.columns if "@" in c]])
    auc = subject_auc(full, "score")
    per_subject = per_subject.join(auc)
    summ["win_auc_mean"] = float(auc.mean())
    summ["win_auc_pooled_pct"] = float(roc_auc_score(full.loc[full.valid == 1, "y"], full.loc[full.valid == 1, "score_pct"]))
    costs = pd.DataFrame([i["cost"] for i in infos])
    summ["cost_median"] = {k: float(costs[k].median()) for k in costs.columns}
    summ["cost_max"] = {k: float(costs[k].max()) for k in costs.columns}
    summ["n_feats_median"] = float(np.median([len(i["feats"]) for i in infos]))
    summ["feat_freq"] = {f: int(sum(f in i["feats"] for i in infos)) for f in FEATURES}
    summ["seconds"] = float(sum(i["seconds"] for i in infos))
    froc = sweep(full, "score_pct")   # 백분위 점수로 pooled FROC
    out.mkdir(parents=True, exist_ok=True)
    full.to_csv(out / "preds.csv", index=False)
    per_subject.to_csv(out / "per_subject.csv")
    froc.to_csv(out / "froc.csv", index=False)
    (out / "folds.json").write_text(json.dumps(infos, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    return summ


def run_model(model: str, win: int, n_jobs: int, sids: list[int] | None) -> None:
    spec = MODELS[model]
    df = load_table(win)
    all_sids = sorted(df.sid.unique())
    test_sids = sids or all_sids
    out = OUT_DIR / f"{model}_{win}s"
    log(f"== {model} {win}s: {len(test_sids)} folds, n_jobs={n_jobs}")
    t0 = time.time()
    res = Parallel(n_jobs=n_jobs, verbose=0)(delayed(run_fold)(model, win, s, df) for s in test_sids)
    preds = pd.concat([r["preds"] for r in res], ignore_index=True)
    infos = [r["info"] for r in res]
    summ = summarize(df, preds, infos, out, f"{model}_{win}s")
    log(f"   main done {time.time() - t0:.0f}s: " + " ".join(
        f"N={c:g}:sens={summ[f'cap_{c:g}']['event_sens']:.3f}/fa={summ[f'cap_{c:g}']['fa_per_hour']:.2f}" for c in CAPS)
        + f" auc={summ['win_auc_mean']:.3f} feats={summ['n_feats_median']:.0f} bytes={summ['cost_median']['param_bytes']:.0f}")
    if spec.ladder and sids is None:
        rows = []
        for k, ov in enumerate(spec.ladder):
            t1 = time.time()
            fixed = {i["sid"]: {"feats": i["feats"], "params": i["params"], "feats0": i["feats0"]} for i in infos}
            res = Parallel(n_jobs=n_jobs)(delayed(run_fold)(model, win, s, df, ov, fixed[s]) for s in test_sids)
            p = pd.concat([r["preds"] for r in res], ignore_index=True)
            inf = [r["info"] for r in res]
            s = summarize(df, p, inf, out / f"ladder_{k}", f"{model}_{win}s_ladder_{k}")
            for c in CAPS:
                rows.append({"ladder": k, "override": json.dumps(ov), "cap": c, **s[f"cap_{c:g}"],
                             "win_auc_mean": s["win_auc_mean"], **{f"cost_{a}": b for a, b in s["cost_median"].items()}})
            log(f"   ladder {k} {ov} {time.time() - t1:.0f}s auc={s['win_auc_mean']:.3f} bytes={s['cost_median']['param_bytes']:.0f}")
        pd.DataFrame(rows).to_csv(out / "ladder.csv", index=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=ORDER)
    ap.add_argument("--wins", nargs="+", type=int, default=[30, 60])
    ap.add_argument("--n-jobs", type=int, default=8)
    ap.add_argument("--sids", nargs="*", type=int, default=None)
    a = ap.parse_args(argv)
    for m in a.models:
        for w in a.wins:
            try:
                run_model(m, w, a.n_jobs, a.sids)
            except Exception as e:  # 한 모델이 죽어도 다음 모델은 돈다
                log(f"!! {m} {w}s FAILED: {e!r}")
                import traceback; traceback.print_exc()


if __name__ == "__main__":
    main()
