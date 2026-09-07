"""공개 데이터셋 내려받기.

사용법:
    python scripts/download_data.py            # 기본 세트 (advitam, ppg-dalia)
    python scripts/download_data.py advitam
    python scripts/download_data.py --list

중단되면 같은 명령을 다시 실행한다. 이미 받은 파일은 건너뛴다.

AdVitam은 4GB짜리 zip 하나를 통째로 받지 않고, 그 안에서 필요한 항목만
HTTP Range로 골라 받는다(2.6GB). 쓰지 않는 .acq 원본과 주행 로그를 빼는 것도 있지만,
회선이 끊겼을 때 파일 하나만 다시 받으면 되는 게 더 크다.
"""

import argparse
import gzip
import hashlib
import http.client
import io
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
# Zenodo는 "Mozilla/5.0"처럼 짧은 User-Agent를 403으로 막는다.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HEADERS = {"User-Agent": UA, "Accept": "*/*"}
RETRIES = 5
# Zenodo 연결이 자주 끊긴다. IncompleteRead는 OSError가 아니라 HTTPException이라 따로 잡아야 한다.
NET_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, EOFError)

ADVITAM_EXP4 = "https://zenodo.org/api/records/7319612/files/Exp4.zip/content"
ADVITAM_FILE = "https://zenodo.org/api/records/7319612/files/{}/content"
PPG_DALIA = "https://archive.ics.uci.edu/static/public/495/ppg+dalia.zip"
MPD_DF_API = "https://api.figshare.com/v2/articles/28455737"


# --- 원격 zip: 파일 전체를 받지 않고 필요한 항목만 읽는다 -------------------

