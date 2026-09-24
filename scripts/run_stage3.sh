#!/usr/bin/env bash
# 3단계 전체 실행. 한글 경로 함정 때문에 임시 폴더를 C:/tmp로 돌린다.
# 사용: bash scripts/run_stage3.sh [모델...]   (기본: 모델 7종 전부, 창 30·60)
cd "$(dirname "$0")/.."
mkdir -p C:/tmp/joblib data/processed/stage3
export TMP=C:/tmp TEMP=C:/tmp JOBLIB_TEMP_FOLDER=C:/tmp/joblib LOKY_MAX_CPU_COUNT=8 PYTHONWARNINGS=ignore
# HistGradientBoosting은 내부에서 OpenMP 스레드를 또 만든다. 작업 8개 x 스레드 8개면
# 워커가 강제 종료된다. 스레드를 1로 고정한다.
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
MODELS="${@:-rule dtree logreg rf gboost svm_rbf mlp}"
.venv/Scripts/python.exe -m src.stage3.run --models $MODELS --wins 30 60 --n-jobs ${NJOBS:-6} 2>&1 | grep --line-buffered -v -E "Warning|warnings.warn|out.append" | tee -a data/processed/stage3/run.log
