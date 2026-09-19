#!/usr/bin/env bash
# 남은 실행: 부스팅 두 창 → 랜덤포레스트 60초. 분리 프로세스로 띄운다.
cd "$(dirname "$0")/.."
mkdir -p C:/tmp/joblib
export TMP=C:/tmp TEMP=C:/tmp JOBLIB_TEMP_FOLDER=C:/tmp/joblib LOKY_MAX_CPU_COUNT=8 PYTHONWARNINGS=ignore
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1   # 9/18 15:09 워커 강제종료 방지
L=data/processed/stage3/run.log
.venv/Scripts/python.exe -m src.stage3.run --models gboost --wins 30 60 --n-jobs 6 2>&1 | grep --line-buffered -v -E "Warning|warnings.warn" >> "$L"
.venv/Scripts/python.exe -m src.stage3.run --models rf --wins 60 --n-jobs 6 2>&1 | grep --line-buffered -v -E "Warning|warnings.warn" >> "$L"
echo "$(date +%H:%M:%S)    ALL DONE" >> "$L"
