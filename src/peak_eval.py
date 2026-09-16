"""단순 봉우리 검출을 정답과 비교. 놓침·오검출·SQI 유효율.

정답은 1024 Hz 원본에서 neurokit2로 뽑아 240 Hz 인덱스로 환산한 것.
매칭 허용 오차 ±TOL 샘플.
"""

import numpy as np

TOL = 12  # 50 ms


def match(peaks, gt, tol=TOL):
    """정답마다 ±tol 안에 검출이 있으면 hit. 검출마다 ±tol 안에 정답이 있으면 tp."""
    peaks = np.asarray(peaks); gt = np.asarray(gt)
    if len(peaks) == 0:
        return np.zeros(len(gt), bool), np.zeros(0, bool)
    j = np.searchsorted(peaks, gt)
    hit = np.zeros(len(gt), bool)
    for k, g in enumerate(gt):
        for jj in (j[k] - 1, j[k]):
            if 0 <= jj < len(peaks) and abs(peaks[jj] - g) <= tol:
                hit[k] = True; break
    j2 = np.searchsorted(gt, peaks)
    tp = np.zeros(len(peaks), bool)
    for k, p in enumerate(peaks):
        for jj in (j2[k] - 1, j2[k]):
            if 0 <= jj < len(gt) and abs(gt[jj] - p) <= tol:
                tp[k] = True; break
    return hit, tp


def summarize(peaks, rr, ok, gt):
    hit, tp = match(peaks, gt)
    return dict(
        n_gt=len(gt), n_det=len(peaks),
        miss=int((~hit).sum()), miss_pct=100 * (~hit).mean() if len(gt) else 0,
        fp=int((~tp).sum()), fp_pct=100 * (~tp).mean() if len(peaks) else 0,
        n_rr=len(rr), sqi_ok_pct=100 * ok.mean() if len(ok) else 0,
    )


def fmt(s):
    return (f"정답 {s['n_gt']}  검출 {s['n_det']}  놓침 {s['miss']} ({s['miss_pct']:.2f}%)  "
            f"오검출 {s['fp']} ({s['fp_pct']:.2f}%)  SQI 유효 {s['sqi_ok_pct']:.1f}%")
