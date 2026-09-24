"""고개 떨굼 규칙(imu_rule.v)의 파이썬 정수 기준 모델.

입력은 신호처리 블록이 100 Hz 로 주는 가속도 3축(16비트 signed, ±2 g = 16,384 LSB/g). 출력은 샘플마다 (nod, tilt).

규칙
  - 앞축 = 센서 Z 에 FWD_SIGN(-1) 을 곱한 것. 고개를 앞으로 숙이면 커진다 (센서 장착 방향에서 물리 도출).
    세로축 = 센서 Y. 세웠을 때 ±1 g. 위아래 부호는 착용에 따라 바뀌므로 절댓값을 쓴다.
  - 두 축에 1차 IIR 저역 필터 `lp += (a - lp) >>> 3` (100 Hz 에서 약 2.1 Hz. Ellcie 특허의 2 Hz 와 같다).
  - tilt = (lp_fwd >= TH_FWD) and (|lp_vert| <= TH_VERT).  TH = sin35°·LSB, cos35°·LSB.
    앞축만 보면 급제동(앞축 0.3~0.5 g)이 숙임과 같아 보인다. 숙임은 세로축을 cos θ 로 줄이고 제동은 안 줄인다.
  - cnt = tilt 가 연속된 샘플 수. cnt 가 N_HOLD(50 = 0.5 s)에 닿는 순간 펄스 1개.
    떨어진 채 있으면 cnt 가 N_HOLD+N_REPEAT(550)에 닿을 때마다 펄스를 내고 cnt 를 N_HOLD 로 되돌린다 → 5초마다 반복.
    tilt 가 풀리면 cnt = 0.
  - 모든 연산은 정수. Verilog 가 이 파일과 비트 단위로 같아야 한다. 곱셈 없음.

신호처리 블록의 imu_feature(자이로, 25° 꾸벅)와 infer_top 에서 OR 로 합쳐진다. 이 모듈은 '숙인 채 있음'(자세)만 본다.
"""
import math

LSB_PER_G = 16384            # ACCEL_CONFIG0 = 0x69 (±2 g, 100 Hz). 신호처리 블록 icm42670_reader 설정
THETA_DEG = 35               # ICM-42670-P 내장 기울기 감지 기본값과 같다
TH_FWD = int(math.sin(math.radians(THETA_DEG)) * LSB_PER_G)    # 9397  (0.5736 g)
TH_VERT = int(math.cos(math.radians(THETA_DEG)) * LSB_PER_G)   # 13420 (0.8192 g)
LPF_SH = 3                   # 100 Hz 에서 차단 약 2.1 Hz
N_HOLD = 50                  # 0.5 s
N_REPEAT = 500               # 5 s
FWD_AXIS, FWD_SIGN = 2, -1   # 센서 Z, 숙이면 음 → 뒤집어서 양
VERT_AXIS = 1                # 센서 Y
W_CNT = 10                   # N_HOLD + N_REPEAT = 550 < 1024


def s16(v):
    """16비트 signed 로 자른다(입력 확인용). 필터 출력은 수학적으로 범위 안이라 안 잘린다."""
    v = int(v) & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def neg16(v):
    """부호 반전. -32768 은 자기 자신이 되므로 32767 로 잘라 준다(Verilog 와 동일)."""
    return 32767 if v == -32768 else -v


class ImuRef:
    def __init__(self, fwd_axis=FWD_AXIS, fwd_sign=FWD_SIGN, vert_axis=VERT_AXIS,
                 th_fwd=TH_FWD, th_vert=TH_VERT, lpf_sh=LPF_SH, n_hold=N_HOLD, n_repeat=N_REPEAT):
        self.fwd_axis, self.fwd_sign, self.vert_axis = fwd_axis, fwd_sign, vert_axis
        self.th_fwd, self.th_vert, self.lpf_sh = th_fwd, th_vert, lpf_sh
        self.n_hold, self.n_repeat = n_hold, n_repeat
        self.lp_f = 0
        self.lp_v = 0
        self.cnt = 0
        self.tilt = 0

    def push(self, ax, ay, az):
        """샘플 하나(o_imu_valid). (nod, tilt) 반환. lp_f/lp_v/cnt 는 갱신 뒤 값이며 Verilog 레지스터와 같다."""
        a = (s16(ax), s16(ay), s16(az))
        a_fwd = a[self.fwd_axis]
        if self.fwd_sign < 0:
            a_fwd = neg16(a_fwd)
        a_vert = a[self.vert_axis]

        # Verilog 의 >>> 는 산술 시프트. 파이썬 int 의 >> 도 산술 시프트(바닥)다.
        self.lp_f = self.lp_f + ((a_fwd - self.lp_f) >> self.lpf_sh)
        self.lp_v = self.lp_v + ((a_vert - self.lp_v) >> self.lpf_sh)
        assert -32768 <= self.lp_f <= 32767 and -32768 <= self.lp_v <= 32767

        abs_v = neg16(self.lp_v) if self.lp_v < 0 else self.lp_v
        self.tilt = int(self.lp_f >= self.th_fwd and abs_v <= self.th_vert)

        nod = 0
        if self.tilt:
            self.cnt += 1
            if self.cnt == self.n_hold:
                nod = 1
            elif self.cnt == self.n_hold + self.n_repeat:
                nod = 1
                self.cnt = self.n_hold
        else:
            self.cnt = 0
        assert self.cnt < (1 << W_CNT)
        return nod, self.tilt


def run(acc):
    """(N,3) 정수 배열 전체. (nod, tilt, lp_f, lp_v, cnt) 열을 담은 리스트."""
    ref = ImuRef()
    out = []
    for ax, ay, az in acc:
        nod, tilt = ref.push(ax, ay, az)
        out.append((nod, tilt, ref.lp_f, ref.lp_v, ref.cnt))
    return out
