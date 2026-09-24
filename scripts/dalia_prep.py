"""PPG-DaLiA 전처리. zip 을 풀지 않고 S1..S15 pkl 을 하나씩 스트리밍으로 읽어
(1) 가벼운 npz 로 저장하고 (2) 5초 블록별 가속도 요약표를 만든다.

  npz  : S{n}.npz
         wrist_acc (int16, 32 Hz, 1/64 g), bvp (float32, 64 Hz), ecg (float32, 700 Hz),
         chest_acc (float32, 100 Hz 로 다운샘플, g 단위), rpeaks (int64, 700 Hz 인덱스),
         activity (int8, 4 Hz), label_hr (float32, 8초 창 2초 이동), fs_* 스칼라
  블록표: acc_blocks.csv  (5초 블록 하나가 한 줄)
         subject, activity(블록 내 최빈 ID), t0, 손목·가슴 각각
           mag_dev_max/p95/mean : | ‖a‖ − 1 g | (정지 기울기와 무관한 동적 크기), g 단위
           jerk_mean            : 연속 샘플 차의 L2 크기 평균, g/sample
         pkl 의 두 가속도는 모두 g 단위. 가슴은 크기 중앙값이 0.94 라 앉기(ID 1) 구간 ‖a‖ 중앙값을 1 g 로 다시 맞춤(c_one_g).

용도: 6단계 "움직임 과다" 보류 기준의 참고(활동별 분포), 5단계 ECG↔PPG RR 비교 입력.
손목·가슴 센서라 이마와 같지 않다. 활동 ID: 0 이동 1 앉기 2 계단 3 축구 4 자전거 5 운전 6 점심 7 걷기 8 업무.
"""
import argparse
import csv
import pickle
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data/raw/ppg_dalia/ppg+dalia.zip"
OUT = ROOT / "data/interim/dalia"
FS = dict(wrist_acc=32, bvp=64, ecg=700, chest=700, chest_out=100, activity=4)
BLOCK_S = 5


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def open_inner():
    outer = zipfile.ZipFile(ZIP)
    return zipfile.ZipFile(outer.open("data.zip"))


def load_subject(inner, n):
    name = f"PPG_FieldStudy/S{n}/S{n}.pkl"
    with inner.open(name) as f:
        return pickle.load(f, encoding="latin1")


def downsample_mean(x, factor):
    m = (len(x) // factor) * factor
    return x[:m].reshape(-1, factor, x.shape[1]).mean(axis=1)


def block_stats(acc_g, fs, activity, one_g=1.0):
    """acc_g: (N,3) g 단위. 5초 블록별 요약. activity 는 4 Hz 정수열."""
    n_blk = len(acc_g) // (fs * BLOCK_S)
    mag = np.linalg.norm(acc_g, axis=1)
    dev = np.abs(mag - one_g)
    jerk = np.linalg.norm(np.diff(acc_g, axis=0, prepend=acc_g[:1]), axis=1)
    rows = []
    for b in range(n_blk):
        s, e = b * fs * BLOCK_S, (b + 1) * fs * BLOCK_S
        a_s, a_e = b * FS["activity"] * BLOCK_S, (b + 1) * FS["activity"] * BLOCK_S
        act = activity[a_s:a_e]
        act_id = int(np.bincount(act.astype(np.int64)).argmax()) if len(act) else -1
        d = dev[s:e]
        rows.append((act_id, b * BLOCK_S, d.max(), np.percentile(d, 95), d.mean(), jerk[s:e].mean()))
    return rows


def process(n, inner, writer):
    t0 = time.time()
    d = load_subject(inner, n)
    sig = d["signal"]
    w_g = np.asarray(sig["wrist"]["ACC"], dtype=np.float32)               # pkl 은 이미 g 단위(1/64 배수)
    wrist_acc = np.round(w_g * 64).astype(np.int16)                       # 1/64 g 정수로 저장
    bvp = np.asarray(sig["wrist"]["BVP"], dtype=np.float32).reshape(-1)
    ecg = np.asarray(sig["chest"]["ECG"], dtype=np.float32).reshape(-1)
    chest_acc = np.asarray(sig["chest"]["ACC"], dtype=np.float32)          # g 단위이나 크기 중앙값 0.94 로 약간 어긋남
    activity = np.asarray(d["activity"], dtype=np.int8).reshape(-1)
    label = np.asarray(d["label"], dtype=np.float32).reshape(-1)
    rpeaks = np.asarray(d["rpeaks"], dtype=np.int64).reshape(-1)
    del d, sig

    chest_ds = downsample_mean(chest_acc, FS["chest"] // FS["chest_out"]).astype(np.float32)
    del chest_acc

    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / f"S{n}.npz",
        wrist_acc=wrist_acc, bvp=bvp, ecg=ecg, chest_acc=chest_ds, rpeaks=rpeaks,
        activity=activity, label_hr=label,
        fs_wrist_acc=FS["wrist_acc"], fs_bvp=FS["bvp"], fs_ecg=FS["ecg"],
        fs_chest_acc=FS["chest_out"], fs_activity=FS["activity"],
        wrist_acc_unit="1/64 g", chest_acc_unit="g (nominal), see acc_blocks.csv c_one_g",
    )

    w_rows = block_stats(w_g, FS["wrist_acc"], activity)
    # 가슴: 앉기 구간 크기 중앙값을 1 g 로 다시 맞춤
    act_100 = np.repeat(activity, FS["chest_out"] // FS["activity"])
    m = min(len(act_100), len(chest_ds))
    sit = np.linalg.norm(chest_ds[:m][act_100[:m] == 1], axis=1)
    one_g = float(np.median(sit)) if len(sit) else float(np.median(np.linalg.norm(chest_ds, axis=1)))
    c_rows = block_stats(chest_ds / one_g, FS["chest_out"], activity)

    for (act, t, wmax, wp95, wmean, wj), (_, _, cmax, cp95, cmean, cj) in zip(w_rows, c_rows):
        writer.writerow([n, act, t,
                         f"{wmax:.4f}", f"{wp95:.4f}", f"{wmean:.4f}", f"{wj:.5f}",
                         f"{cmax:.4f}", f"{cp95:.4f}", f"{cmean:.4f}", f"{cj:.5f}", f"{one_g:.1f}"])
    log(f"S{n}: {len(w_rows)} blocks, {len(ecg)/FS['ecg']/60:.1f} min, "
        f"chest one_g={one_g:.1f}, {time.time()-t0:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", type=int, nargs="*", default=list(range(1, 16)))
    ap.add_argument("--csv", default=str(OUT / "acc_blocks.csv"))
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.csv)
    new = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["subject", "activity", "t0_s",
                        "w_dev_max", "w_dev_p95", "w_dev_mean", "w_jerk_mean",
                        "c_dev_max", "c_dev_p95", "c_dev_mean", "c_jerk_mean", "c_one_g"])
        inner = open_inner()
        for n in args.subjects:
            try:
                process(n, inner, w)
                f.flush()
            except Exception as e:  # 한 명 실패해도 다음으로
                log(f"S{n}: FAILED {type(e).__name__}: {e}")
    log("ALL DONE")


if __name__ == "__main__":
    sys.exit(main())
