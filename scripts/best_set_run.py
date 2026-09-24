"""1-SE 규칙 대신 '안쪽 AUC 최고' 특징 세트로 바깥 고리를 다시 돈다.

손잡이는 주 실행에서 고른 것을 그대로 쓰고 특징 세트만 바꾼다. 안쪽 탐색이 없어 값싸다.
결과는 {model}_{win}s_bestset 폴더에 저장.
사용: python -m scripts.best_set_run logreg dtree --wins 30 60
"""
import argparse, json, sys
from pathlib import Path
import pandas as pd
from joblib import Parallel, delayed
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.stage3.data import OUT_DIR, load_table
from src.stage3.run import run_fold, summarize, log

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--wins", nargs="+", type=int, default=[30, 60])
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--all-feats", action="store_true", help="1-SE 대신 상관 정리 후 전체 특징을 쓴다")
    a = ap.parse_args()
    for m in a.models:
        for w in a.wins:
            src = OUT_DIR / f"{m}_{w}s" / "folds.json"
            if not src.exists():
                log(f"skip {m} {w}s (주 실행 결과 없음)"); continue
            folds = json.loads(src.read_text(encoding="utf-8"))
            fixed = {}
            for f in folds:
                h = f["elimination"]
                if a.all_feats:
                    chosen = f["feats0"]
                else:
                    chosen = (max(h, key=lambda x: x["auc"]) if h else {"feats": f["feats"]})["feats"]
                fixed[f["sid"]] = {"feats": chosen, "params": f["params"], "feats0": f["feats0"]}
            tag = "allfeats" if a.all_feats else "bestset"
            df = load_table(w)
            sids = sorted(fixed)
            log(f"== {m} {w}s {tag}: 특징 중앙 {pd.Series([len(v['feats']) for v in fixed.values()]).median():.0f}개")
            res = Parallel(n_jobs=a.n_jobs)(delayed(run_fold)(m, w, s, df, None, fixed[s]) for s in sids)
            preds = pd.concat([r["preds"] for r in res], ignore_index=True)
            infos = [r["info"] for r in res]
            s = summarize(df, preds, infos, OUT_DIR / f"{m}_{w}s_{tag}", f"{m}_{w}s_{tag}")
            log("   " + " ".join(f"N={c}:sens={s[f'cap_{c}']['event_sens']:.3f}/fa={s[f'cap_{c}']['fa_per_hour']:.2f}"
                                for c in ("1", "2", "4", "8")) + f" auc={s['win_auc_mean']:.3f} feats={s['n_feats_median']:.0f}")

if __name__ == "__main__":
    main()
