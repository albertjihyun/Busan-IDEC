"""MPD-DF 라벨 요약.

Annotation.txt는 30초 에폭 단위인데 에폭마다 한 줄이 아니라 상태가 바뀌는
지점만 적혀 있다. 이를 펼쳐서 피험자별 클래스 비율을 본다.

    python scripts/inspect_mpd_labels.py
"""

import collections
import csv
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "mpd_df"
EPOCH_SEC = 30
LEVEL_NAME = {0: "각성", 1: "피로1", 2: "피로2", 3: "N1", 4: "N2"}
# 라벨 자리에 숫자 대신 품질 표시가 오기도 한다. 그 구간은 학습·평가에서 뺀다.
EXCLUDE = {"Severe Artifacts", "Signal Abnormality"}


def edf_seconds(path):
    """EDF 헤더에서 기록 길이(초)를 읽는다."""
    with path.open("rb") as fh:
        fh.seek(236)                       # 데이터 레코드 수 위치
        n_rec = int(fh.read(8).decode("ascii"))
        dur = float(fh.read(8).decode("ascii"))
    return n_rec * dur


def expand(anno_path, total_epochs):
    """전이 목록을 에폭별 라벨 배열로 펼친다."""
    rows = [r for r in csv.reader(anno_path.open(encoding="utf-8")) if len(r) >= 3]
    marks = []
    for r in rows:
        value = r[2].strip()
        marks.append((int(r[1]), int(value) if value.isdigit() else value))
    labels = [None] * (total_epochs + 1)   # 에폭 번호는 1부터
    for (start, level), (nxt, _) in zip(marks, marks[1:] + [(total_epochs + 1, None)]):
        for e in range(start, min(nxt, total_epochs + 1)):
            labels[e] = level
    return [l for l in labels[1:] if l is not None]


def main():
    subjects = sorted(RAW.glob("*_Annotation.txt"))
    if not subjects:
        print("라벨 파일이 없다. scripts/download_data.py mpd-df 를 먼저 실행한다.")
        return 1

    total = collections.Counter()
    per_subject = []
    for anno in subjects:
        code = anno.name.replace("_Annotation.txt", "")
        edf = RAW / f"{code}_PSG.edf"
        n_epochs = int(edf_seconds(edf) // EPOCH_SEC) if edf.exists() else None
        labels = expand(anno, n_epochs)
        counts = collections.Counter(labels)
        total.update(counts)
        scored = [l for l in labels if isinstance(l, int)]
        fatigue = sum(1 for l in scored if l >= 1)
        per_subject.append((code, len(labels), counts, fatigue / len(scored) if scored else 0))

    print(f"피험자 {len(per_subject)}명, 에폭 {sum(total.values()):,}개 "
          f"({sum(total.values()) * EPOCH_SEC / 3600:.1f}시간)\n")

    print("전체 라벨 분포")
    grand = sum(total.values())
    for level in sorted(total, key=lambda x: (isinstance(x, str), x)):
        c = total[level]
        name = LEVEL_NAME.get(level, "제외") if isinstance(level, int) else "제외"
        print(f"  {str(level):<20} {name:<5} {c:6,}개 "
              f"({c * EPOCH_SEC / 3600:5.1f}시간, {100 * c / grand:5.1f}%)")
    scored = sum(c for l, c in total.items() if isinstance(l, int))
    fatigue = sum(c for l, c in total.items() if isinstance(l, int) and l >= 1)
    dropped = grand - scored
    print(f"\n품질 문제로 제외: {dropped:,}개 ({100 * dropped / grand:.1f}%)")
    print(f"\n남은 것 기준 이진: 각성 {100 * (scored - fatigue) / scored:.1f}% : 피로 {100 * fatigue / scored:.1f}%")

    ratios = sorted(r for *_, r in per_subject)
    print(f"\n피험자별 피로 비율: 최소 {ratios[0]:.1%}, 중앙값 {ratios[len(ratios)//2]:.1%}, "
          f"최대 {ratios[-1]:.1%}")
    none_ = [c for c, _, _, r in per_subject if r == 0]
    all_ = [c for c, _, _, r in per_subject if r == 1]
    if none_:
        print(f"  피로 구간이 전혀 없는 피험자 {len(none_)}명: {', '.join(none_)}")
    if all_:
        print(f"  전 구간이 피로인 피험자 {len(all_)}명: {', '.join(all_)}")

    print("\n피험자별 (피로 비율 순)")
    for code, n, counts, ratio in sorted(per_subject, key=lambda x: -x[3]):
        dist = " ".join(f"{l}:{counts[l]}" for l in sorted(counts, key=lambda x: (isinstance(x, str), x)))
        print(f"  {code:<16} 에폭 {n:4d}  피로 {ratio:5.1%}   {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
