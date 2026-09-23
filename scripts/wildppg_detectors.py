"""이마 PPG(WildPPG 원본, 128 Hz)에서 두 검출기를 같은 잣대로 채점.

준용은 v13 검증에 이마 PPG 실데이터 1명을 썼지만 우리 검출기는 이마에서 돌려 본 적이 없다.
여기서는 WildPPG(ETH, 이마 PPG + 흉골 ECG, 13시간/명)를 받아
  이마 PPG → 보드 AFE 흉내(HP 0.16 Hz, LP 16 Hz) → 240 Hz → 코드(2초 창 p-p 중앙값 = TARGET_PP) → ±2047
를 두 검출기(+ 극성 ±)에 넣고, 정답은 흉골 ECG 의 neurokit R 봉우리로 잡는다.
채점은 compare_detectors 와 같다: 60초 창 '통과 RR 평균 ÷ 정답 RR 평균' 편향, 커버리지(n ≥ 30),
그리고 봉우리 일치(맥파 전달 지연을 중앙값으로 뺀 뒤 ±24샘플).
움직임이 적은 창(이마 가속도 크기 표준편차 하위 절반)을 따로 집계해 준용의 '안정 구간'에 대응시킨다.

    .venv/Scripts/python.exe scripts/wildppg_detectors.py data/raw/wildppg/WildPPG_Part_an0.mat [--hours 2]
"""

import sys
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, sosfiltfilt, resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.peak_simple import detect, FS  # noqa: E402
from src.peak_eval import match  # noqa: E402
from scripts.compare_detectors import jy_detect, WARM_N  # noqa: E402

TARGET_PP = 238          # 준용 회로 해석의 이마 중심 동작점 [코드]
AFE_HP, AFE_LP = 0.16, 16.0
TOL = 24                 # 100 ms. PPG 봉우리는 ECG R 보다 넓고 PTT 가 흔들린다
OUT_MD = Path(__file__).resolve().parents[1] / "data" / "processed" / "stage1" / "wildppg_compare.md"


def load_participant(path):
    m = loadmat(path)
    out = {"id": str(m["id"][0])}
    for loc in ["sternum", "head"]:
        d = {}
        for name, sd in zip(m[loc][0].dtype.names, m[loc][0][0]):
            fields = sd[0][0].dtype.names
            e = {f: v[0] for f, v in zip(fields, sd[0][0])}
            if "fs" in e:
                e["fs"] = float(np.ravel(e["fs"])[0])
            d[name] = e
        out[loc] = d
    return out


