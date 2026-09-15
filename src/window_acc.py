"""5초 블록 누산기와 창 합산. 하드웨어 팀이 만드는 블록의 파이썬 정답지.

규칙
  - 봉우리가 확정될 때 RR = 이번 봉우리 위치 − 직전 봉우리 위치 (샘플 수).
    확정은 봉우리보다 최대 DROP_WIN 샘플 늦다. RR은 봉우리 위치 기준이고,
    누산은 확정된 샘플이 속한 블록에 들어간다.
  - SQI를 통과한 RR만 누산한다.
  - d = RR − rr_prev. rr_prev는 직전에 누산된(SQI 통과) RR이며 블록 경계를 넘어 이어진다.
    첫 RR(rr_prev 없음)은 d 항에 넣지 않는다. 그 뒤로는 누산 RR마다 d 하나가 생기므로
    창 안의 d 개수 ≈ N. RMSSD² = Σd² / N 로 쓴다(N−1 대신. 일관된 편향이라 임계값이 흡수).
  - 1200샘플(5초)마다 누산기 한 벌을 닫아 12벌 시프트 레지스터에 넣고 0으로 초기화.
  - 창 30초 = 최근 6벌 합, 창 60초 = 최근 12벌 합. 블록을 닫을 때마다 갱신.
"""

BLOCK = 1200          # 240 SPS × 5 s
DEPTH = 12            # 60 s
W30, W60 = 6, 12

FIELDS = ("n", "sum_rr", "sum_rr2", "sum_d", "sum_d2")


class WindowAcc:
    def __init__(self):
        self.acc = dict.fromkeys(FIELDS, 0)
        self.rr_prev = None
        self.hist = []            # 최근 DEPTH벌. 끝이 최신
        self.sample = -1
        self.win30 = dict.fromkeys(FIELDS, 0)
        self.win60 = dict.fromkeys(FIELDS, 0)

    def push_sample(self):
        """샘플마다 호출. 블록 경계면 True(창 갱신됨)."""
        self.sample += 1
        if self.sample > 0 and self.sample % BLOCK == 0:
            self._close_block()
            return True
        return False

    def push_rr(self, rr, ok):
        """확정된 봉우리마다 호출. SQI 탈락이면 아무것도 안 한다."""
        if not ok:
            return
        a = self.acc
        a["n"] += 1
        a["sum_rr"] += rr
        a["sum_rr2"] += rr * rr
        if self.rr_prev is not None:
            d = rr - self.rr_prev
            a["sum_d"] += d
            a["sum_d2"] += d * d
        self.rr_prev = rr

    def _close_block(self):
        self.hist.append(dict(self.acc))
        if len(self.hist) > DEPTH:
            self.hist.pop(0)
        self.acc = dict.fromkeys(FIELDS, 0)
        self.win30 = {k: sum(b[k] for b in self.hist[-W30:]) for k in FIELDS}
        self.win60 = {k: sum(b[k] for b in self.hist[-W60:]) for k in FIELDS}
