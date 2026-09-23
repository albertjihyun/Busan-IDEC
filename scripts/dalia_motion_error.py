"""PPG-DaLiA 로 '움직임 크기 vs PPG 심박 오차' 를 잰다. 6단계 보류(hold) 문턱의 근거 자료.

칩과 같은 조건으로 손목 PPG(BVP 64 Hz → 240 Hz, 0.16~16 Hz 대역)에 우리 봉우리 규칙(src/peak_simple)과
SQI, 5초 블록 누산(src/window_acc), 정수 판정(src/infer_ref)을 돌리고, 가슴 ECG 의 R봉우리(데이터셋 제공,
보정본)를 정답으로 삼아 블록·창 단위로 비교한다. 움직임은 scripts/dalia_prep.py 가 만든 acc_blocks.csv
(손목 = PPG 센서 자체의 움직임, 가슴 = 이마 대용).

출력 (data/processed/stage6/)
  blocks.csv   블록 하나가 한 줄: subject, blk, activity, 손목·가슴 움직임(dev_max), 5초 블록 n·ΣRR (ECG / PPG SQI 있음 / PPG SQI 없음)
  windows.csv  60초 창(블록마다 하나): 창 평균 RR 오차(PPG−ECG)/ECG, ECG·PPG 판정(hold, drowsy; 기준선은 ECG 것 공유), 창 안 최대 움직임
  요약표는 report_motion_error() 가 표준 출력으로 (마크다운).

한계: 손목 PPG 는 이마보다 나쁘다(문턱은 이마 기준으로 보수적). 활동은 운전 3.8 h 포함 9종.
"""
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfiltfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import peak_simple as ps                     # noqa: E402
from src.window_acc import WindowAcc, BLOCK, W60      # noqa: E402
from src.infer_ref import InferRef, MIN_N60           # noqa: E402
from src.mpd_io import resample_to                    # noqa: E402

IN = ROOT / "data/interim/dalia"
OUT = ROOT / "data/processed/stage6"
FS_PPG = 240
FS_ECG = 700
HP_HZ, LP_HZ = 0.16, 16.0          # AFE 대역(회로도). PPG 는 16 Hz 로 충분
POLARITY = -1                      # Empatica BVP 는 급상승이 아래로 향한다. 뒤집어야 우리 규칙(급하강 24샘플)이 맞는다.
                                   # 극성 그대로면 반값 하강에 82샘플(0.34 s)이 걸려 DROP_WIN 72 이상 필요. 준용 v9 PPG_INVERT 와 같은 문제
MOTION_BINS = [0, 0.1, 0.2, 0.3, 0.5, 1.0, np.inf]
ACT = {0: "이동", 1: "앉기", 2: "계단", 3: "축구", 4: "자전거", 5: "운전", 6: "점심", 7: "걷기", 8: "업무"}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def ppg_chain(bvp, fs_in):
    x = resample_to(bvp.astype(float), fs_in, FS_PPG)
    sos_hp = butter(1, HP_HZ, btype="high", fs=FS_PPG, output="sos")
    sos_lp = butter(1, LP_HZ, btype="low", fs=FS_PPG, output="sos")
    return POLARITY * sosfiltfilt(sos_lp, sosfiltfilt(sos_hp, x))


def blocks_from_peaks(peaks, oks, n_blocks):
    """봉우리 위치(240 Hz 샘플)와 유효 마스크 → 블록별 (n, sum_rr). RR 은 뒤 봉우리가 속한 블록에."""
    n = np.zeros(n_blocks, dtype=np.int64)
    s = np.zeros(n_blocks, dtype=np.int64)
    rr = np.diff(peaks)
    blk = peaks[1:] // BLOCK
    m = (blk < n_blocks) & oks
    np.add.at(n, blk[m], 1)
    np.add.at(s, blk[m], rr[m])
    return n, s


def run_ppg(x_codes, n_blocks):
    """칩 규칙: 봉우리 → SQI → 블록 누산. SQI 있음/없음 두 벌."""
    det, sqi = ps.PeakDetector(), ps.SQI()
    acc_sqi, acc_raw = WindowAcc(), WindowAcc()
    n_s = np.zeros(n_blocks, dtype=np.int64); s_s = np.zeros(n_blocks, dtype=np.int64)
    n_r = np.zeros(n_blocks, dtype=np.int64); s_r = np.zeros(n_blocks, dtype=np.int64)
    for v in x_codes:
        p = det.push(int(v))
        if p is not None:
            rr, ok = sqi.push(p)
            if rr is not None:
                acc_sqi.push_rr(rr, ok)
                acc_raw.push_rr(rr, ps.RR_MIN <= rr <= ps.RR_MAX)   # 범위만, 급변 규칙 없음
        for acc, n, s in ((acc_sqi, n_s, s_s), (acc_raw, n_r, s_r)):
            if acc.push_sample():
                k = acc.sample // BLOCK - 1
                if k < n_blocks:
                    n[k] = acc.hist[-1]["n"]; s[k] = acc.hist[-1]["sum_rr"]
    return (n_s, s_s), (n_r, s_r)


