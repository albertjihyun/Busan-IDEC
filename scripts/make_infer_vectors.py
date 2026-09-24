"""4단계. 판정 블록의 정수 정답지와 테스트 벡터. 설계는 docs/integer-inference-design.md.

    python scripts/make_infer_vectors.py              # 50명 전부 + edge
    python scripts/make_infer_vectors.py --calib [--frac=10]   # T_FIX 후보를 훑어 헛경보 4회/h 이하 최소값 찾기
    python scripts/make_infer_vectors.py 02 05        # 일부

만드는 것
  data/processed/stage4/infer_key.csv   50명 × 5초 블록. 재료·기준선·정수 판정·실수 판정·뒤집힘
  sim/vectors/infer/NN.txt              사람마다 "block n60 sum_rr60 bad60 hold drowsy" (테스트벤치 입력·정답)
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
T_FLOAT_4 = 1.0601714757378689     # 50명 전체 mean_rb_chip 에서 헛경보 4회/h 실수 문턱 (설계서 2절, scripts/calib_t_float.py 로 재현 가능)
T_FLOAT_2 = 1.0999238569284642     # 2회/h. 칩에는 안 넣고 참고용


def block_materials(sid):
    """블록마다 (n60, sum_rr60, bad60). scripts/make_features.windows 와 같은 절차, 저장만 5초마다.
    bad60 = 최근 12블록에서 SQI 탈락한 RR 수(준용 o_bad60 와 같은 뜻)."""
    z = np.load(IN / f"{sid}.npz")
    peaks, rr, ok, labels = z["peaks"], z["rr"], z["ok"], z["labels"].astype(int)
    nblk = len(labels) * EPOCH_BLOCKS
    blk = peaks[1:] // BLOCK
    per_blk = {}
    for b, r, o in zip(blk, rr, ok):
        if b < nblk:
            per_blk.setdefault(int(b), []).append((int(r), bool(o)))
    acc = WindowAcc()
    out, bad = [], []
    for b in range(nblk):
        nb = 0
        for r, o in per_blk.get(b, []):
            acc.push_rr(r, o)
            nb += (not o)
        bad.append(nb)
        acc.sample = (b + 1) * BLOCK - 1
        acc.push_sample()
        out.append((int(acc.win60["n"]), int(acc.win60["sum_rr"]), min(255, sum(bad[max(0, b - 11):b + 1]))))
    return out, labels


def subject_key(sid, mats, labels, t_fix, frac=R.FRAC):
    ref = InferRef(t_fix, frac)
    rows = []
    for b, (n60, s60, b60) in enumerate(mats):
        hold, drowsy = ref.push(n60, s60, b60)
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
                         label=int(labels[epoch]), n60=n60, sum_rr60=s60, bad60=b60,
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
    # 9/24 기준선·창 품질 규칙 이후: 표(첫 3분 고정 기준선, n60<30 만 무효)와 다를 수 있는 곳은 둘뿐이다.
    # (1) 첫 3분 창 중 나쁜 창이 있어 기준선이 늦게 잡힌 사람, (2) 탈락이 많아 추가로 hold 된 창.
    # 그 밖에서는 기준선·mean_rb 가 표와 같아야 한다.
    j = e[(e.judged == 1) & (e.hold == 0)]
    same = j[(j.base_n == j.base_n_chip) & (j.base_sum == j.base_sum_rr_chip)]
    moved = sorted(j[(j.base_n != j.base_n_chip) | (j.base_sum != j.base_sum_rr_chip)].sid.unique().tolist())
    assert np.allclose(same.mean_rb, same.mean_rb_chip, rtol=2e-5), "mean_rb 불일치"   # 표는 %.6g 로 저장됨
    extra_hold = int(((e.judged == 1) & (e.hold == 1)).sum())
    return len(e), len(j), moved, extra_hold


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
    """손으로 만든 경계 사례. 기준 모델로 정답을 붙인다. 각 사례는 리셋부터 시작(테스트벤치가 case 이름이 바뀔 때 리셋).
    한 줄 = (n60, sum_rr60, bad60)."""
    cases = []
    warm = [(80, 19200, 0)] * 36                        # 60초 창: 80박, ΣRR 19200 (RR 240 = 1초). base_n=240, base_sum=57600
    base_n, base_sum = 80 * 3, 19200 * 3
    r = R.T_FIX * base_sum
    n60 = 80
    s_eq = -(-r * n60 // (base_n << R.FRAC))            # 올림: 이 값부터 drowsy=1
    # 1. 판정 경계: 양변 같음(≥ 이므로 drowsy=1), 1 작음, n60=29/30, n60=0, 최대값
    body = [(n60, s_eq, 0), (n60, s_eq - 1, 0), (n60, s_eq + 1, 0), (29, 7000, 0), (30, 7000, 0), (30, 8000, 0),
            (0, 0, 0), (255, 131071, 0)]
    cases.append(("boundary", warm + body))
    # 2. 창 품질 경계: KEEP_K × bad60 = n60 은 좋음, 넘으면 hold. bad60 최대
    k = R.KEEP_K
    body = [(81, s_eq * 81 // 80, 81 // k), (81, s_eq * 81 // 80, 81 // k + 1), (90, 21600, 30), (90, 21600, 31),
            (30, 8000, 10), (30, 8000, 11), (200, 50000, 255), (255, 131071, 85)]
    cases.append(("keep", warm + body))
    # 3. 기준선: 나쁜 창(박동 부족·탈락 과다)은 건너뛰고 좋은 창 3개가 모일 때 완성. 사이 블록 값은 안 쓰임
    seq = [(255, 131071, 200)] * 72
    for kk, v in ((11, (10, 2400, 0)), (23, (80, 19200, 0)), (35, (80, 19200, 27)), (47, (70, 16800, 23)),
                  (59, (29, 7000, 0)), (71, (90, 21600, 0))):
        seq[kk] = v
    cases.append(("base_skip", seq + [(80, 19200, 0), (80, 22000, 0), (80, 22000, 30)]))
    # 4. 최대값: base_n·base_sum 상한 근처
    cases.append(("maxval", [(255, 14760, 0)] * 36 + [(200, 72000, 0), (200, 131071, 0), (255, 131071, 0), (30, 131071, 0)]))
    lines = ["case block n60 sum_rr60 bad60 hold drowsy"]
    for name, seq in cases:
        ref = InferRef()
        for b, (n, s_, bd) in enumerate(seq):
            h, d = ref.push(n, s_, bd)
            lines.append(f"{name} {b} {n} {s_} {bd} {h} {d}")
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
    n_e, n_j, moved, extra_hold = check_against_table(key)
    print(f"표 대조: 에폭 {n_e}개 재료 일치, 판정 에폭 {n_j}개. 표는 판정하는데 창 품질·기준선 규칙으로 hold 된 에폭 {extra_hold}개, "
          f"기준선이 첫 3분과 달라진 사람 {moved}")

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
          f"기준선 늦게 잡힌 사람: {moved}")

    OUT_KEY.mkdir(parents=True, exist_ok=True)
    key.to_csv(OUT_KEY / "infer_key.csv", index=False, float_format="%.6g")
    OUT_VEC.mkdir(parents=True, exist_ok=True)
    for sid, k in key.groupby("sid"):
        with open(OUT_VEC / f"{sid:02d}.txt", "w", newline="\n") as f:
            f.write("block n60 sum_rr60 bad60 hold drowsy\n")
            for r in k.itertuples():
                f.write(f"{r.block} {r.n60} {r.sum_rr60} {r.bad60} {r.hold} {r.drowsy}\n")
    with open(OUT_VEC / "edge.txt", "w", newline="\n") as f:
        f.write("\n".join(edge_cases()) + "\n")
    print(f"→ {OUT_KEY.relative_to(ROOT)}/infer_key.csv, {OUT_VEC.relative_to(ROOT)}/NN.txt × {key.sid.nunique()}, edge.txt"
          f"  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
