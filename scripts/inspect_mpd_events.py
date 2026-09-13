"""MPD-DF 졸음 '사건' 단위 통계.

inspect_mpd_labels.py 는 에폭을 세었다. 이 스크립트는 연속된 피로 구간을
하나의 사건으로 묶어서 센다. 목적이 "졸음이 오는 전조를 놓치지 않는 것"이면
평가 단위가 에폭이 아니라 사건이어야 하기 때문이다. 한 졸음 구간에서 한 번만
울려도 운전자는 깬다.

확인하는 것:
  1. 사건이 몇 번 일어나고 얼마나 지속되는가
  2. 짧은 사건이 많으면 '연속 N회일 때 경보' 규칙이 사건을 통째로 놓친다
  3. 피로1이 정말 전조인가. 뒤에 더 깊은 단계가 오는가, 그냥 각성으로 돌아가는가

    python scripts/inspect_mpd_events.py
"""

import collections
import csv
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "mpd_df"
EPOCH_SEC = 30
EXCLUDE = {"Severe Artifacts", "Signal Abnormality"}


def edf_seconds(path):
    with path.open("rb") as fh:
        fh.seek(236)
        n_rec = int(fh.read(8).decode("ascii"))
        dur = float(fh.read(8).decode("ascii"))
    return n_rec * dur


def expand(anno_path, total_epochs):
    rows = [r for r in csv.reader(anno_path.open(encoding="utf-8")) if len(r) >= 3]
    marks = []
    for r in rows:
        value = r[2].strip()
        marks.append((int(r[1]), int(value) if value.isdigit() else value))
    labels = [None] * (total_epochs + 1)
    for (start, level), (nxt, _) in zip(marks, marks[1:] + [(total_epochs + 1, None)]):
        for e in range(start, min(nxt, total_epochs + 1)):
            labels[e] = level
    return [l for l in labels[1:] if l is not None]


def runs_of_fatigue(labels):
    """연속된 피로(1 이상) 구간을 (길이, 최고 단계) 목록으로 반환.

    아티팩트 에폭은 상태를 모르는 구간이므로 사건을 끊는다.
    """
    out = []
    cur_len = 0
    cur_max = 0
    for l in labels:
        if isinstance(l, int) and l >= 1:
            cur_len += 1
            cur_max = max(cur_max, l)
        else:
            if cur_len:
                out.append((cur_len, cur_max))
            cur_len = 0
            cur_max = 0
    if cur_len:
        out.append((cur_len, cur_max))
    return out


def main():
    subjects = sorted(RAW.glob("*_Annotation.txt"))
    if not subjects:
        print("라벨 파일이 없다.")
        return 1

    all_runs = []
    per_subject = []
    deeper_after_1 = collections.Counter()

    for anno in subjects:
        code = anno.name.replace("_Annotation.txt", "")
        edf = RAW / f"{code}_PSG.edf"
        n_epochs = int(edf_seconds(edf) // EPOCH_SEC) if edf.exists() else None
        labels = expand(anno, n_epochs)
        runs = runs_of_fatigue(labels)
        all_runs.extend(runs)
        per_subject.append((code, len(labels), len(runs)))
        for length, top in runs:
            deeper_after_1["깊어짐" if top >= 2 else "피로1에 머무름"] += 1

    n = len(all_runs)
    lengths = sorted(r[0] for r in all_runs)
    total_epochs = sum(lengths)

    print(f"피험자 {len(subjects)}명, 졸음 사건 {n}건, 피로 에폭 {total_epochs}개")
    print(f"사건당 평균 {total_epochs / n:.1f}에폭 = {total_epochs / n * EPOCH_SEC:.0f}초")
    print(f"중앙값 {lengths[n // 2]}에폭 = {lengths[n // 2] * EPOCH_SEC}초")
    print(f"사람당 평균 {n / len(subjects):.1f}건")

    print("\n사건 길이 분포")
    buckets = [(1, 1), (2, 2), (3, 4), (5, 10), (11, 20), (21, 10**9)]
    for lo, hi in buckets:
        c = sum(1 for x in lengths if lo <= x <= hi)
        label = f"{lo}에폭" if lo == hi else (f"{lo}~{hi}에폭" if hi < 10**9 else f"{lo}에폭 이상")
        secs = f"({lo * EPOCH_SEC}~{hi * EPOCH_SEC}초)" if hi < 10**9 else f"({lo * EPOCH_SEC}초 이상)"
        print(f"  {label:>12} {secs:>14} : {c:4d}건 {c / n * 100:5.1f}%  {'#' * (c * 40 // n)}")

    print("\n윈도우 길이별로 '내용이 전부 피로인 창'이 하나도 안 생기는 사건")
    print("  창은 30초(에폭 1칸)씩 미끄러진다. 길이 W에폭짜리 창이 사건 안에")
    print("  완전히 들어가는 횟수는 max(0, L-W+1)이다. 0이면 그 사건은 항상")
    print("  각성 구간과 섞인 창으로만 보이므로 특징이 희석된다.")
    for w in (1, 2, 4):
        blind = sum(1 for x in lengths if x - w + 1 <= 0)
        full = sum(max(0, x - w + 1) for x in lengths)
        print(f"  창 {w * EPOCH_SEC:3d}초: 희석만 되는 사건 {blind:3d}건 "
              f"({blind / n * 100:4.1f}%), 순수 피로 창 {full}개")

    print("\n피로1이 더 깊은 단계로 진행하는가")
    for k, v in deeper_after_1.most_common():
        print(f"  {k}: {v}건 ({v / n * 100:.1f}%)")

    print("\n사건이 아예 없는 피험자")
    zero = [c for c, _, r in per_subject if r == 0]
    print(f"  {len(zero)}명: {', '.join(zero) if zero else '없음'}")
    few = [(c, r) for c, _, r in per_subject if 0 < r <= 2]
    print(f"  사건이 1~2건뿐인 피험자: {len(few)}명")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
