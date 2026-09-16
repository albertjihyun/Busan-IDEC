"""회로로 옮길 수 있는 단순 봉우리 검출과 SQI.

한 샘플씩 들어와서 상태 몇 개만 갱신한다. 배열 전체를 보는 연산이 없다.
전부 정수 연산이다. 곱셈은 상수 곱 세 번(문턱·급하강 비교·급변 비교)이고 나머지는 덧셈·비교·시프트다.
이 파일이 하드웨어 팀이 Verilog로 옮기는 설계도다. 상수는 전부 위에 모아 둔다.

입력 조건: FIR 대역통과를 거친 **0 중심** 부호 있는 정수(12~16비트). DC가 남아 있으면 상대 문턱이 깨진다.

규칙
  1. 올라가다 꺾이는 샘플이 봉우리 후보 (x[i-1] > x[i] 이고 직전에 상승 중이었음)
  2. 후보 높이가 적응 문턱 이상이어야 한다. 문턱 = 최근 봉우리 높이의 THR_NUM/THR_DEN
  3. 직전 봉우리로부터 REFRACT 샘플 안이면 무시 (불응기)
  4. 후보 뒤 DROP_WIN 샘플 안에 봉우리 높이의 DROP_NUM/DROP_DEN 이상 떨어져야 확정 (급하강 확인)
  5. 확정된 봉우리 높이로 문턱 기준을 갱신 (level += (peak - level) >> LEVEL_SHIFT)
SQI
  6. RR이 RR_MIN~RR_MAX 밖이면 탈락
  7. 직전 유효 RR 대비 JUMP_NUM/JUMP_DEN 넘게 달라지면 탈락. 첫 RR은 기준이 없어 탈락
"""

FS = 240

# 봉우리 검출
REFRACT = 96          # 0.4 s. 분당 150회 상한. T파·dicrotic notch가 봉우리 뒤 0.3~0.4 s에 오므로 72로는 부족(26번에서 확인)
THR_NUM, THR_DEN = 3, 5     # 문턱 = 최근 봉우리 높이의 3/5
DROP_WIN = 24         # 0.1 s 안에
DROP_NUM, DROP_DEN = 1, 2   # 봉우리 높이의 1/2 이상 떨어져야
LEVEL_SHIFT = 3       # level 갱신 1/8

# SQI
RR_MIN, RR_MAX = 72, 360    # 0.3~1.5 s
JUMP_NUM, JUMP_DEN = 1, 4   # 직전 RR 대비 25% 초과 변화면 탈락

# 초기 문턱. 0이면 첫 봉우리부터 적응하므로 신호 단위·이득에 무관
LEVEL_INIT = 0


class PeakDetector:
    """샘플 하나 넣으면 (봉우리 확정 여부, 봉우리 위치) 반환.

    급하강 확인 때문에 확정은 후보보다 최대 DROP_WIN 샘플 늦게 난다.
    회로에서는 위치 대신 '후보로부터 지연된 샘플 수'를 쓰면 된다.
    """

    def __init__(self, level_init=LEVEL_INIT):
        self.i = -1
        self.prev = None
        self.rising = False
        self.level = level_init
        self.last_peak = -10**9
        # 급하강 확인 대기 중인 후보
        self.cand_i = None
        self.cand_v = None
        self.cand_min = None

    def push(self, x):
        self.i += 1
        out = None

        # 4. 대기 중 후보의 급하강 확인
        if self.cand_i is not None:
            if x < self.cand_min:
                self.cand_min = x
            elapsed = self.i - self.cand_i
            dropped = (self.cand_v - self.cand_min) * DROP_DEN >= self.cand_v * DROP_NUM
            if dropped:
                out = self.cand_i
                self.last_peak = self.cand_i
                # 산술 시프트. Verilog에서는 signed >>> LEVEL_SHIFT
                self.level += (self.cand_v - self.level) >> LEVEL_SHIFT
                self.cand_i = None
            elif elapsed >= DROP_WIN:
                self.cand_i = None       # 급하강 없음. 버림
            elif x > self.cand_v:
                self.cand_i = None       # 더 높은 값이 옴. 이 후보는 버리고 아래에서 다시 판단

        # 1~3. 꺾이는 지점
        if self.prev is not None:
            if x > self.prev:
                self.rising = True
            elif x < self.prev and self.rising:
                self.rising = False
                cand_i, cand_v = self.i - 1, self.prev
                if (cand_v * THR_DEN >= self.level * THR_NUM
                        and cand_i - self.last_peak >= REFRACT
                        and self.cand_i is None):
                    self.cand_i, self.cand_v, self.cand_min = cand_i, cand_v, x
        self.prev = x
        return out


class SQI:
    """봉우리 위치를 넣으면 (RR, 유효 여부) 반환. 첫 봉우리는 RR 없음."""

    def __init__(self):
        self.last = None
        self.last_rr = None

    def push(self, peak_i):
        if self.last is None:
            self.last = peak_i
            return None, False
        rr = peak_i - self.last
        self.last = peak_i
        in_range = RR_MIN <= rr <= RR_MAX
        # 첫 RR은 비교 기준이 없으므로 탈락. 시동 직후 잡음 봉우리가 누산에 들어가는 것을 막는다
        ok = in_range and self.last_rr is not None
        if ok:
            diff = abs(rr - self.last_rr)
            ok = diff * JUMP_DEN <= self.last_rr * JUMP_NUM
        # 기준값은 급변 판정과 무관하게 '범위 안인 마지막 RR'로 전진시킨다.
        # 급변 탈락한 RR을 기준에서 빼면 오검출 하나가 그 뒤 정상 RR 전부를 탈락시키는 연쇄가 생긴다.
        if in_range:
            self.last_rr = rr
        return rr, ok


def to_codes(x, scale=400):
    """mV float → 0 중심 정수 코드. 테스트·시뮬레이션용. 실제 칩은 FIR 출력이 이 자리에 온다."""
    import numpy as np
    return np.round(np.asarray(x, dtype=float) * scale).astype(np.int64)


def detect(x, level_init=LEVEL_INIT):
    """배열 전체를 한 번에. float가 오면 정수 코드로 바꾼다. 반환 (봉우리 인덱스, RR, 유효 마스크)."""
    import numpy as np
    x = np.asarray(x)
    if not np.issubdtype(x.dtype, np.integer):
        x = to_codes(x)
    det, sqi = PeakDetector(level_init), SQI()
    peaks, rrs, oks = [], [], []
    for v in x:
        p = det.push(int(v))
        if p is not None:
            peaks.append(p)
            rr, ok = sqi.push(p)
            if rr is not None:
                rrs.append(rr); oks.append(ok)
    return np.array(peaks), np.array(rrs), np.array(oks, dtype=bool)
