"""5단계 본론: 같은 사람의 흉골 ECG(우리 검출기)와 이마 PPG(준용 v14 검출기)에서 칩 방식 mean_rb 를 나란히 낸다.

두 경로 모두 칩과 같은 절차를 밟는다:
  ECG → AFE 흉내(0.16~40 Hz, 학습 파이프라인과 동일) → 240 Hz → 코드 → 우리 peak_detect/SQI → 5초 블록 → 60초 창 (n60, sum_rr60)
  PPG → AFE 흉내(0.16~16 Hz, 보드) → 240 Hz → 코드(2초 창 p-p 중앙값 238) → 준용 v14 골든 → 5초 블록 → 60초 창
그 뒤 src.infer_ref.InferRef(T_FIX 1086)로 워밍업(첫 3분 창 합 셋, N_base ≥ 45)·hold·drowsy 를 칩 그대로 굴리고,
둘 다 판정한 블록에서 mean_rb_PPG ÷ mean_rb_ECG − 1 의 치우침·흔들림, 그리고 drowsy 판정 일치율을 낸다.

    .venv/Scripts/python.exe scripts/wildppg_meanrb.py data/raw/wildppg/WildPPG_Part_an0.mat [more.mat ...] [--start-min 10] [--hours H]

결과 data/processed/stage5/wildppg_meanrb.md (참가자별 + 합산).
"""

import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, resample_poly

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.peak_simple import detect, to_codes, FS  # noqa: E402
from src.window_acc import WindowAcc, BLOCK  # noqa: E402
from src.infer_ref import InferRef, T_FIX, FRAC  # noqa: E402
from src.mpd_io import AFE_HP_HZ, AFE_LP_HZ  # noqa: E402
from scripts.compare_detectors import jy_detect  # noqa: E402
from scripts.wildppg_detectors import load_participant, to_240, to_codes_pp  # noqa: E402

OUT = ROOT / "data" / "processed" / "stage5" / "wildppg_meanrb.md"
T_REAL = T_FIX / (1 << FRAC)

# 준용 imu_feature.v 의 모션 에너지 (sim/motion_gate.py 와 같은 정수 연산). rr_extractor 조건 4: motion_energy > MOTION_TH 면 박동 탈락
GRAV_SH, LPF_SH, MOT_WIN, MOT_SH, MOTION_TH, LSB_G, ODR = 6, 2, 100, 6, 4000, 16384.0, 100


def motion_energy(A):
    """A: (3, n) int64, 16384 LSB/g, 100 Hz. imu_feature 와 같은 연산."""
    n = A.shape[1]
    gv = A[:, 0].astype(np.int64).copy(); f = np.zeros(3, dtype=np.int64)
    buf = np.zeros(MOT_WIN, dtype=np.int64); ptr, msum, prime = 0, 0, False
    out = np.zeros(n, dtype=np.int64)
    for i in range(n):
        a = A[:, i]
        gv = gv + ((a - gv) >> GRAV_SH)
        f = f + (((a - gv) - f) >> LPF_SH)
        v = np.sort(np.abs(f))[::-1]
        amag = int(v[0] + (v[1] >> 1) + (v[2] >> 2))
        msum = msum + amag - (int(buf[ptr]) if prime else 0)
        buf[ptr] = amag; ptr += 1
        if ptr == MOT_WIN:
            ptr, prime = 0, True
        out[i] = 0 if not prime else min(msum >> MOT_SH, 65535)
    return out