def to_240(x, fs):
    sos = butter(1, AFE_HP, btype="high", fs=fs, output="sos")
    sos2 = butter(1, AFE_LP, btype="low", fs=fs, output="sos")
    y = sosfiltfilt(sos2, sosfiltfilt(sos, np.asarray(x, float)))
    from math import gcd
    g = gcd(int(fs), FS)
    return resample_poly(y, FS // g, int(fs) // g)


def to_codes_pp(y, target=TARGET_PP):
    """2초 창 p-p 중앙값이 target 코드가 되게 스케일. 준용 real_ppg 절차와 같은 발상."""
    w = 2 * FS
    n = len(y) // w
    pp = np.array([y[i * w:(i + 1) * w].max() - y[i * w:(i + 1) * w].min() for i in range(n)])
    pp = pp[np.isfinite(pp) & (pp > 0)]
    scale = target / np.median(pp)
    return np.clip(np.round(y * scale), -2047, 2047).astype(np.int64), scale


def ecg_gt(ecg, fs):
    import neurokit2 as nk
    _, info = nk.ecg_peaks(np.asarray(ecg, float), sampling_rate=int(fs))
    pk = info["ECG_R_Peaks"]
    return np.round(pk * FS / fs).astype(int)


def window_stats(rr_at, rr, okr, gt, n_samples, still_mask=None, win=60 * FS):
    gt = np.asarray(gt); gt_rr = np.diff(gt); gt_at = gt[1:]
    rows = []
    for s in range(WARM_N + 3 * 60 * FS, n_samples - win, win):
        e = s + win
        g = (gt_at >= s) & (gt_at < e)
        if g.sum() < 20:
            continue
        gm = gt_rr[g].mean()
        # 정답 자체가 흔들리는 창(ECG 아티팩트)은 뺀다: 정답 RR 변동계수 > 30%
        if gt_rr[g].std() / gm > 0.30:
            continue
        m = (rr_at >= s) & (rr_at < e) & okr
        n = int(m.sum())
        bias = 100 * (rr[m].mean() / gm - 1) if n else np.nan
        still = bool(still_mask[s // win]) if still_mask is not None and s // win < len(still_mask) else True
        rows.append((bias, n, still))
    return rows


def agg(rows, only_still=None):
    if only_still is not None:
        rows = [r for r in rows if r[2] == only_still]
    if not rows:
        return dict(n_win=0, med=np.nan, q1=np.nan, q3=np.nan, sd=np.nan, cover=np.nan, abs2=np.nan)
    b = np.array([r[0] for r in rows], float); n = np.array([r[1] for r in rows], float)
    ok = ~np.isnan(b)
    return dict(n_win=len(b), med=np.nanmedian(b), q1=np.nanpercentile(b[ok], 25) if ok.any() else np.nan,
                q3=np.nanpercentile(b[ok], 75) if ok.any() else np.nan, sd=np.nanstd(b),
                cover=100 * (n >= 30).mean(), abs2=100 * (np.abs(b[ok]) > 2.0).mean() if ok.any() else np.nan)


def peak_match(peaks, gt):
    """PTT 중앙값을 뺀 뒤 ±TOL 일치율. (놓침%, 오검출%, 지연 샘플)"""
    if len(peaks) < 10:
        return np.nan, np.nan, np.nan
    j = np.clip(np.searchsorted(gt, peaks), 1, len(gt) - 1)
    d1, d0 = peaks - gt[j], peaks - gt[j - 1]
    d = np.where(np.abs(d1) <= np.abs(d0), d1, d0)
    off = float(np.median(d[np.abs(d) <= 120]))
    hit, tp = match(peaks - int(off), gt, tol=TOL)
    return 100 * (~hit).mean(), 100 * (~tp).mean(), off


def run_one(codes, gt, still_mask, det, drop_win=None, **kw):
    if det == "ours":
        import src.peak_simple as ps
        old = ps.DROP_WIN
        if drop_win: ps.DROP_WIN = drop_win
        try:
            p, rr, ok = detect(codes)
        finally:
            ps.DROP_WIN = old
        rr_at = p[1:]
    else:
        p, rr_at, rr, ok = jy_detect(codes, **kw)
    rows = window_stats(rr_at, rr, ok, gt, len(codes), still_mask)
    miss, fp, off = peak_match(p, gt)
    return dict(rows=rows, miss=miss, fp=fp, off=off, n_peaks=len(p), rej=100 * (1 - ok.mean()) if len(ok) else np.nan)


def main(argv):
    path = argv[0]
    hours = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else None
    t0 = time.time()
    P = load_participant(path)
    head, st = P["head"], P["sternum"]
    ecg = st["ecg"]["v"]
    fs_e = st["ecg"]["fs"]
    chans = [c for c in ("ppg_g", "ppg_ir", "ppg_r") if c in head]
    if "--chan" in argv:
        chans = [argv[argv.index("--chan") + 1]]
    print(f"참가자 {P['id']}  ECG fs={fs_e}  이마 채널 {chans}  fs={head[chans[0]]['fs']}")
    if hours:
        ecg = ecg[: int(hours * 3600 * fs_e)]
    gt = ecg_gt(ecg, fs_e)
    print(f"정답 R 봉우리 {len(gt)}개, {len(ecg)/fs_e/3600:.2f} h  ({time.time()-t0:.0f}s)")

    # 움직임: 이마 가속도 크기의 60초 창 표준편차, 하위 절반 = 정지
    acc = None
    if all(k in head for k in ("acc_x", "acc_y", "acc_z")):
        ax = [head[k]["v"].astype(float) for k in ("acc_x", "acc_y", "acc_z")]
        fs_a = head["acc_x"]["fs"]
        mag = np.sqrt(ax[0] ** 2 + ax[1] ** 2 + ax[2] ** 2)
        w = int(60 * fs_a)
        nw = len(mag) // w
        sd = np.array([mag[i * w:(i + 1) * w].std() for i in range(nw)])
        still_mask = sd <= np.median(sd)
        acc = sd
    else:
        still_mask = None

    lines = [f"# 이마 PPG 검출기 비교 — WildPPG 참가자 {P['id']} ({len(ecg)/fs_e/3600:.1f} h)", "",
             f"코드 스케일: 2초 창 p-p 중앙값 = {TARGET_PP}. AFE 흉내 HP {AFE_HP} Hz / LP {AFE_LP} Hz. 정답 = 흉골 ECG neurokit. "
             f"창 편향 = 통과 RR 평균 ÷ 정답 RR 평균 − 1 (첫 3분·정답 불안정 창 제외). 봉우리 일치는 PTT 중앙값 보정 후 ±{TOL}샘플.", "",
             "| 채널 | 극성 | 검출기 | 놓침% | 오검출% | 탈락% | 창편향 중앙 | 사분위 | \\|편향\\|>2% 창 | 커버% | 정지창 편향 중앙 | 정지창 커버% | 창 수 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for ch in chans:
        raw = head[ch]["v"].astype(float)
        fs_p = head[ch]["fs"]
        if hours:
            raw = raw[: int(hours * 3600 * fs_p)]
        y = to_240(raw, fs_p)
        for pol in ((-1,) if "--neg-only" in argv else (+1, -1)):
            codes, scale = to_codes_pp(pol * y)
            for name, det, kw in [("우리", "ours", {}), ("우리 DROP_WIN=48", "ours", dict(drop_win=48)),
                                  ("준용 v13", "jy", dict(fix_prev=False, use_lpf=True)),
                                  ("준용 +prev_idx 수정", "jy", dict(fix_prev=True, use_lpf=True)),
                                  ("준용 +수정 +진폭규칙(C)", "jy", dict(fix_prev=True, use_lpf=True, amp_rule=True))]:
                r = run_one(codes, gt, still_mask, det, **kw)
                A, S = agg(r["rows"]), agg(r["rows"], only_still=True)
                lines.append(f"| {ch} | {'+' if pol > 0 else '−'} | {name} | {r['miss']:.1f} | {r['fp']:.1f} | {r['rej']:.1f} | "
                             f"{A['med']:+.2f} | {A['q1']:+.2f}~{A['q3']:+.2f} | {A['abs2']:.0f} | {A['cover']:.0f} | "
                             f"{S['med']:+.2f} | {S['cover']:.0f} | {A['n_win']} |")
                print(lines[-1], f"  ({time.time()-t0:.0f}s)", flush=True)
    out = OUT_MD.with_name(f"wildppg_compare_{P['id']}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