def windows(n, s):
    """블록마다 최근 12블록 합. 앞 11블록은 부분 합(칩도 그렇다)."""
    c_n = np.concatenate([[0], np.cumsum(n)]); c_s = np.concatenate([[0], np.cumsum(s)])
    i = np.arange(1, len(n) + 1); j = np.maximum(0, i - W60)
    return c_n[i] - c_n[j], c_s[i] - c_s[j]


def judge(n60, s60, base=None):
    """블록별 (hold, drowsy). base=(base_n, r) 를 주면 그 기준선으로 판정(워밍업 없음).

    DaLiA 는 걷는 구간으로 시작해 첫 3분 PPG 기준선이 망가진다. 기준선 오차와 창 오차를 분리하려고
    ECG 스트림의 기준선을 PPG 쪽에도 같이 쓴다. 반환 셋째 값은 ECG 스트림에서 잡은 기준선.
    """
    n60 = np.minimum(n60, 255); s60 = np.minimum(s60, (1 << 17) - 1)
    ref = InferRef()
    if base is None:
        out = np.array([ref.push(int(a), int(b)) for a, b in zip(n60, s60)])
        return out[:, 0], out[:, 1], (ref.base_n, ref.r)
    base_n, r = base
    hold = (n60 < MIN_N60).astype(int)
    if r == 0:
        return hold, np.zeros(len(n60), dtype=int), base
    drowsy = (((s60.astype(np.int64) * base_n) << ref.frac) >= r * n60.astype(np.int64)).astype(int)
    drowsy = np.where(hold == 1, 0, drowsy)
    return hold, drowsy, base


def process(sub, acc_tbl):
    d = np.load(IN / f"S{sub}.npz")
    fs_bvp = int(d["fs_bvp"]); n_samp = len(d["bvp"]) * FS_PPG // fs_bvp
    n_blocks = n_samp // BLOCK
    a = acc_tbl[acc_tbl.subject == sub].sort_values("t0_s").reset_index(drop=True)
    n_blocks = min(n_blocks, len(a))

    x = ppg_chain(d["bvp"], fs_bvp)[: n_blocks * BLOCK]
    codes = np.round(x).astype(np.int64)             # 진폭 ±300 정도. 문턱은 적응형이라 스케일 무관
    (n_s, s_s), (n_r, s_r) = run_ppg(codes, n_blocks)

    rp = (d["rpeaks"].astype(np.int64) * FS_PPG) // FS_ECG           # 700 Hz 인덱스 → 240 Hz 샘플
    n_e, s_e = blocks_from_peaks(rp, np.ones(len(rp) - 1, dtype=bool), n_blocks)

    blk = pd.DataFrame({
        "subject": sub, "blk": np.arange(n_blocks), "activity": a["activity"].values[:n_blocks],
        "w_motion": a["w_dev_max"].values[:n_blocks], "c_motion": a["c_dev_max"].values[:n_blocks],
        "n_ecg": n_e, "s_ecg": s_e, "n_sqi": n_s, "s_sqi": s_s, "n_raw": n_r, "s_raw": s_r,
    })

    rows = {}
    base = None
    for tag, (n, s) in (("ecg", (n_e, s_e)), ("sqi", (n_s, s_s)), ("raw", (n_r, s_r))):
        n60, s60 = windows(n, s)
        h, dr, base = judge(n60, s60, base)          # ECG 가 먼저 돌아 기준선을 잡고 PPG 둘이 그걸 씀
        rows[f"n60_{tag}"] = n60; rows[f"s60_{tag}"] = s60
        rows[f"hold_{tag}"] = h; rows[f"drowsy_{tag}"] = dr
    win = pd.DataFrame(rows)
    win.insert(0, "subject", sub); win.insert(1, "blk", np.arange(n_blocks))
    win["activity"] = blk["activity"].values
    # 창 안 최대 움직임(최근 12블록)
    win["w_motion_max"] = pd.Series(blk["w_motion"]).rolling(W60, min_periods=1).max().values
    win["c_motion_max"] = pd.Series(blk["c_motion"]).rolling(W60, min_periods=1).max().values
    win["w_motion_blk"] = blk["w_motion"].values
    win["c_motion_blk"] = blk["c_motion"].values
    for tag in ("sqi", "raw"):
        ok = (win[f"n60_{tag}"] >= MIN_N60) & (win["n60_ecg"] >= MIN_N60)
        mean_p = win[f"s60_{tag}"] / win[f"n60_{tag}"].replace(0, np.nan)
        mean_e = win["s60_ecg"] / win["n60_ecg"].replace(0, np.nan)
        win[f"err_{tag}"] = np.where(ok, (mean_p - mean_e) / mean_e, np.nan)
    log(f"S{sub}: {n_blocks} blocks, ECG beats {n_e.sum()}, PPG sqi {n_s.sum()} raw {n_r.sum()}, "
        f"|err| median sqi {np.nanmedian(np.abs(win['err_sqi'])):.4f} raw {np.nanmedian(np.abs(win['err_raw'])):.4f}")
    return blk, win


