"""준용 검출기(v13 골든 모델) vs 우리 검출기, MPD-DF 50명 ECG에서 같은 잣대로 채점.

두 검출기를 같은 입력(AFE 대역 ECG → 240 Hz → 정수 코드, ±2047 클립)에 넣고
  1) 봉우리 놓침·오검출 (src/peak_eval, ±12샘플)
  2) 60초 창마다 '통과 RR의 평균' 대 '정답 RR의 평균' 편향 (%)  ← 판정식 sum_rr60/n60 이 쓰는 값
  3) 창 커버리지 (n ≥ 30 인 창 비율)
를 낸다. 준용 체인은 sim/make_ppg_stim.py 의 골든 모델을 옮긴 것(HPF 512 이동평균 →
FIR LPF 8 Hz 132탭 → signal_quality → peak_detector → rr_extractor). 봉우리 위치는
체인 고정 지연(256 + 66 = 322샘플)을 빼고 정답과 맞춘다.

    .venv/Scripts/python.exe scripts/compare_detectors.py            # 전원
    .venv/Scripts/python.exe scripts/compare_detectors.py 02 05      # 일부
    .venv/Scripts/python.exe scripts/compare_detectors.py --fix-prev # 준용 검출기에 prev_idx 수정 적용

준용 RR 출력은 data/interim/rr_jy/{sid}.npz 에 저장한다 (peaks, rr, ok, gt).
표는 data/processed/stage1/detector_compare.md.
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mpd_io import load_ecg_as_ppg_chain, subject_ids  # noqa: E402
from src.peak_simple import to_codes, FS  # noqa: E402
from src.peak_eval import summarize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OURS = ROOT / "data" / "interim" / "rr"
OUT_JY = ROOT / "data" / "interim" / "rr_jy"
OUT_MD = ROOT / "data" / "processed" / "stage1" / "detector_compare.md"

# ---- 준용 v13 상수 (sim/make_ppg_stim.py 와 동일) ----
LOG2N = 9; N_MA = 1 << LOG2N; CENTER = N_MA >> 1
REFRACTORY = 48; DECAY_SH = 8; THR_MIN = 6; SEARCH_LEN = 40; NOPEAK_LIM = 400; GUARD_LEN = 120
RR_MIN, RR_MAX = 72, 360; REJ_LIM = 3
WIN_SQ = 480; PP_MIN = 10; PP_GOOD = 120; BASE_WIN = 90; BASE_MIN = 40
NTAP = 132; FC_LPF = 8.0
WARM_N = 644
CHAIN_DELAY = CENTER + NTAP // 2        # 322


def jy_hpf(x):
    """ppg_dc_remover: y[n] = x[n-256] - (Σ x[n-511..n] >> 9). 골든의 리스트 루프를 누적합으로."""
    x = np.asarray(x, dtype=np.int64)
    pad = np.concatenate([np.zeros(N_MA, np.int64), x])
    cs = np.concatenate([[0], np.cumsum(pad)])
    n = np.arange(len(x)) + N_MA
    s = cs[n + 1] - cs[n + 1 - N_MA]                 # x[n-511..n]
    ctr = pad[n - CENTER]
    return np.clip(ctr - (s >> LOG2N), -32768, 32767)


def jy_lpf_coefs():
    M, H = NTAP - 1, NTAP // 2
    n = np.arange(NTAP); fc = FC_LPF / FS
    h = 2 * fc * np.sinc(2 * fc * (n - M / 2.0)) * (0.54 - 0.46 * np.cos(2 * np.pi * n / M))
    h = h / np.sum(h)
    half = np.round(h[:H] * 32768).astype(np.int64)
    q = np.concatenate([half, half[::-1]])
    d = (32768 - q.sum()) // 2
    q[H - 1] += d; q[H] += d
    return q


def jy_lpf(x):
    acc = np.convolve(np.asarray(x, np.int64), jy_lpf_coefs())[:len(x)]
    return np.clip(acc >> 15, -32768, 32767).astype(np.int64)


def jy_sq(y):
    ok = np.zeros(len(y), dtype=bool)
    vmin, vmax = 32767, -32768
    w, have, pp = 0, False, 0
    pp_base, base_cnt, base_ready = 0, 0, False
    for n, v in enumerate(y):
        v = int(v)
        ok[n] = have and pp >= PP_MIN and n >= WARM_N
        vmin, vmax = min(vmin, v), max(vmax, v)
        if w >= WIN_SQ - 1:
            pp, have, w = vmax - vmin, True, 0
            vmin = vmax = v
            if not base_ready and pp >= PP_MIN:
                pp_base = pp if base_cnt == 0 else pp_base - (pp_base >> 3) + (pp >> 3)
                if base_cnt >= BASE_WIN - 1:
                    if pp_base >= BASE_MIN: base_ready = True
                    else: base_cnt = 0
                else:
                    base_cnt += 1
        else:
            w += 1
    return ok


def jy_peaks(y, ok):
    thr, spk, refr, nopk, guard = THR_MIN, 0, 0, 0, 0
    have_spk, st = False, 0
    mx, mx_idx, slen = 0, 0, 0
    out = []
    for n, v in enumerate(y):
        v = int(v)
        if not ok[n]:
            st, refr, guard = 0, 0, 0
            continue
        if nopk > NOPEAK_LIM and spk > 0:
            spk = spk - (spk >> 5) if (spk >> 5) > 0 else 0
        lo = (spk >> 1) + (spk >> 3) if guard > 0 else (spk >> 2) + (spk >> 3)
        if lo < THR_MIN: lo = THR_MIN
        dec = thr >> DECAY_SH
        if dec <= 0: dec = 1
        thr = thr - dec if (thr - dec) > lo else lo
        if nopk < 65535: nopk += 1
        if guard > 0: guard -= 1
        if st == 0:
            if refr > 0: refr -= 1
            else: st = 1
        elif st == 1:
            if v > thr:
                mx, mx_idx, slen, st = v, n, 0, 2
        else:
            if v > mx: mx, mx_idx = v, n
            slen += 1
            if (v < thr) or (slen >= SEARCH_LEN):
                out.append((mx_idx, mx, n))
                refr, st, nopk, guard = REFRACTORY, 0, 0, GUARD_LEN
                if not have_spk: spk, have_spk = mx, True
                elif mx > spk: spk = spk + ((mx - spk) >> 2)
                else: spk = spk + ((mx - spk) >> 4)
                tn = (spk >> 1) + (spk >> 3)
                thr = tn if tn > THR_MIN else THR_MIN
    return out


def jy_rr(peaks, ok, fix_prev=False, amp_rule=False, mot_bad=None):
    """rr_extractor. fix_prev=True 면 RR<RR_MIN 탈락 시 prev_idx 를 갱신하지 않는다(v14 반영).
    amp_rule=True 면 급변 탈락이면서 새 봉우리 높이가 기준 봉우리(prev_idx 자리, last_amp)의 절반 미만일 때도
    가짜로 보고 prev_idx·last_amp 를 갱신하지 않는다(C 안). 짧은 탈락이 아닌 T파·중복맥(RR≥72)을 겨냥."""
    prev_idx, have_prev = 0, False
    last_rr, have_last = 0, False
    rr_ref, have_ref, rejrun = 0, False, 0
    last_amp = 0
    rows = []
    for (pidx, pamp, n) in peaks:
        if not have_prev:
            prev_idx, have_prev, last_amp = pidx, True, pamp
            continue
        rr = pidx - prev_idx
        range_bad = (rr > RR_MAX) or (rr < RR_MIN)
        base = last_rr if have_last else rr_ref
        mul = 4 if have_last else 2
        jump_bad = ((have_last or have_ref) and base != 0 and abs(rr - base) * mul > base)
        motion = bool(mot_bad[n]) if mot_bad is not None and n < len(mot_bad) else False
        rej = bool(range_bad or jump_bad or (not ok[n]) or motion)
        rows.append((pidx, rr, rej))
        spurious = (fix_prev and rr < RR_MIN) or                    (amp_rule and jump_bad and not range_bad and last_amp > 0 and pamp * 2 < last_amp)
        if not spurious:
            prev_idx, last_amp = pidx, pamp
        if rej:
            have_last = False
            if rejrun >= REJ_LIM: have_ref, rejrun = False, 0
            else: rejrun += 1
        else:
            rejrun = 0
            last_rr, have_last = rr, True
            rr_ref = (rr_ref - (rr_ref >> 2) + (rr >> 2)) if have_ref else rr
            have_ref = True
    return rows


def jy_detect(codes, fix_prev=False, use_lpf=True, amp_rule=False, mot_bad=None):
    """use_lpf=False 면 8 Hz FIR 을 빼고 HPF 출력을 바로 검출기에 넣는다(우리와 같은 40 Hz 대역).
    ECG 는 R파 성분이 40 Hz 근처라 8 Hz LPF 가 R을 T파 크기로 깎는다(mpd_io 참고). PPG 에는 없는 왜곡."""
    h = jy_hpf(codes)
    y = jy_lpf(h) if use_lpf else h
    delay = CHAIN_DELAY if use_lpf else CENTER
    ok = jy_sq(y)
    pk = jy_peaks(y, ok)
    rows = jy_rr(pk, ok, fix_prev, amp_rule, mot_bad)
    peaks = np.array([p[0] for p in pk]) - delay
    rr_at = np.array([r[0] for r in rows]) - delay   # RR 이 확정된 봉우리 위치
    rr = np.array([r[1] for r in rows]); okr = np.array([not r[2] for r in rows], bool)
    return peaks, rr_at, rr, okr


def window_bias(rr_at, rr, okr, gt, n_samples, win=60 * FS):
    """비겹침 60초 창마다 통과 RR 평균 / 정답 RR 평균 - 1. (창의 편향 %, n) 목록."""
    gt = np.asarray(gt); gt_rr = np.diff(gt); gt_at = gt[1:]
    out = []
    for s in range(WARM_N + 3 * 60 * FS, n_samples - win, win):   # 앞 3분(워밍업)은 뺀다
        e = s + win
        m = (rr_at >= s) & (rr_at < e) & okr
        g = (gt_at >= s) & (gt_at < e)
        n = int(m.sum())
        if g.sum() < 20:
            continue
        gm = gt_rr[g].mean()
        out.append((100 * (rr[m].mean() / gm - 1) if n else np.nan, n))
    return out


def peak_offset(peaks, gt):
    """검출 봉우리와 가장 가까운 정답의 차이 중앙값(샘플). 체인 지연 보정이 맞는지 확인용."""
    j = np.clip(np.searchsorted(gt, peaks), 1, len(gt) - 1)
    d = np.minimum(np.abs(gt[j] - peaks), np.abs(gt[j - 1] - peaks))
    sgn = np.where(np.abs(gt[j] - peaks) <= np.abs(gt[j - 1] - peaks), peaks - gt[j], peaks - gt[j - 1])
    return float(np.median(sgn[d <= 30]))


def run(sid, fix_prev, use_lpf=True, amp_rule=False):
    x = load_ecg_as_ppg_chain(sid, FS)
    codes = np.clip(to_codes(x), -2047, 2047)
    d = np.load(OURS / f"{sid}.npz")
    gt = d["gt"]
    # 준용
    p_j, at_j, rr_j, ok_j = jy_detect(codes, fix_prev, use_lpf, amp_rule)
    s_j = summarize(p_j, rr_j, ok_j, gt)
    b_j = window_bias(at_j, rr_j, ok_j, gt, len(codes))
    OUT_JY.mkdir(parents=True, exist_ok=True)
    np.savez(OUT_JY / f"{sid}.npz", peaks=p_j, rr_at=at_j, rr=rr_j, ok=ok_j, gt=gt)
    # 우리 (1단계 결과 그대로. rr/ok 는 peaks[1:] 에 대응)
    p_o = d["peaks"]; rr_o = d["rr"]; ok_o = d["ok"]
    s_o = summarize(p_o, rr_o, ok_o, gt)
    b_o = window_bias(p_o[1:], rr_o, ok_o, gt, len(codes))
    return dict(sid=sid, jy=s_j, ours=s_o, bias_jy=b_j, bias_ours=b_o,
                off_jy=peak_offset(p_j, gt), off_ours=peak_offset(p_o, gt))


def agg(bias_lists):
    b = np.array([v for lst in bias_lists for v, n in lst], float)
    n = np.array([n for lst in bias_lists for v, n in lst], float)
    ok = ~np.isnan(b)
    return dict(n_win=len(b), med=np.nanmedian(b), q1=np.nanpercentile(b[ok], 25), q3=np.nanpercentile(b[ok], 75),
                sd=np.nanstd(b), cover=100 * (n >= 30).mean(), abs1=100 * (np.abs(b[ok]) > 1.0).mean())


def main(argv):
    fix_prev = "--fix-prev" in argv
    use_lpf = "--no-lpf" not in argv
    amp_rule = "--amp-rule" in argv
    sids = [a for a in argv if not a.startswith("--")] or subject_ids()
    t0 = time.time(); rows = []
    tag = ("prev_idx 수정" if fix_prev else "v13 그대로") + (" + 진폭 규칙(C)" if amp_rule else "") + ("" if use_lpf else ", 8 Hz LPF 없음")
    print(f"준용 검출기 = {tag}")
    print(f"{'sid':>4} | {'놓침% 준용':>9} {'우리':>6} | {'오검출% 준용':>10} {'우리':>6} | {'창편향% 중앙 준용':>14} {'우리':>6} | {'커버% 준용':>9} {'우리':>6}")
    for sid in sids:
        r = run(sid, fix_prev, use_lpf, amp_rule); rows.append(r)
        aj, ao = agg([r["bias_jy"]]), agg([r["bias_ours"]])
        print(f"{sid:>4} | {r['jy']['miss_pct']:9.2f} {r['ours']['miss_pct']:6.2f} | {r['jy']['fp_pct']:10.2f} {r['ours']['fp_pct']:6.2f} | "
              f"{aj['med']:14.2f} {ao['med']:6.2f} | {aj['cover']:9.1f} {ao['cover']:6.1f} | 지연잔차 {r['off_jy']:+.0f}/{r['off_ours']:+.0f}", flush=True)

    def pooled(key, det):
        gt = sum(r[det]["n_gt"] for r in rows); miss = sum(r[det]["miss"] for r in rows)
        det_n = sum(r[det]["n_det"] for r in rows); fp = sum(r[det]["fp"] for r in rows)
        return 100 * miss / gt, 100 * fp / det_n
    mj, fj = pooled("miss", "jy"); mo, fo = pooled("miss", "ours")
    AJ = agg([r["bias_jy"] for r in rows]); AO = agg([r["bias_ours"] for r in rows])
    lines = [f"# 검출기 비교 (MPD-DF {len(rows)}명, 준용 = {tag})", "",
             "| | 준용 v13 | 우리 |", "|---|---|---|",
             f"| 놓침 (pooled) | {mj:.2f}% | {mo:.2f}% |",
             f"| 오검출 (pooled) | {fj:.2f}% | {fo:.2f}% |",
             f"| 60초 창 평균 RR 편향, 중앙값 | {AJ['med']:+.2f}% | {AO['med']:+.2f}% |",
             f"| 창 편향 사분위 | {AJ['q1']:+.2f} ~ {AJ['q3']:+.2f}% | {AO['q1']:+.2f} ~ {AO['q3']:+.2f}% |",
             f"| 창 편향 표준편차 | {AJ['sd']:.2f}% | {AO['sd']:.2f}% |",
             f"| \\|편향\\| > 1% 인 창 | {AJ['abs1']:.1f}% | {AO['abs1']:.1f}% |",
             f"| 커버리지 (n60 ≥ 30) | {AJ['cover']:.1f}% | {AO['cover']:.1f}% |",
             f"| 창 수 | {AJ['n_win']} | {AO['n_win']} |", "",
             "편향 = (통과 RR 평균 ÷ neurokit 정답 RR 평균 − 1). 첫 3분 제외, 비겹침 60초 창. "
             "입력은 둘 다 AFE 대역 ECG → 240 Hz → ±2047 코드. 준용 봉우리는 체인 지연 322샘플 보정.", ""]
    lines += ["| sid | 놓침% 준용 | 우리 | 오검출% 준용 | 우리 | 창편향% 준용 | 우리 | 커버% 준용 | 우리 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        aj, ao = agg([r["bias_jy"]]), agg([r["bias_ours"]])
        lines.append(f"| {r['sid']} | {r['jy']['miss_pct']:.2f} | {r['ours']['miss_pct']:.2f} | {r['jy']['fp_pct']:.2f} | {r['ours']['fp_pct']:.2f} | "
                     f"{aj['med']:+.2f} | {ao['med']:+.2f} | {aj['cover']:.0f} | {ao['cover']:.0f} |")
    out = OUT_MD.with_name(OUT_MD.stem + ("_fixprev" if fix_prev else "") + ("_amp" if amp_rule else "") + ("" if use_lpf else "_nolpf") + ".md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines[:12]))
    print(f"\n{len(rows)}명 {time.time() - t0:.0f}s → {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