def head_motion_gate(P, s0, s1, n_ecg, fs):
    """이마 IMU → 100 Hz, 16384 LSB/g(긴 구간 벡터 크기 중앙값 = 1 g 로 역산) → motion_energy → 240 Hz 샘플별 게이트."""
    imu = np.stack([P["head"][k]["v"].astype(float)[s0:s1][:n_ecg] for k in ("acc_x", "acc_y", "acc_z")])
    lsb = float(np.median(np.sqrt((imu ** 2).sum(0))))
    imu = imu * (LSB_G / lsb)
    from math import gcd
    g = gcd(int(fs), ODR)
    imu = np.stack([resample_poly(imu[j], ODR // g, int(fs) // g) for j in range(3)])
    me = motion_energy(np.clip(np.round(imu), -32768, 32767).astype(np.int64))
    n240 = int(n_ecg * FS / fs)
    idx = np.minimum(np.arange(n240) * ODR // FS, len(me) - 1)
    return me[idx] > MOTION_TH, me


def ecg_chain(ecg, fs):
    """학습 파이프라인(src.mpd_io.load_ecg_as_ppg_chain)과 같은 대역·리샘플·코드화."""
    sos_hp = butter(1, AFE_HP_HZ, btype="high", fs=fs, output="sos")
    sos_lp = butter(1, AFE_LP_HZ, btype="low", fs=fs, output="sos")
    y = sosfiltfilt(sos_lp, sosfiltfilt(sos_hp, np.asarray(ecg, float)))
    from math import gcd
    g = gcd(int(fs), FS)
    y = resample_poly(y, FS // g, int(fs) // g)
    # WildPPG ECG 단위는 mV 가 아니므로 R 봉우리 높이가 학습 데이터(수백 코드)와 비슷해지게 맞춘다
    scale = 400.0 / max(np.percentile(np.abs(y), 99.5), 1e-9)
    return np.clip(np.round(y * scale), -2047, 2047).astype(np.int64)


def block_materials(rr_at, rr, ok, n_samples):
    """봉우리 위치 기준 5초 블록 배정 → 블록마다 (n60, sum_rr60, bad60). bad60 = 최근 12블록의 탈락 박동 수(준용 o_bad60)."""
    nblk = n_samples // BLOCK
    per = {}
    for p, r, o in zip(rr_at, rr, ok):
        b = int(p) // BLOCK
        if b < nblk:
            per.setdefault(b, []).append((int(r), bool(o)))
    acc = WindowAcc()
    out, bad = [], []
    for b in range(nblk):
        nb_bad = 0
        for r, o in per.get(b, []):
            acc.push_rr(r, o)
            nb_bad += (not o)
        bad.append(nb_bad)
        acc.sample = (b + 1) * BLOCK - 1
        acc.push_sample()
        out.append((int(acc.win60["n"]), int(acc.win60["sum_rr"]), int(sum(bad[max(0, b - 11):b + 1]))))
    return out


def run_chip(mats, keep=0.0, base_keep=0.0, base_blocks=None):
    """칩 절차를 블록마다 굴려 (hold, drowsy, mean_rb 또는 nan, base_n, base_sum) 목록과 기준선에 쓴 블록 번호를 낸다.
    기본(0, 0, None): InferRef 와 같다 — 12·24·36번째 블록의 60초 창 합 셋, N_base ≥ 45 아니면 재시작.
    base_keep > 0 : B 방식 — 워밍업 중 12블록(1분)마다 창 하나를 보고, n60 ≥ 30 이고 살린 비율 ≥ base_keep 인
                    창만 기준선에 더한다. 좋은 창 3개가 모이면 완성.
    keep > 0      : 판정 중 살린 비율 < keep 인 블록을 추가 hold.
    base_blocks   : 기준선을 이 블록들의 창 합으로 강제(ECG 쪽을 PPG 와 같은 시점 기준선으로 맞출 때)."""
    T = T_FIX / (1 << FRAC)
    rows = []
    warm = 0; base_n = base_sum = 0; used = []; ready = False
    for b, (n60, s60, b60) in enumerate(mats):
        kr = n60 / max(n60 + b60, 1)
        if not ready:
            warm += 1
            if base_blocks is not None:
                if b in base_blocks:
                    base_n += n60; base_sum += s60; used.append(b)
                ready = len(used) == len(base_blocks)
            elif warm % 12 == 0:
                if base_keep > 0:
                    if n60 >= 30 and kr >= base_keep:
                        base_n += n60; base_sum += s60; used.append(b)
                    ready = len(used) == 3
                else:
                    base_n += n60; base_sum += s60; used.append(b)
                    if len(used) == 3:
                        if base_n >= 45:
                            ready = True
                        else:
                            warm = 0; base_n = base_sum = 0; used = []
            rows.append((1, 0, np.nan, base_n, base_sum)); continue
        hold = n60 < 30 or (keep > 0 and kr < keep) or base_n == 0 or base_sum == 0
        if hold or n60 == 0:
            rows.append((1, 0, np.nan, base_n, base_sum))
        else:
            mrb = (s60 / n60) * base_n / base_sum
            rows.append((0, int(mrb >= T), mrb, base_n, base_sum))
    return rows, used


def stats(d):
    d = np.asarray(d, float)
    if len(d) == 0:
        return dict(n=0)
    return dict(n=len(d), med=100 * np.median(d), q1=100 * np.percentile(d, 25), q3=100 * np.percentile(d, 75),
                sd=100 * d.std(), gt1=100 * (np.abs(d) > 0.01).mean(), gt2=100 * (np.abs(d) > 0.02).mean(),
                gt4=100 * (np.abs(d) > 0.04).mean())


def analyze(path, start_min=0.0, hours=None, keep=0.0, base_keep=0.0):
    t0 = time.time()
    P = load_participant(path)
    fs = P["sternum"]["ecg"]["fs"]
    s0 = int(start_min * 60 * fs)
    s1 = int(s0 + hours * 3600 * fs) if hours else None
    ecg = P["sternum"]["ecg"]["v"].astype(float)[s0:s1]
    ppg = P["head"]["ppg_g"]["v"].astype(float)[s0:s1]
    n = min(len(ecg), len(ppg)); ecg, ppg = ecg[:n], ppg[:n]

    # 정지 여부(이마 가속도 60초 창 표준편차 하위 절반) — 블록(5초) 단위로 펼친다
    acc = np.sqrt(sum(P["head"][k]["v"].astype(float)[s0:s1][:n] ** 2 for k in ("acc_x", "acc_y", "acc_z")))
    w = int(60 * fs); nw = len(acc) // w
    sd = np.array([acc[i * w:(i + 1) * w].std() for i in range(nw)])
    still_min = sd <= np.percentile(sd, 25)          # 가장 조용한 25% 분 = 착석에 대응(준용 motion_gate.py 와 같은 정의)
    g1 = float(np.median(acc))                       # 긴 구간 벡터 크기 중앙값 = 1 g
    seat_min = sd / g1 < 0.02                        # 절대 기준: 분당 표준편차 0.02 g 미만 (DaLiA 앉기 0.017 g, 운전 0.16 g p95)
    mot_bad, me100 = head_motion_gate(P, s0, s1, n, fs)

    # ECG → 우리 검출기
    ce = ecg_chain(ecg, fs)
    pe, rre, oke = detect(ce)
    me = block_materials(pe[1:], rre, oke, len(ce))
    # PPG → 준용 v14 검출기 (보드 극성: −)
    yp = to_240(ppg, fs)
    cp, _ = to_codes_pp(-yp)
    pp, at, rrp, okp = jy_detect(cp, fix_prev=True, use_lpf=True, mot_bad=mot_bad)
    mp = block_materials(at, rrp, okp, len(cp))

    nb = min(len(me), len(mp))
    rp, used_p = run_chip(mp[:nb], keep, base_keep)
    # ECG(참값 쪽)는 PPG 가 기준선으로 쓴 것과 같은 창으로 기준선을 잡는다. 안 그러면 두 기준선의 시점이 달라
    # 시간 경과에 따른 심박 하강이 차이로 섞인다. 기준선 창이 없으면(끝내 못 잡음) ECG 는 기본 절차.
    re, used_e = run_chip(me[:nb], base_blocks=set(used_p)) if used_p and len(used_p) == 3 else run_chip(me[:nb])
    base_delay_min = (used_p[-1] + 1) * 5 / 60 if len(used_p) == 3 else float("nan")
    both = [(e, p, b) for b, (e, p) in enumerate(zip(re, rp)) if e[0] == 0 and p[0] == 0]
    d = [p[2] / e[2] - 1 for e, p, b in both]
    # 기준선을 뺀 창 평균 RR 만의 차이 (sum60/n60 비율) — 창 오차와 기준선 오차를 분리
    dw = [(mp[b][1] / mp[b][0]) / (me[b][1] / me[b][0]) - 1 for e, p, b in both]
    still = np.array([still_min[min(b // 12, nw - 1)] for e, p, b in both], bool) if nw else np.zeros(len(both), bool)
    seat = np.array([seat_min[min(b // 12, nw - 1)] for e, p, b in both], bool) if nw else np.zeros(len(both), bool)
    agree = np.array([e[1] == p[1] for e, p, b in both], bool)
    de = np.array([e[1] for e, p, b in both], bool); dp = np.array([p[1] for e, p, b in both], bool)
    r = dict(
        id=P["id"], hours=nb * 5 / 3600, n_blocks=nb,
        hold_e=100 * np.mean([x[0] for x in re]), hold_p=100 * np.mean([x[0] for x in rp]),
        both=len(both), all=stats(d), still=stats(np.array(d)[still]) if len(both) else dict(n=0),
        seat=stats(np.array(d)[seat]) if len(both) else dict(n=0), seat_agree=100 * agree[seat].mean() if seat.any() else np.nan,
        agree=100 * agree.mean() if len(both) else np.nan,
        drowsy_e=100 * de.mean() if len(both) else np.nan, drowsy_p=100 * dp.mean() if len(both) else np.nan,
        base_e=(re[-1][3], re[-1][4]), base_p=(rp[-1][3], rp[-1][4]),
        base_rr_e=re[-1][4] / max(re[-1][3], 1), base_rr_p=rp[-1][4] / max(rp[-1][3], 1),
        d=np.array(d), dw=stats(dw), still_mask=still, seat_mask=seat, sec=time.time() - t0, base_delay=base_delay_min,
    )
    return r


def fmt_row(r):
    a, s = r["all"], r["still"]
    return (f"| {r['id']} | {r['hours']:.1f} | {r['hold_e']:.0f} / {r['hold_p']:.0f} | {r['both']} | "
            f"{a.get('med', np.nan):+.2f} | {a.get('q1', np.nan):+.2f} ~ {a.get('q3', np.nan):+.2f} | {a.get('sd', np.nan):.2f} | "
            f"{a.get('gt1', np.nan):.0f} / {a.get('gt2', np.nan):.0f} / {a.get('gt4', np.nan):.0f} | "
            f"{s.get('med', np.nan):+.2f} / {s.get('sd', np.nan):.2f} | {r['agree']:.1f} | {r['drowsy_e']:.1f} / {r['drowsy_p']:.1f} | "
            f"{r['base_rr_e']:.1f} / {r['base_rr_p']:.1f} | {r['dw'].get('med', np.nan):+.2f} / {r['dw'].get('sd', np.nan):.2f} | "
            f"{r['seat'].get('n', 0)}: {r['seat'].get('med', np.nan):+.2f} / {r['seat'].get('sd', np.nan):.2f} / {r['seat_agree']:.0f} | {r['base_delay']:.1f} |")


def main(argv):
    paths = [a for a in argv if a.endswith(".mat")]
    start_min = float(argv[argv.index("--start-min") + 1]) if "--start-min" in argv else 0.0
    hours = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else None
    keep = float(argv[argv.index("--keep") + 1]) if "--keep" in argv else 0.0
    base_keep = float(argv[argv.index("--base-keep") + 1]) if "--base-keep" in argv else 0.0
    hdr = ["| 참가자 | 시간(h) | hold% ECG/PPG | 둘 다 판정 블록 | 차이 중앙% | 사분위 | 표준편차% | \\|차이\\|>1/2/4% 블록% | 정지: 중앙/표준편차 | 판정 일치% | drowsy% ECG/PPG | 기준선 RR ECG/PPG | 창 평균 RR만: 중앙/표준편차 | 앉기(<0.02 g) 블록: 중앙/표준편차/일치% | 기준선 완성(분) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    rows, allD, allS, allSeat, agrees = [], [], [], [], []
    for p in paths:
        r = analyze(p, start_min, hours, keep, base_keep)
        rows.append(fmt_row(r)); allD.append(r["d"]); allS.append(r["d"][r["still_mask"]]); allSeat.append(r["d"][r["seat_mask"]]); agrees.append((r["agree"], r["both"]))
        print(rows[-1], f"({r['sec']:.0f}s)", flush=True)
    D = np.concatenate(allD) if allD else np.array([]); S = np.concatenate(allS) if allS else np.array([])
    Se = np.concatenate(allSeat) if allSeat else np.array([])
    A, St, Sa = stats(D), stats(S), stats(Se)
    wa = sum(a * n for a, n in agrees if np.isfinite(a)) / max(sum(n for a, n in agrees if np.isfinite(a)), 1)
    lines = [f"# 5단계: ECG(우리 검출기) 대 이마 PPG(준용 v14) 60초 창 mean_rb — WildPPG {len(paths)}명" + (f" (PPG 살린 비율 ≥ {keep:.2f} 추가 hold)" if keep else "") + (f" (기준선 창 살린 비율 ≥ {base_keep:.2f} 아니면 재시작)" if base_keep else ""), "",
             f"차이 = mean_rb_PPG ÷ mean_rb_ECG − 1 (5초 블록마다, 둘 다 판정한 블록만). 워밍업·hold·기준선은 칩(InferRef, T_FIX {T_FIX}) 그대로. "
             f"시작 오프셋 {start_min:.0f}분. 정지 = 이마 가속도 60초 창 표준편차 하위 25%(착석 대응). PPG 경로에는 준용 모션 게이트(motion_energy > 4000 박동 탈락) 포함. 판정 일치 = 문턱 {T_REAL:.4f}에서 drowsy 가 같은 블록 비율.", "",
             *hdr, *rows, "",
             f"**합산 {len(paths)}명, 블록 {A.get('n', 0)}개:** 차이 중앙 {A.get('med', np.nan):+.2f}%, 사분위 {A.get('q1', np.nan):+.2f}~{A.get('q3', np.nan):+.2f}%, "
             f"표준편차 {A.get('sd', np.nan):.2f}%, |차이|>1% {A.get('gt1', np.nan):.0f}% · >2% {A.get('gt2', np.nan):.0f}% · >4% {A.get('gt4', np.nan):.0f}%. "
             f"정지(하위 25%) 블록 {St.get('n', 0)}개: 중앙 {St.get('med', np.nan):+.2f}%, 표준편차 {St.get('sd', np.nan):.2f}%. "
             f"앉기(<0.02 g) 블록 {Sa.get('n', 0)}개: 중앙 {Sa.get('med', np.nan):+.2f}%, 표준편차 {Sa.get('sd', np.nan):.2f}%, |차이|>2% {Sa.get('gt2', np.nan):.0f}%. 판정 일치 {wa:.1f}%.",
             "", "비교 기준: 졸음이 만드는 mean_rb 변화 1.3%, 각성 중 사람 안 흔들림 4.0%(설계서). WildPPG는 각성·야외 활동 기록이라 졸음 라벨 없음 → 특징 전이까지만."]
    out = OUT.with_name(f"wildppg_meanrb_start{int(start_min)}" + (f"_keep{int(keep * 100)}" if keep else "") + (f"_base{int(base_keep * 100)}" if base_keep else "") + ".md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines[-3:]))
    print(f"→ {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