def report_motion_error(win, blk):
    """텍스트 요약. ⑤ 결정용."""
    warnings.simplefilter("ignore")
    pd.set_option("display.width", 250)
    lines = []
    lab = [f"{MOTION_BINS[i]}~{MOTION_BINS[i+1]}" for i in range(len(MOTION_BINS) - 1)]

    def table(col_motion, title):
        w = win.copy()
        w["bin"] = pd.cut(w[col_motion], MOTION_BINS, labels=lab, right=False)
        valid = w["err_sqi"].notna()
        both = (w["hold_ecg"] == 0) & (w["hold_sqi"] == 0)
        g = w.groupby("bin", observed=False)
        t = pd.DataFrame({
            "창 수": g.size(),
            "PPG hold %": (g["hold_sqi"].mean() * 100).round(1),
            "|오차| 중앙값 % (SQI)": (g.apply(lambda x: np.nanmedian(np.abs(x["err_sqi"])) * 100)).round(2),
            "|오차| p90 % (SQI)": (g.apply(lambda x: np.nanpercentile(np.abs(x["err_sqi"]), 90) if x["err_sqi"].notna().any() else np.nan) * 100).round(2),
            "|오차| 중앙값 % (SQI 없음)": (g.apply(lambda x: np.nanmedian(np.abs(x["err_raw"])) * 100)).round(2),
            "판정 뒤집힘 % (SQI)": (g.apply(lambda x: ((x["drowsy_sqi"] != x["drowsy_ecg"]) & (x["hold_ecg"] == 0) & (x["hold_sqi"] == 0)).sum()
                                          / max(1, ((x["hold_ecg"] == 0) & (x["hold_sqi"] == 0)).sum()) * 100)).round(2),
            "운전 창 %": (g.apply(lambda x: (x["activity"] == 5).sum()) / (w["activity"] == 5).sum() * 100).round(1),
        })
        lines.append(f"\n### {title}\n"); lines.append(t.to_string())

    table("w_motion_max", "손목 움직임(창 안 12블록 최대) 대 60초 창 오차 — PPG 센서 자체 움직임")
    table("w_motion_blk", "손목 움직임(해당 블록만) 대 60초 창 오차")
    table("c_motion_max", "가슴 움직임(창 안 최대) 대 60초 창 오차 — 이마 대용")

    # 보류 정책 시뮬: 문턱 × 범위(해당 블록 / 12블록) → 남는 뒤집힘 %, 보류되는 창 %(전체·운전)
    lines.append("\n### 보류 정책별 결과 (손목 움직임 기준, SQI 있음)\n")
    rows = []
    base = (win["hold_ecg"] == 0) & (win["hold_sqi"] == 0)
    for thr in (None, 0.1, 0.2, 0.3, 0.5, 1.0):
        for scope, col in (("해당 블록", "w_motion_blk"), ("12블록", "w_motion_max")):
            if thr is None and scope == "12블록":
                continue
            held = np.zeros(len(win), dtype=bool) if thr is None else (win[col] >= thr).values
            keep = base & ~held
            flip = ((win["drowsy_sqi"] != win["drowsy_ecg"]) & keep).sum() / max(1, keep.sum()) * 100
            drv = win["activity"] == 5
            rows.append({"문턱 g": "없음" if thr is None else thr, "범위": "-" if thr is None else scope,
                         "남는 뒤집힘 %": round(flip, 2), "판정 가능 창 %": round(keep.sum() / max(1, base.sum()) * 100, 1),
                         "보류 창 % (전체)": round(held.mean() * 100, 1), "보류 창 % (운전)": round(held[drv].mean() * 100, 1)})
    lines.append(pd.DataFrame(rows).to_string(index=False))

    lines.append("\n### 활동별 (SQI 있음)\n")
    g = win.groupby("activity")
    t = pd.DataFrame({"창 수": g.size(), "PPG hold %": (g["hold_sqi"].mean() * 100).round(1),
                      "|오차| 중앙값 %": (g.apply(lambda x: np.nanmedian(np.abs(x["err_sqi"])) * 100)).round(2),
                      "뒤집힘 %": (g.apply(lambda x: ((x["drowsy_sqi"] != x["drowsy_ecg"]) & (x["hold_ecg"] == 0) & (x["hold_sqi"] == 0)).sum()
                                     / max(1, ((x["hold_ecg"] == 0) & (x["hold_sqi"] == 0)).sum()) * 100)).round(2)})
    t.index = [ACT.get(i, i) for i in t.index]
    lines.append(t.to_string())
    return "\n".join(lines)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    acc = pd.read_csv(IN / "acc_blocks.csv")
    subs = [int(s) for s in sys.argv[1:]] or list(range(1, 16))
    blks, wins = [], []
    for s in subs:
        b, w = process(s, acc)
        blks.append(b); wins.append(w)
    blk = pd.concat(blks, ignore_index=True); win = pd.concat(wins, ignore_index=True)
    blk.to_csv(OUT / "blocks.csv", index=False); win.to_csv(OUT / "windows.csv", index=False)
    rep = report_motion_error(win, blk)
    (OUT / "motion_error.md").write_text(rep, encoding="utf-8")
    print(rep)
    log("ALL DONE")


if __name__ == "__main__":
    main()
