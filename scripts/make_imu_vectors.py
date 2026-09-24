"""6단계. 고개 떨굼 규칙(imu_ref.py / imu_rule.v)의 테스트 벡터와 정답.

    python scripts/make_imu_vectors.py            # 합성 시나리오 → sim/vectors/imu/cases.txt, 기대 펄스 수 확인
    python scripts/make_imu_vectors.py --dalia    # + PPG-DaLiA 가슴 가속도 15명(이마 대용)에 규칙을 돌려 오발 횟수 표,
                                                  #   S1 전체를 data/processed/stage6/imu_dalia_S1.txt 로 (git 제외, tb +vec= 용)

합성 시나리오는 100 Hz, ±2 g(16,384 LSB/g) 정수. 좌표는 센서 장착 기준: Y = 이마-턱(세우면 +1 g), Z = 앞(숙이면 −sinθ·g),
X = 귀-귀. 급제동은 차가 뒤로 잡아당기므로 +Z(앞)에 −a 가 실린다(숙임과 같은 부호). 정답은 라벨이 아니라 파이썬 정수 규칙이다.
"""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import imu_ref as R  # noqa: E402

OUT_VEC = ROOT / "sim" / "vectors" / "imu"
OUT_DAT = ROOT / "data" / "processed" / "stage6"
FS = 100
G = R.LSB_PER_G
rng = np.random.default_rng(6)


def q(v):
    return np.clip(np.round(v), -32768, 32767).astype(np.int64)


def make(theta_deg, brake_g=0.0, vib_g=0.0, noise_g=0.003, lateral_g=None, y_sign=+1):
    """theta_deg: 샘플별 앞으로 숙인 각(배열). brake_g: 앞축에 실리는 제동 가속(배열 또는 상수). 반환 (N,3) 정수."""
    th = np.radians(np.asarray(theta_deg, dtype=float))
    n = len(th)
    t = np.arange(n) / FS
    brake = np.broadcast_to(np.asarray(brake_g, dtype=float), (n,))
    ax = np.zeros(n)
    ay = y_sign * np.cos(th) * G
    az = -np.sin(th) * G - brake * G
    if lateral_g is not None:
        ax = ax + lateral_g * G
    if vib_g:
        v = vib_g * G * np.sin(2 * np.pi * 12 * t)
        ax, ay, az = ax + v, ay + 0.6 * v, az + 0.8 * v
    noise = rng.normal(0, noise_g * G, (n, 3))
    return q(np.stack([ax, ay, az], axis=1) + noise)


def ramp_hold(peak_deg, ramp_s, hold_s, pre_s=1.0, post_s=1.0):
    """0 → peak(ramp) → 유지(hold) → 0(ramp). 앞뒤 정지 구간 포함."""
    pre, r, h, post = int(pre_s * FS), int(ramp_s * FS), int(hold_s * FS), int(post_s * FS)
    up = np.linspace(0, peak_deg, r, endpoint=False)
    dn = np.linspace(peak_deg, 0, r, endpoint=False)
    return np.concatenate([np.zeros(pre), up, np.full(h, peak_deg), dn, np.zeros(post)])


def scenarios():
    """(이름, (N,3) 배열, 기대 펄스 수 또는 None, 설명)."""
    S = []
    z = lambda s: np.zeros(int(s * FS))
    S.append(("still", make(z(10)), 0, "정지 10 s"))
    S.append(("vibration", make(z(10), vib_g=0.1, noise_g=0.03), 0, "도로 진동 12 Hz 0.1 g + 잡음 0.03 g"))
    S.append(("brake_0p5g", make(z(5), brake_g=np.r_[np.zeros(100), np.full(300, 0.5), np.zeros(100)]), 0,
              "급제동 0.5 g 3 s. 앞축은 숙임 30° 와 같지만 세로축 1 g 그대로"))
    S.append(("brake_0p7g", make(z(4), brake_g=np.r_[np.zeros(100), np.full(200, 0.7), np.zeros(100)]), 0,
              "급제동 0.7 g 2 s. 앞축이 문턱을 넘어도 세로축이 막는다"))
    S.append(("dashboard_20deg", make(ramp_hold(20, 0.2, 2.0)), 0, "계기판 보기 20° 2 s"))
    S.append(("glance_40deg_0p3s", make(ramp_hold(40, 0.1, 0.3)), 0, "꾸벅 40° 0.3 s. 지속 부족"))
    S.append(("nod_40deg_1s", make(ramp_hold(40, 0.15, 1.0)), 1, "떨굼 40° 1 s"))
    S.append(("sleep_50deg_20s", make(ramp_hold(50, 0.3, 20.0)), 4, "잠듦 50° 20 s. 0.5 s + 5 s 마다"))
    S.append(("sleep_45deg_vib", make(ramp_hold(45, 0.3, 3.0), vib_g=0.1, noise_g=0.03), 1, "요철 위에서 45° 3 s"))
    S.append(("shake_lateral", make(z(6), lateral_g=0.5 * np.sin(2 * np.pi * 1.0 * np.arange(600) / FS)), 0,
              "고개 좌우 흔들기 ±0.5 g 1 Hz"))
    S.append(("tilt_back_30deg", make(ramp_hold(-30, 0.2, 3.0)), 0, "뒤로 젖힘 30° 3 s"))
    S.append(("dash_plus_brake", make(ramp_hold(20, 0.2, 2.0), brake_g=np.r_[np.zeros(120), np.full(200, 0.5), np.zeros(int(4.4 * FS) - 320)]),
              0, "계기판 20° 보면서 급제동 0.5 g. 앞축 합은 문턱 넘지만 세로축 cos20° 가 막는다"))
    th = np.concatenate([np.zeros(100), np.linspace(0, 45, 600), np.full(1000, 45), np.linspace(45, 0, 100), np.zeros(100)])
    S.append(("slow_slump", make(th), None, "6 s 에 걸쳐 45° 까지 천천히 처져 10 s 유지. 신호처리 블록 자이로 규칙은 못 잡는 경우"))
    S.append(("exact_35deg", make(ramp_hold(35, 0.2, 5.0)), None, "정확히 35° 5 s. 잡음·반올림에 따라 경계"))
    S.append(("nod_y_negative", make(ramp_hold(40, 0.15, 1.0), y_sign=-1), 1, "세로축 부호가 반대(밴드 뒤집어 씀)여도 같아야 함"))
    S.append(("clip_extreme", q(np.tile([[32767, -32768, -32768]], (300, 1))), None, "포화값. 오버플로 없음만 확인"))
    return S


