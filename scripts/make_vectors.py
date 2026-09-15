"""하드웨어 팀 채점 파일. 파형 → 봉우리 → RR → 5초 블록 → 창 합산.

    python scripts/make_vectors.py            # 02번 60~180초
    python scripts/make_vectors.py 05 300 120 # 05번 300초부터 120초

sim/vectors/ 에 텍스트로 떨군다. 전부 10진수, 한 줄에 레코드 하나, 첫 줄은 열 이름.
  in.txt       샘플 코드 (16비트 부호 있는 정수, 0 중심). 한 줄에 하나
  peaks.txt    peak_i confirm_i          봉우리 위치, 확정 샘플
  rr.txt       confirm_i rr ok           확정마다 RR과 SQI
  blocks.txt   block_end n sum_rr sum_rr2 sum_d sum_d2       5초마다 그 블록 누산값
  windows.txt  block_end n30 sum_rr30 ... n60 sum_rr60 ...   5초마다 30초·60초 창 합
in.hex는 같은 입력을 16비트 2의 보수 hex로 ($readmemh용).
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mpd_io import load_ecg_as_ppg_chain  # noqa: E402
from src.peak_simple import PeakDetector, SQI, to_codes, FS, DROP_WIN  # noqa: E402
from src.window_acc import WindowAcc, FIELDS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "sim" / "vectors"


def main(argv):
    sid = argv[0] if argv else "02"
    t0 = int(argv[1]) if len(argv) > 1 else 60
    dur = int(argv[2]) if len(argv) > 2 else 120
    x = load_ecg_as_ppg_chain(sid, FS)[t0 * FS:(t0 + dur) * FS]   # AFE 대역 흉내
    codes = to_codes(x)
    assert codes.min() >= -32768 and codes.max() <= 32767

    det, sqi, acc = PeakDetector(), SQI(), WindowAcc()
    peaks, rrs, blocks, windows = [], [], [], []
    for i, v in enumerate(codes):
        p = det.push(int(v))
        if p is not None:
            peaks.append((p, i))
            rr, ok = sqi.push(p)
            if rr is not None:
                rrs.append((i, rr, int(ok)))
                acc.push_rr(rr, ok)
        if acc.push_sample():
            blocks.append((i, *[acc.hist[-1][k] for k in FIELDS]))
            windows.append((i, *[acc.win30[k] for k in FIELDS], *[acc.win60[k] for k in FIELDS]))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "in.txt").write_text("\n".join(str(int(v)) for v in codes) + "\n")
    (OUT / "in.hex").write_text("\n".join(f"{int(v) & 0xFFFF:04x}" for v in codes) + "\n")
    (OUT / "peaks.txt").write_text("peak_i confirm_i\n" + "\n".join(f"{p} {c}" for p, c in peaks) + "\n")
    (OUT / "rr.txt").write_text("confirm_i rr ok\n" + "\n".join(f"{c} {r} {o}" for c, r, o in rrs) + "\n")
    (OUT / "blocks.txt").write_text("block_end " + " ".join(FIELDS) + "\n"
                                    + "\n".join(" ".join(map(str, b)) for b in blocks) + "\n")
    hdr = "block_end " + " ".join(f"{k}30" for k in FIELDS) + " " + " ".join(f"{k}60" for k in FIELDS)
    (OUT / "windows.txt").write_text(hdr + "\n" + "\n".join(" ".join(map(str, w)) for w in windows) + "\n")
    (OUT / "README.md").write_text(f"""# 채점 파일

출처: MPD-DF {sid}번 ECG, {t0}초부터 {dur}초. 아날로그 프론트엔드 대역(0.16~16 Hz, 1차 RC 두 개) 흉내 → 1024 Hz → 240 Hz → mV × 400 → 정수 코드.
실제 칩에서는 ADC 출력(FPGA 노치 필터 뒤)이 `in`에 해당한다. AC 결합 덕에 0 중심이다.

| 파일 | 내용 |
|---|---|
| `in.txt` / `in.hex` | 입력 {len(codes)}샘플. 16비트 부호 있는 정수. hex는 2의 보수, `$readmemh`용 |
| `peaks.txt` | 확정된 봉우리 {len(peaks)}개. `peak_i`는 봉우리 위치, `confirm_i`는 급하강 확인이 끝나 확정된 샘플(최대 {DROP_WIN} 늦음) |
| `rr.txt` | 확정마다 RR(샘플 수)과 SQI 통과 여부. 첫 봉우리는 RR 없음 |
| `blocks.txt` | 5초 블록마다 그 블록의 누산값 5개. SQI 통과 RR만 |
| `windows.txt` | 5초 블록마다 최근 6벌 합(30초)과 12벌 합(60초) |

규칙과 상수는 `src/peak_simple.py`, `src/window_acc.py`. 회로가 이 파일들과 같은 값을 내면 통과.

검증 순서: `peaks.txt`의 `peak_i`가 맞는지 → `rr.txt` → `blocks.txt` → `windows.txt`. 앞에서 틀리면 뒤는 볼 필요 없다.
""", encoding="utf-8")
    ok_pct = 100 * sum(o for _, _, o in rrs) / max(len(rrs), 1)
    print(f"{sid}번 {t0}~{t0+dur}s: 샘플 {len(codes)}, 봉우리 {len(peaks)}, RR {len(rrs)} (SQI 통과 {ok_pct:.1f}%), 블록 {len(blocks)}")
    print(f"마지막 창: 30초 N={windows[-1][1]} ΣRR={windows[-1][2]}  60초 N={windows[-1][6]} ΣRR={windows[-1][7]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
