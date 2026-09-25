"""판정 블록(classifier.v)의 파이썬 정수 기준 모델.

입력은 신호처리 블록이 5초마다 주는 60초 창 합 셋: n60(통과 박동 수), sum_rr60(통과 RR 합), bad60(탈락 박동 수). 출력은 (hold, drowsy).

규칙
  - 창 품질: 창이 "좋다" = n60 ≥ MIN_N60 이고 KEEP_K × bad60 ≤ n60 (살린 비율 ≥ K/(K+1), K=3 이면 75%).
    KEEP_K = 0 이면 탈락 수는 안 본다.
  - 기준선: 블록 12개(1분)마다 창 하나를 보고, 좋은 창이면 그 창 합을 기준선에 더한다. 좋은 창이 BASE_WINS(3)개
    모이면 기준선 완성. 1분 창은 서로 겹치지 않는다. 처음 3분 창이 전부 좋으면 12·24·36번째 블록의 창 합이 기준선이 된다.
  - 기준선이 완성되면 R = T_FIX × base_sum 을 한 번 계산해 둔다.
  - 매 블록: hold = 기준선 미완성 또는 창이 좋지 않음.
             drowsy = hold 아님 그리고 (sum_rr60 × base_n) << FRAC ≥ R × n60.
    이는 mean_rb = (sum_rr60/n60) / (base_sum/base_n) ≥ T 의 양변에 n60 × base_n × 2^FRAC 를 곱한 것.
  - 모든 연산은 정수. Verilog 가 이 파일과 비트 단위로 같아야 한다.

경보 간격(AlertGate, infer_top 의 심박 경보)
  - 판정은 5초마다 하지만 판정 하나가 최근 60초를 보므로, 연달아 나온 판정은 60초 중 55초가 같은 데이터다.
    그래서 졸림 판정이 나오면 경보를 바로 내고, 그 뒤 REPEAT_BLOCKS(6블록 = 30초, 창의 절반) 동안은
    졸림 판정이 나와도 경보를 내지 않는다. 판정이 중간에 끊겼다 다시 와도 마지막 경보 시각만 본다.
  - 판정(hold, drowsy) 자체는 바꾸지 않는다. 바뀌는 것은 경보 횟수뿐이다.
"""

FRAC = 10                # T 의 소수 비트 수. T = T_FIX / 2**FRAC
T_FIX = 1086             # T = 1.0605. 50명 헛경보 4회/h 이하 최소 정수 (make_infer_vectors.py --calib). 학습 검출기(peak_simple) RR 기준
WIN_BLOCKS = 12          # 60초 창 = 블록 12개. 기준선 후보 창을 1분마다 하나 본다
BASE_WINS = 3            # 기준선 = 좋은 1분 창 3개 (3분)
MIN_N60 = 30             # 창 안 유효 박동 하한 (2단계 표의 low_n 과 같음)
KEEP_K = 3               # 탈락 규칙: KEEP_K × bad60 > n60 이면 나쁜 창. 3 = 살린 비율 75%. 0 = 끔
REPEAT_BLOCKS = 6        # 심박 경보 재송신 간격 = 블록 6개(30초). 60초 창의 절반

# 비트 폭 (Verilog 와 일치)
W_N60, W_SUM60, W_BAD60 = 8, 17, 8   # 신호처리 블록 인터페이스 (o_n60, o_sum_rr60, o_bad60)
W_BASE_N, W_BASE_SUM = 10, 16   # 1분 창 셋: n ≤ 3 × 255 = 765, ΣRR ≤ 3 × (60 s × 240 + 360) = 44,280
W_TFIX = 11                     # T_FIX < 2048
W_R = W_TFIX + W_BASE_SUM       # 27
W_LHS = W_SUM60 + W_BASE_N + FRAC   # 37
W_RHS = W_R + W_N60                 # 35


def window_good(n60, bad60, keep_k=KEEP_K):
    return n60 >= MIN_N60 and (keep_k == 0 or keep_k * bad60 <= n60)


class InferRef:
    def __init__(self, t_fix=T_FIX, frac=FRAC, keep_k=KEEP_K):
        self.t_fix = t_fix
        self.frac = frac
        self.keep_k = keep_k
        self.w_lhs = W_SUM60 + W_BASE_N + frac
        self.w_rhs = t_fix.bit_length() + W_BASE_SUM + W_N60
        self.win = 0             # 1분 안에서 지나온 블록 수 (0..WIN_BLOCKS-1)
        self.good = 0            # 기준선에 넣은 좋은 창 수
        self.ready = False       # 기준선 확정됨
        self.base_n = 0
        self.base_sum = 0
        self.r = 0
        self.base_blocks = []    # 기준선에 쓴 블록 번호(분석용)
        self.blk = 0

    def push(self, n60, sum_rr60, bad60=0):
        """블록 하나(o_win_valid 펄스). (hold, drowsy) 반환. 값은 이 블록에 대한 판정."""
        assert 0 <= n60 < (1 << W_N60) and 0 <= sum_rr60 < (1 << W_SUM60) and 0 <= bad60 < (1 << W_BAD60)
        good = window_good(n60, bad60, self.keep_k)
        b = self.blk; self.blk += 1
        if not self.ready:
            if self.win == WIN_BLOCKS - 1:
                self.win = 0
                if good:
                    self.base_n += n60
                    self.base_sum += sum_rr60
                    self.base_blocks.append(b)
                    self.good += 1
                    if self.good == BASE_WINS:
                        self.ready = True
                        self.r = self.t_fix * self.base_sum
                        assert self.base_n < (1 << W_BASE_N) and self.base_sum < (1 << W_BASE_SUM)
            else:
                self.win += 1
            return 1, 0
        if not good:
            return 1, 0
        lhs = (sum_rr60 * self.base_n) << self.frac
        rhs = self.r * n60
        assert lhs < (1 << self.w_lhs) and rhs < (1 << self.w_rhs)
        return 0, int(lhs >= rhs)


class AlertGate:
    """심박 판정 → 경보. 마지막 경보로부터 REPEAT_BLOCKS 블록이 지나야 다시 낸다. 리셋 직후 첫 졸림은 바로 낸다.
    push 는 블록마다(hold 블록 포함) 한 번 부른다. since 는 infer_top 의 카운터와 같은 값이다."""

    def __init__(self, repeat=REPEAT_BLOCKS):
        self.repeat = repeat
        self.since = repeat      # 마지막 경보 뒤 지난 블록 수 (repeat 에서 포화)

    def push(self, drowsy):
        if self.since < self.repeat:
            self.since += 1
        fire = bool(drowsy) and self.since >= self.repeat
        if fire:
            self.since = 0
        return int(fire)
