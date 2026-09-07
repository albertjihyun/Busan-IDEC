"""공개 데이터셋 내려받기.

사용법:
    python scripts/download_data.py            # 기본 세트 (advitam-exp4, ppg-dalia)
    python scripts/download_data.py --list     # 받을 수 있는 항목 보기
    python scripts/download_data.py advitam-meta

중단되면 같은 명령을 다시 실행한다. 이어받기(Range) 지원.
"""

import argparse
import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

ZENODO = "https://zenodo.org/api/records/7319612/files/{}/content"

DATASETS = {
    # AdVitam: 실험 4(수면부족 63명)가 주 학습 대상. 전체 6개 실험은 13.9GB라 받지 않는다.
    "advitam-meta": [
        (ZENODO.format("README.md"), "advitam/README.md"),
        (ZENODO.format("physiological_indicators.xlsx"), "advitam/physiological_indicators.xlsx"),
    ],
    "advitam-exp4": [(ZENODO.format("Exp4.zip"), "advitam/Exp4.zip")],  # 약 3.97GB
    "advitam-exp1": [(ZENODO.format("Exp1.zip"), "advitam/Exp1.zip")],  # 약 1.57GB
    "ppg-dalia": [
        ("https://archive.ics.uci.edu/static/public/495/ppg+dalia.zip", "ppg_dalia/ppg+dalia.zip")
    ],
}

DEFAULT = ["advitam-meta", "advitam-exp4", "ppg-dalia"]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    done = part.stat().st_size if part.exists() else 0

    # Zenodo는 "Mozilla/5.0"처럼 짧은 UA를 403으로 막는다.
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    if done:
        req.add_header("Range", f"bytes={done}-")

    with urllib.request.urlopen(req, timeout=120) as resp:
        if done and resp.status != 206:  # 서버가 이어받기를 거부하면 처음부터
            done = 0
        total = int(resp.headers.get("Content-Length", 0)) + done
        mode = "ab" if done else "wb"
        with open(part, mode) as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = 100 * done / total
                    print(f"\r  {dest.name}  {done/1e6:8.1f} / {total/1e6:.1f} MB  ({pct:5.1f}%)",
                          end="", flush=True)
    print()
    part.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", default=[], help=f"기본값: {' '.join(DEFAULT)}")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for name, files in DATASETS.items():
            print(f"{name:<14} {', '.join(d for _, d in files)}")
        return 0

    for name in args.names or DEFAULT:
        if name not in DATASETS:
            print(f"알 수 없는 항목: {name}", file=sys.stderr)
            return 1
        for url, rel in DATASETS[name]:
            dest = RAW / rel
            if dest.exists():
                print(f"[건너뜀] {rel} ({dest.stat().st_size/1e6:.1f} MB)")
                continue
            print(f"[받는 중] {rel}")
            download(url, dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