class HttpFile(io.RawIOBase):
    """Range 요청으로 임의 위치를 읽는 읽기 전용 파일 객체."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        req = urllib.request.Request(url, headers={**HEADERS, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status != 206:
                raise RuntimeError("서버가 Range 요청을 지원하지 않는다")
            self.size = int(resp.headers["Content-Range"].split("/")[1])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def _get(self, n):
        if n <= 0:
            return b""
        end = min(self.pos + n, self.size) - 1
        req = urllib.request.Request(self.url, headers={**HEADERS, "Range": f"bytes={self.pos}-{end}"})
        for attempt in range(1, RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = resp.read()
                    if len(data) != end - self.pos + 1:
                        raise http.client.IncompleteRead(data, end - self.pos + 1 - len(data))
                break
            except NET_ERRORS:
                if attempt == RETRIES:
                    raise
                time.sleep(3 * attempt)
        self.pos += len(data)
        return data

    def read(self, n=-1):
        return self._get(self.size - self.pos if n is None or n < 0 else n)

    def readinto(self, buf):
        data = self._get(len(buf))
        buf[:len(data)] = data
        return len(data)


def finalize(part, dest):
    """.part를 최종 이름으로 바꾼다.

    윈도우에서는 방금 닫은 파일을 백신·인덱서가 잠시 잡고 있어
    바로 이름을 바꾸면 WinError 32가 난다. 몇 번 다시 시도한다.
    """
    for attempt in range(1, 11):
        try:
            part.replace(dest)
            return
        except PermissionError:
            if attempt == 10:
                raise
            time.sleep(0.5 * attempt)


def advitam_wanted(names):
    """Exp4.zip에서 실제로 쓰는 항목만 고른다.

    제외: Raw/Physio/BioPac (ECG txt와 같은 신호의 BioPac 전용 포맷, 1.2GB)
          Raw/Driving (핸들·페달 로그. PVT 반응시간은 Preprocessed/PVT에 이미 있다)
    """
    for n in names:
        if n.endswith("/"):
            continue
        if "/Physio/BioPac/" in n or "/Raw/Driving/" in n:
            continue
        yield n


def fetch_members(url, wanted, out_dir):
    """원격 zip에서 항목을 하나씩 받아 저장한다. 큰 txt는 gzip으로 눌러 둔다."""
    zf = zipfile.ZipFile(io.BufferedReader(HttpFile(url), buffer_size=1 << 20))
    names = list(wanted(zf.namelist()))
    todo = []
    for name in names:
        dest = out_dir / name
        if name.endswith(".txt") and zf.getinfo(name).file_size > 10_000_000:
            dest = dest.with_suffix(".txt.gz")
        if not dest.exists():
            todo.append((name, dest))
    print(f"  전체 {len(names)}개 중 {len(todo)}개 남음")

    for i, (name, dest) in enumerate(todo, 1):
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        size = zf.getinfo(name).file_size
        for attempt in range(1, RETRIES + 1):
            try:
                opener = gzip.open if dest.suffix == ".gz" else open
                with zf.open(name) as src, opener(part, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                break
            except NET_ERRORS + (zipfile.BadZipFile,) as exc:
                print(f"    {name} 실패({attempt}/{RETRIES}): {exc}")
                if attempt == RETRIES:
                    raise
                time.sleep(5 * attempt)
                zf = zipfile.ZipFile(io.BufferedReader(HttpFile(url), buffer_size=1 << 20))
        finalize(part, dest)
        print(f"  [{i}/{len(todo)}] {name}  ({size/1e6:.1f} MB)")


# --- 통짜 파일 받기 ---------------------------------------------------------

def download(url, dest, check_zip=False, md5=None):
    """이어받기와 재시도. 서버가 크기를 알려주면 다 받았는지 확인한 뒤 이름을 바꾼다."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    for attempt in range(1, RETRIES + 1):
        done = part.stat().st_size if part.exists() else 0
        headers = dict(HEADERS)
        if done:
            headers["Range"] = f"bytes={done}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as resp:
                if done and resp.status != 206:   # 이어받기 거부 → 처음부터
                    done = 0
                length = resp.headers.get("Content-Length")
                total = int(length) + done if length else 0
                with open(part, "ab" if done else "wb") as fh:
                    while chunk := resp.read(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        print(f"\r  {dest.name}  {done/1e6:8.1f}"
                              + (f" / {total/1e6:.1f} MB" if total else " MB"), end="", flush=True)
            print()
        except NET_ERRORS as exc:
            print(f"\n  끊김({attempt}/{RETRIES}): {exc}")
            time.sleep(5 * attempt)
            continue

        # 다 받았는지 확인. 서버가 크기를 안 주면(UCI) zip을 열어서 확인한다.
        if total and done < total:
            print(f"  {done/1e6:.1f} / {total/1e6:.1f} MB 만 받음. 이어서 받는다.")
            continue
        if md5:
            digest = hashlib.md5()
            with open(part, "rb") as fh:
                while chunk := fh.read(1 << 20):
                    digest.update(chunk)
            if digest.hexdigest() != md5:
                print("  md5가 다르다. 처음부터 다시 받는다.")
                part.unlink()
                continue
        if check_zip:
            try:
                zipfile.ZipFile(part).namelist()
            except zipfile.BadZipFile:
                print("  zip이 깨졌다. 처음부터 다시 받는다.")
                part.unlink()
                continue
        finalize(part, dest)
        return
    raise RuntimeError(f"{dest.name} 내려받기 실패")


# --- 항목 ------------------------------------------------------------------

def get_advitam():
    for key in ("README.md", "physiological_indicators.xlsx"):
        dest = RAW / "advitam" / key
        if not dest.exists():
            download(ADVITAM_FILE.format(key), dest)
    fetch_members(ADVITAM_EXP4, advitam_wanted, RAW / "advitam")


def get_ppg_dalia():
    dest = RAW / "ppg_dalia" / "ppg+dalia.zip"
    if dest.exists():
        print("  [건너뜀] ppg+dalia.zip")
        return
    # UCI는 Content-Length도 Range도 주지 않는다. 끊기면 처음부터 다시 받아야 한다.
    download(PPG_DALIA, dest, check_zip=True)


def get_mpd_df():
    """figshare에서 심전도(PSG)와 30초 단위 라벨만 받는다.

    전체는 13.1GB지만 그중 11.9GB가 32채널 뇌파라 쓰지 않는다.
    """
    req = urllib.request.Request(MPD_DF_API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        files = json.load(resp)["files"]

    wanted = [f for f in files
              if f["name"].endswith(("_PSG.edf", "_Annotation.txt", ".xlsx"))]
    out = RAW / "mpd_df"
    todo = [f for f in wanted if not (out / f["name"]).exists()]
    print(f"  전체 {len(wanted)}개 중 {len(todo)}개 남음")
    for i, f in enumerate(todo, 1):
        # API가 알려주는 ndownloader.figshare.com은 403을 낸다.
        # figstatic.com이 같은 파일을 서명된 S3 주소로 넘겨주고 이어받기도 된다.
        url = f["download_url"].replace("ndownloader.figshare.com", "ndownloader.figstatic.com")
        download(url, out / f["name"], md5=f["computed_md5"])
        print(f"  [{i}/{len(todo)}] {f['name']}")


DATASETS = {
    "advitam": get_advitam,      # Exp4에서 필요한 항목만, 약 2.6GB
    "ppg-dalia": get_ppg_dalia,  # 약 2.7GB
    "mpd-df": get_mpd_df,        # 심전도와 라벨만, 약 1.2GB
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help=f"기본값: {' '.join(DATASETS)}")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for name in DATASETS:
            print(name)
        return 0

    for name in args.names or list(DATASETS):
        if name not in DATASETS:
            print(f"알 수 없는 항목: {name}", file=sys.stderr)
            return 1
        print(f"[{name}]")
        DATASETS[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