def write_cases(S):
    OUT_VEC.mkdir(parents=True, exist_ok=True)
    rows = []
    summary = []
    for name, acc, expect, desc in S:
        out = R.run(acc)
        n_nod = sum(o[0] for o in out)
        first = next((k for k, o in enumerate(out) if o[0]), None)
        ok = "-" if expect is None else ("OK" if n_nod == expect else "!!")
        summary.append((name, len(acc) / FS, n_nod, expect, first, ok, desc))
        for k, (a, o) in enumerate(zip(acc, out)):
            rows.append(f"{name} {k} {a[0]} {a[1]} {a[2]} {o[0]} {o[2]} {o[3]} {o[4]}")
    with open(OUT_VEC / "cases.txt", "w", newline="\n") as f:
        f.write("case k ax ay az nod lp_f lp_v cnt\n")
        f.write("\n".join(rows) + "\n")
    print(f"{'시나리오':22s} {'길이':>6s} {'펄스':>4s} {'기대':>4s} {'첫 펄스(s)':>10s}  설명")
    bad = 0
    for name, dur, n_nod, expect, first, ok, desc in summary:
        fs = "-" if first is None else f"{first / FS:.2f}"
        print(f"{name:22s} {dur:6.1f} {n_nod:4d} {str(expect) if expect is not None else '-':>4s} {fs:>10s}  {ok:2s} {desc}")
        bad += ok == "!!"
    print(f"sim/vectors/imu/cases.txt: {len(rows)} 샘플, 시나리오 {len(S)}개, 기대 불일치 {bad}")
    return bad


def dalia(write_s1=True):
    """가슴 가속도(이마 대용)에 규칙을 돌린다. 가슴 센서는 X = 세로(앉기 0.9 g), Z = 앞뒤(운전 자세 −0.5 g = 뒤로 젖힘)."""
    import pandas as pd
    names = {0: "이동", 1: "앉기", 2: "계단", 3: "축구", 4: "자전거", 5: "운전", 6: "점심", 7: "걷기", 8: "업무"}
    rows = []
    for s in range(1, 16):
        d = np.load(ROOT / f"data/interim/dalia/S{s}.npz")
        a = d["chest_acc"]; act = np.repeat(d["activity"], 25)
        m = min(len(a), len(act)); a, act = a[:m], act[:m]
        one = np.median(np.linalg.norm(a[act == 1], axis=1)) if (act == 1).any() else np.median(np.linalg.norm(a, axis=1))
        acc = q(a / one * G)
        # 가슴 축 → 규칙 축: 앞 = +Z(숙이면 커짐), 세로 = X
        ref = R.ImuRef(fwd_axis=2, fwd_sign=+1, vert_axis=0)
        out = np.array([ref.push(*r)[0] for r in acc])
        for k in names:
            sel = act == k
            if sel.sum():
                rows.append((s, k, sel.sum() / FS / 3600, out[sel].sum()))
        if s == 1 and write_s1:
            OUT_DAT.mkdir(parents=True, exist_ok=True)
            ref = R.ImuRef(fwd_axis=2, fwd_sign=+1, vert_axis=0)
            with open(OUT_DAT / "imu_dalia_S1.txt", "w", newline="\n") as f:
                f.write("case k ax ay az nod lp_f lp_v cnt\n")
                for k, r in enumerate(acc):
                    nod, _ = ref.push(*r)
                    f.write(f"S1 {k} {r[0]} {r[1]} {r[2]} {nod} {ref.lp_f} {ref.lp_v} {ref.cnt}\n")
            print(f"data/processed/stage6/imu_dalia_S1.txt: {len(acc)} 샘플 (tb +vec= 용)")
    t = pd.DataFrame(rows, columns=["subject", "act", "hours", "pulses"])
    g = t.groupby("act")
    print("\nPPG-DaLiA 가슴 가속도(이마 대용, 앞=+Z 세로=X)에 규칙 적용 — 활동별 펄스/시간 (참고)")
    print(f"{'활동':6s} {'시간(h)':>8s} {'펄스':>6s} {'펄스/h':>8s}")
    for k, gg in g:
        h, p = gg.hours.sum(), gg.pulses.sum()
        print(f"{names[k]:6s} {h:8.2f} {int(p):6d} {p / h:8.1f}")
    print("운전 사람별 펄스:", {int(r.subject): int(r.pulses) for r in t[t.act == 5].itertuples()})


def main(argv):
    bad = write_cases(scenarios())
    if "--dalia" in argv:
        dalia()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
