"""재료 5개 → 1차 특징 8개.

입력은 창 하나의 재료 dict {n, sum_rr, sum_rr2, sum_d, sum_d2} (단위 샘플 수).
출력도 샘플 수 단위. 회로가 같은 식을 정수로 계산하므로 여기서는
- 분산을 N으로 나눈다 (N−1 아님)
- RMSSD² = Σd²/N (d 개수가 아니라 N)
- SD2² = 2·SDNN² − RMSSD²/2. 음수면 0으로 자른다
- SD1/SD2의 분모는 SD2_FLOOR 아래로 내리지 않는다
4단계의 정수 버전은 이 함수를 기준으로 맞춘다.
"""

import math

NAMES = ("mean_nn", "sdnn", "rmssd", "sdsd", "cvnn", "cvsd", "sd2", "sd12")
SD2_FLOOR = 1.0       # 샘플. SD1/SD2 분모 하한 (4 ms)


def primary(m):
    """재료 dict → 특징 dict. n == 0 이면 전부 NaN. sd2_clipped 플래그를 같이 돌려준다."""
    n = m["n"]
    if n == 0:
        out = dict.fromkeys(NAMES, math.nan)
        out["sd2_clipped"] = False
        return out
    mean = m["sum_rr"] / n
    var = m["sum_rr2"] / n - mean * mean
    sdnn = math.sqrt(max(var, 0.0))
    msd = m["sum_d2"] / n                       # RMSSD²
    rmssd = math.sqrt(msd)
    dmean = m["sum_d"] / n
    sdsd = math.sqrt(max(msd - dmean * dmean, 0.0))
    sd2_sq = 2.0 * var - 0.5 * msd
    clipped = sd2_sq < 0
    sd2 = math.sqrt(max(sd2_sq, 0.0))
    sd1 = rmssd / math.sqrt(2.0)
    return dict(
        mean_nn=mean, sdnn=sdnn, rmssd=rmssd, sdsd=sdsd,
        cvnn=sdnn / mean, cvsd=rmssd / mean,
        sd2=sd2, sd12=sd1 / max(sd2, SD2_FLOOR),
        sd2_clipped=bool(clipped),
    )
