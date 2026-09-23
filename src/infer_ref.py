"""판정 블록(rtl/classifier.v)의 파이썬 정수 기준 모델. 설계는 docs/integer-inference-design.md.

입력은 준용 블록이 5초마다 주는 60초 창 합 (n60, sum_rr60) 둘. 출력은 (hold, drowsy).

규칙
  - 워밍업 = 블록 36개(3분). 기준선 재료는 새 신호 없이 60초 창 합을 세 번(12·24·36번째 블록) 더해서 만든다.
    창 셋이 겹치지 않으니 블록 0~35의 합과 같다.
  - 워밍업 끝에 base_n < MIN_BASE_N 이면 기준선을 버리고 워밍업을 다시 시작한다(3분 더).
  - 워밍업이 끝나면 R = T_FIX × base_sum 을 한 번 계산해 둔다.
  - 매 블록: hold = 워밍업 중 또는 n60 < MIN_N60.
             drowsy = hold 아님 그리고 (sum_rr60 × base_n) << FRAC ≥ R × n60.
    이는 mean_rb = (sum_rr60/n60) / (base_sum/base_n) ≥ T 의 양변에 n60 × base_n × 2^FRAC 를 곱한 것.
    나눗셈이 없고, 근사는 T 를 T_FIX / 2^FRAC 로 둔 것 하나뿐이다.
  - 모든 연산은 정수. Verilog 가 이 파일과 비트 단위로 같아야 한다.
"""

FRAC = 10                # T 의 소수 비트 수. T = T_FIX / 2**FRAC
T_FIX = 1086             # T = 1.0605. 50명 헛경보 4회/h 이하 최소 정수 (scripts/make_infer_vectors.py --calib). 학습 검출기(peak_simple) RR 기준
WARM_BLOCKS = 36         # 3분
WIN_BLOCKS = 12          # 60초 창 = 블록 12개
MIN_N60 = 30             # 창 안 유효 박동 하한. 미만이면 hold (2단계 표의 low_n 과 같음)
MIN_BASE_N = 45          # 기준선 박동 하한. 미만이면 워밍업 재시작 (표의 base_ok_chip 과 같음)

# 비트 폭 (Verilog 와 일치)
W_N60, W_SUM60 = 8, 17          # 준용 인터페이스
W_BASE_N, W_BASE_SUM = 10, 16   # 3분 × 3.3 bps = 594, 3분 × 240 SPS = 43,200 + 360
W_TFIX = 11                     # T_FIX < 2048
W_R = W_TFIX + W_BASE_SUM       # 27
W_LHS = W_SUM60 + W_BASE_N + FRAC   # 37
W_RHS = W_R + W_N60                 # 35


class InferRef:
    def __init__(self, t_fix=T_FIX, frac=FRAC):
        self.t_fix = t_fix
        self.frac = frac
        self.w_lhs = W_SUM60 + W_BASE_N + frac
        self.w_rhs = t_fix.bit_length() + W_BASE_SUM + W_N60
        self.warm = 0            # 워밍업 안에서 지나온 블록 수 (0..WARM_BLOCKS-1)
        self.ready = False       # 기준선 확정됨
        self.base_n = 0
        self.base_sum = 0
        self.r = 0

    def push(self, n60, sum_rr60):
        """블록 하나(o_win_valid 펄스). (hold, drowsy) 반환. 값은 이 블록에 대한 판정."""
        assert 0 <= n60 < (1 << W_N60) and 0 <= sum_rr60 < (1 << W_SUM60)
        if not self.ready:
            if (self.warm + 1) % WIN_BLOCKS == 0:
                self.base_n += n60
                self.base_sum += sum_rr60
            if self.warm == WARM_BLOCKS - 1:
                if self.base_n >= MIN_BASE_N:
                    self.ready = True
                    self.r = self.t_fix * self.base_sum
                    assert self.base_n < (1 << W_BASE_N) and self.base_sum < (1 << W_BASE_SUM)
                else:
                    self.base_n = 0
                    self.base_sum = 0
                self.warm = 0
            else:
                self.warm += 1
            return 1, 0
        if n60 < MIN_N60:
            return 1, 0
        lhs = (sum_rr60 * self.base_n) << self.frac
        rhs = self.r * n60
        assert lhs < (1 << self.w_lhs) and rhs < (1 << self.w_rhs)
        return 0, int(lhs >= rhs)
