"""모델 7종의 등록부: 추정기, 탐색 공간, 후보 수, 비용식, 크기 사다리. 설계서 5·6절.

채점기는 여기 등록된 것만 돌린다. 절차(분할·특징 선택·문턱)는 run.py에 있고 모델별로 다르지 않다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

SEED = 0


class RuleClassifier(ClassifierMixin, BaseEstimator):
    """특징 1개 + 문턱. 학습 = 학습 데이터에서 AUC(방향 포함)가 가장 높은 특징을 고른다. 점수 = 부호 * 특징값."""

    def fit(self, X, y):
        X = np.asarray(X, float); y = np.asarray(y)
        self.classes_ = np.unique(y)
        best = (-1.0, 0, 1.0)
        for j in range(X.shape[1]):
            a = roc_auc_score(y, X[:, j])
            s = 1.0 if a >= 0.5 else -1.0
            a = max(a, 1 - a)
            if a > best[0]:
                best = (a, j, s)
        self.auc_, self.feature_, self.sign_ = best
        return self

    def decision_function(self, X):
        X = np.asarray(X, float)
        return self.sign_ * X[:, self.feature_]

    def predict(self, X):
        return (self.decision_function(X) >= 0).astype(int)


def _tree_nodes(tree) -> tuple[int, int]:
    """(내부 노드 수, 잎 수)"""
    t = tree.tree_
    leaves = int((t.children_left == -1).sum())
    return int(t.node_count) - leaves, leaves


def _hgb_nodes(est) -> tuple[int, int]:
    internal = leaves = 0
    for stage in est._predictors:
        for p in stage:
            n = p.nodes
            leaves += int(n["is_leaf"].sum())
            internal += int((~n["is_leaf"].astype(bool)).sum())
    return internal, leaves


def _final(est):
    return est.steps[-1][1] if isinstance(est, Pipeline) else est


def cost_rule(est, d):
    return {"param_bytes": 2, "mults": 0, "nodes": 1}


def cost_dtree(est, d):
    i, l = _tree_nodes(_final(est))
    return {"param_bytes": 3 * i + l, "mults": 0, "nodes": i + l}


def cost_logreg(est, d):
    return {"param_bytes": d + 1, "mults": d, "nodes": 0}


def cost_rf(est, d):
    i = l = 0
    for t in _final(est).estimators_:
        a, b = _tree_nodes(t); i += a; l += b
    return {"param_bytes": 3 * i + l, "mults": 0, "nodes": i + l}


def cost_gboost(est, d):
    i, l = _hgb_nodes(_final(est))
    return {"param_bytes": 3 * i + 2 * l, "mults": 0, "nodes": i + l}


def cost_svm(est, d):
    n_sv = int(_final(est).n_support_.sum())
    return {"param_bytes": n_sv * d + 2 * n_sv, "mults": n_sv * d, "nodes": n_sv}


def cost_mlp(est, d):
    m = _final(est)
    w = sum(c.size for c in m.coefs_) + sum(b.size for b in m.intercepts_)
    mults = sum(c.size for c in m.coefs_)
    return {"param_bytes": int(w), "mults": int(mults), "nodes": int(sum(c.shape[1] for c in m.coefs_))}


@dataclass
class ModelSpec:
    name: str
    make: Callable[[], BaseEstimator]
    param_dist: dict = field(default_factory=dict)
    n_iter: int = 0
    cost: Callable = cost_rule
    ladder: list[dict] = field(default_factory=list)   # 크기 사다리: 최종 손잡이 위에 덮어쓸 파라미터
    select_features: bool = True                       # 규칙 모델은 특징 1개를 학습이 고르므로 제거 단계 없음
    chip: bool = True                                  # 칩 후보인지(비교선은 False)


def _pipe(scaler: bool, est):
    return Pipeline([("scale", StandardScaler()), ("est", est)]) if scaler else Pipeline([("est", est)])


MODELS: dict[str, ModelSpec] = {
    "rule": ModelSpec(
        name="rule", make=lambda: _pipe(False, RuleClassifier()), cost=cost_rule, select_features=False),
    "dtree": ModelSpec(
        name="dtree", make=lambda: _pipe(False, DecisionTreeClassifier(random_state=SEED)),
        param_dist={"est__max_depth": [1, 2, 3, 4, 5, 6, 7, 8],
                    "est__min_samples_leaf": [20, 50, 100, 200, 500],
                    "est__class_weight": [None, "balanced"]},
        n_iter=30, cost=cost_dtree,
        ladder=[{"est__max_depth": d} for d in (1, 2, 3, 4)]),
    "logreg": ModelSpec(
        name="logreg", make=lambda: _pipe(True, LogisticRegression(max_iter=2000)),
        param_dist={"est__C": list(np.logspace(-3, 2, 11)), "est__class_weight": [None, "balanced"]},
        n_iter=22, cost=cost_logreg),
    "rf": ModelSpec(
        name="rf", make=lambda: _pipe(False, RandomForestClassifier(random_state=SEED, n_jobs=1)),
        param_dist={"est__n_estimators": [50, 100, 200],
                    "est__max_depth": [2, 3, 4, 6, 8, None],
                    "est__min_samples_leaf": [5, 20, 50, 100],
                    "est__max_features": ["sqrt", 0.5, 1.0],
                    "est__class_weight": [None, "balanced_subsample"]},
        n_iter=30, cost=cost_rf,
        ladder=[{"est__n_estimators": n, "est__max_depth": d}
                for n, d in ((4, 3), (8, 3), (8, 4), (16, 4), (32, 4), (64, 6))]),
    "gboost": ModelSpec(
        name="gboost", make=lambda: _pipe(False, HistGradientBoostingClassifier(random_state=SEED, early_stopping=False)),
        param_dist={"est__max_iter": [50, 100, 200, 400],
                    "est__learning_rate": [0.03, 0.1, 0.3],
                    "est__max_depth": [2, 3, 4],
                    "est__min_samples_leaf": [20, 50, 100],
                    "est__l2_regularization": [0.0, 1.0, 10.0],
                    "est__class_weight": [None, "balanced"]},
        n_iter=30, cost=cost_gboost,
        ladder=[{"est__max_iter": n, "est__max_depth": d}
                for n, d in ((8, 3), (8, 4), (16, 4), (32, 4), (64, 4))]),
    "svm_rbf": ModelSpec(
        name="svm_rbf", make=lambda: _pipe(True, SVC(kernel="rbf", cache_size=500)),
        param_dist={"est__C": list(np.logspace(-2, 2, 5)),
                    "est__gamma": ["scale", 0.01, 0.1, 1.0],
                    "est__class_weight": [None, "balanced"]},
        n_iter=15, cost=cost_svm, chip=False),
    "mlp": ModelSpec(
        name="mlp", make=lambda: _pipe(True, MLPClassifier(max_iter=300, early_stopping=True, random_state=SEED)),
        param_dist={"est__hidden_layer_sizes": [(4,), (8,), (16,), (32,), (16, 8)],
                    "est__alpha": [1e-4, 1e-3, 1e-2, 1e-1],
                    "est__learning_rate_init": [1e-3, 1e-2]},
        n_iter=20, cost=cost_mlp, chip=False,
        ladder=[{"est__hidden_layer_sizes": h} for h in ((2,), (4,), (8,))]),
}

ORDER = ["rule", "dtree", "logreg", "rf", "gboost", "svm_rbf", "mlp"]
