"""4단계. 판정 블록의 정수 정답지와 테스트 벡터. 설계는 docs/integer-inference-design.md.

    python scripts/make_infer_vectors.py              # 50명 전부 + edge
    python scripts/make_infer_vectors.py --calib [--frac=10]   # T_FIX 후보를 훑어 헛경보 4회/h 이하 최소값 찾기
    python scripts/make_infer_vectors.py 02 05        # 일부

만드는 것
  data/processed/stage4/infer_key.csv   50명 × 5초 블록. 재료·기준선·정수 판정·실수 판정·뒤집힘
  sim/vectors/infer/NN.txt              사람마다 "block n60 sum_rr60 hold drowsy" (테스트벤치 입력·정답)
  sim/vectors/infer/edge.txt            손으로 만든 경계 사례. 같은 형식

정답은 라벨이 아니라 src/infer_ref.py 의 정수 판정이다. Verilog 가 이것과 비트 단위로 같으면 통과.
재료(n60, sum_rr60)는 2단계 표와 같은 절차(WindowAcc, 봉우리 위치 기준 블록)로 만들되 5초마다 저장한다.
30초 에폭 끝 블록의 재료는 features_60s.csv 의 n, sum_rr 와 같아야 한다(스크립트가 확인한다).
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.window_acc import WindowAcc, BLOCK  # noqa: E402
from src import infer_ref as R  # noqa: E402
from src.infer_ref import InferRef  # noqa: E402
from src.stage3 import scoring as S  # noqa: E402

IN = ROOT / "data" / "interim" / "rr"
TABLE = ROOT / "data" / "processed" / "features_60s.csv"
OUT_KEY = ROOT / "data" / "processed" / "stage4"
OUT_VEC = ROOT / "sim" / "vectors" / "infer"
EPOCH_BLOCKS = 6
T_FLOAT_4 = 1.067202691345673      # 50명 전체 mean_rb_chip 에서 헛경보 4회/h 실수 문턱 (scripts/calib_t_float.py, 준용 v14 검출기 기준 9/23)
T_FLOAT_2 = 1.105804472236118      # 2회/h. 칩에는 안 넣고 참고용


def block_materials(sid):
    """블록마다 (n60, sum_rr60). scripts/make_features.windows 와 같은 절차, 저장만 5초마다."""
    z = np.load(IN / f"{sid}.npz")
    peaks, rr, ok, labels = z["peaks"], z["rr"], z["ok"], z["labels"].astype(int)
    nblk = len(labels) * EPOCH_BLOCKS
    blk = peaks[1:] // BLOCK
    per_blk = {}
    for b, r, o in zip(blk, rr, ok):
        if b < nblk:
            per_blk.setdefault(int(b), []).append((int(r), bool(o)))
    acc = WindowAcc()
    out = []
    for b in range(nblk):
        for r, o in per_blk.get(b, []):
            acc.push_rr(r, o)
        acc.sample = (b + 1) * BLOCK - 1
        acc.push_sample()
        out.append((int(acc.win60["n"]), int(acc.win60["sum_rr"])))
    return out, labels


def subject_key(sid, mats, labels, t_fix, frac=R.FRAC):
    ref = InferRef(t_fix, frac)
    rows = []
    for b, (n60, s60) in enumerate(mats):
        base_n, base_sum = ref.base_n, ref.base_sum
        ready = ref.ready
        hold, drowsy = ref.push(n60, s60)
        # 실수 판정: 표의 mean_rb_chip 정의 그대로 (mean_nn × base_n / base_sum). 기준선은 push 전 값이 아니라
        # 판정에 실제 쓰인 값(ready 상태의 것)이어야 하므로 hold 가 아닐 때만 의미 있다.
        if hold:
            mean_rb = np.nan
            f4 = f2 = -1
        else:
            mean_rb = (s60 / n60) * ref.base_n / ref.base_sum
            f4 = int(mean_rb >= T_FLOAT_4)
            f2 = int(mean_rb >= T_FLOAT_2)
        epoch = b // EPOCH_BLOCKS
        rows.append(dict(sid=int(sid), block=b, epoch=epoch, epoch_end=int((b + 1) % EPOCH_BLOCKS == 0),
                         label=int(labels[epoch]), n60=n60, sum_rr60=s60,
                         base_n=ref.base_n if ref.ready else 0, base_sum=ref.base_sum if ref.ready else 0,
                         hold=hold, drowsy=drowsy, mean_rb=mean_rb, drowsy_f4=f4, drowsy_f2=f2))
    return pd.DataFrame(rows)


def check_against_table(key):
    """에폭 끝 블록의 재료·기준선이 2단계 표(features_60s.csv)와 같은지."""
    t = pd.read_csv(TABLE)
    e = key[key.epoch_end == 1].merge(t, on=["sid", "epoch"], suffixes=("", "_t"))
    e = e[e.reason != "no_window"]
    bad = e[(e.n60 != e.n) | (e.sum_rr60 != e.sum_rr)]
    assert bad.empty, f"재료 불일치 {len(bad)}행\n{bad.head()}"
    j = e[(e.judged == 1)]
    assert (j.hold == 0).all(), "표는 판정하는데 정답지는 hold"
    assert (j.base_n == j.base_n_chip).all() and (j.base_sum == j.base_sum_rr_chip).all(), "기준선 불일치"
    assert np.allclose(j.mean_rb, j.mean_rb_chip, rtol=2e-5), "mean_rb 불일치"   # 표는 %.6g 로 저장됨
    return len(e), len(j)


def epoch_score(key, t_fix_col="drowsy"):
    """에폭 끝 블록의 판정으로 3단계와 같은 채점(사람 단위 사건·헛경보). 표의 valid 행만."""
    t = pd.read_csv(TABLE)[["sid", "epoch", "y", "valid"]]
    e = key[key.epoch_end == 1][["sid", "epoch", t_fix_col]].merge(t, on=["sid", "epoch"], how="right")
    e = e.sort_values(["sid", "epoch"]).reset_index(drop=True)
    e["alarm"] = ((e[t_fix_col] == 1) & (e.valid == 1)).astype(int)
    return S.pooled(S.score_table(e, "alarm"))


def calibrate(sids, frac):
    """T_FIX 후보를 훑어 헛경보 4회/h 이하가 되는 최소 정수. 실수 문턱 근처만 본다."""
    mats = {sid: block_materials(sid) for sid in sids}
    rows = []
    c = int(T_FLOAT_4 * (1 << frac))
    for t_fix in range(c - 3, c + 5):
        key = pd.concat([subject_key(s, m, l, t_fix, frac) for s, (m, l) in mats.items()], ignore_index=True)
        p = epoch_score(key)
        j = key[key.hold == 0]
        flips = int((j.drowsy != j.drowsy_f4).sum())
        rows.append(dict(frac=frac, t_fix=t_fix, T=t_fix / (1 << frac), fa_per_hour=p["fa_per_hour"],
                         event_sens=p["event_sens"], win_sens=p["win_sens"], flips=flips, judged=len(j)))
        print(rows[-1])
    df = pd.DataFrame(rows)
    ok = df[df.fa_per_hour <= 4.0]
    print("\n헛경보 4회/h 이하 최소 T_FIX:", int(ok.t_fix.min()) if not ok.empty else None)
    return df


def edge_cases():
    """손으로 만든 경계 사례. 기준 모델로 정답을 붙인다. 각 사례는 리셋부터 시작(테스트벤치가 'reset' 줄에서 리셋)."""
    cases = []
    # 1. 정상 워밍업 뒤 경계값: 양변이 정확히 같을 때(≥ 이므로 drowsy=1), 1 작을 때, n60=29/30, n60=0
    warm = [(80, 19200)] * 36                          # 60초 창: 80박, ΣRR 19200 (RR 240 = 1초). base_n=240, base_sum=57600
    base_n, base_sum = 80 * 3, 19200 * 3
    r = R.T_FIX * base_sum
    # lhs = (s60 × base_n) << FRAC ≥ r × n60  →  s60 ≥ r × n60 / (base_n << FRAC)
    n60 = 80
    s_eq = -(-r * n60 // (base_n << R.FRAC))            # 올림: 이 값부터 drowsy=1
    body = [(n60, s_eq), (n60, s_eq - 1), (n60, s_eq + 1), (29, 7000), (30, 7000), (30, 8000), (0, 0), (255, 131071)]
    cases.append(("boundary", warm + body))
    # 2. 워밍업 재시작: 첫 3분 base_n < 45 → 다시 3분, 그 뒤 판정. 재시작 전후 hold 확인
    cases.append(("restart", [(10, 2400)] * 36 + [(80, 19200)] * 36 + [(80, 19200), (80, 22000)]))
    # 3. 최대값: base_n 594·base_sum 43560 근처, sum_rr60 최대. 폭 넘침이 없는지
    cases.append(("maxval", [(198, 14520)] * 36 + [(200, 72000), (200, 131071), (255, 131071), (1, 131071)]))
    # 4. 워밍업 중 창 합이 들쭉날쭉해도 12·24·36번째만 더하는지 (다른 블록에 큰 값)
    seq = [(255, 131071)] * 36
    for k in (11, 23, 35):
        seq[k] = (80, 19200)
    cases.append(("warm_pick", seq + [(80, 19200), (80, 21000)]))
    lines = ["case block n60 sum_rr60 hold drowsy"]
    for name, seq in cases:
        ref = InferRef()
        for b, (n, s) in enumerate(seq):
            h, d = ref.push(n, s)
            lines.append(f"{name} {b} {n} {s} {h} {d}")
    return lines


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    sids = [a for a in argv if not a.startswith("--")] or sorted(p.stem for p in IN.glob("*.npz"))
    t0 = time.time()
    if "--calib" in flags:
        frac = int(next((a.split("=")[1] for a in flags if a.startswith("--frac=")), R.FRAC))
        df = calibrate(sids, frac)
        OUT_KEY.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT_KEY / f"t_fix_calib_frac{frac}.csv", index=False, float_format="%.6g")
        return 0

    keys = []
    for sid in sids:
        mats, labels = block_materials(sid)
        keys.append(subject_key(sid, mats, labels, R.T_FIX))
    key = pd.concat(keys, ignore_index=True)
    n_e, n_j = check_against_table(key)
    print(f"표 대조: 에폭 {n_e}개 재료 일치, 판정 에폭 {n_j}개 기준선·mean_rb 일치")

    j = key[key.hold == 0]
    flips = j[j.drowsy != j.drowsy_f4]
    print(f"T_FIX={R.T_FIX} (T={R.T_FIX / (1 << R.FRAC):.4f}) vs 실수 T={T_FLOAT_4:.4f}: "
          f"판정 블록 {len(j)}개 중 뒤집힘 {len(flips)}개 ({100 * len(flips) / len(j):.3f}%)")
    if len(flips):
        print("  뒤집힌 블록의 mean_rb 범위:", flips.mean_rb.min(), "~", flips.mean_rb.max())
    p = epoch_score(key)
    print(f"에폭 채점(3단계 방식, 50명 전체): 헛경보 {p['fa_per_hour']:.3f}/h, 사건 민감도 {p['event_sens']:.3f}, "
          f"창 민감도 {p['win_sens']:.3f}, 잡은 사건 {p['detected']}/{p['n_events']}")
    print(f"블록 전체: {len(key)}, hold {int(key.hold.sum())} ({100 * key.hold.mean():.1f}%), "
          f"drowsy {int(key.drowsy.sum())} ({100 * key.drowsy.mean():.1f}%)")
    print(f"기준선 범위: base_n {j.base_n.min()}~{j.base_n.max()}, base_sum {j.base_sum.min()}~{j.base_sum.max()}, "
          f"재시작 있었던 사람: {sorted(key[(key.block >= 36) & (key.block < 72) & (key.hold == 1) & (key.n60 >= R.MIN_N60)].sid.unique().tolist())}")

    OUT_KEY.mkdir(parents=True, exist_ok=True)
    key.to_csv(OUT_KEY / "infer_key.csv", index=False, float_format="%.6g")
    OUT_VEC.mkdir(parents=True, exist_ok=True)
    for sid, k in key.groupby("sid"):
        with open(OUT_VEC / f"{sid:02d}.txt", "w", newline="\n") as f:
            f.write("block n60 sum_rr60 hold drowsy\n")
            for r in k.itertuples():
                f.write(f"{r.block} {r.n60} {r.sum_rr60} {r.hold} {r.drowsy}\n")
    with open(OUT_VEC / "edge.txt", "w", newline="\n") as f:
        f.write("\n".join(edge_cases()) + "\n")
    print(f"→ {OUT_KEY.relative_to(ROOT)}/infer_key.csv, {OUT_VEC.relative_to(ROOT)}/NN.txt × {key.sid.nunique()}, edge.txt"
          f"  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
