#!/usr/bin/env bash
# PPG-DaLiA 전처리를 분리 프로세스로. 로그는 data/interim/dalia/prep.log
cd "$(dirname "$0")/.."
mkdir -p data/interim/dalia
export TMP=C:/tmp TEMP=C:/tmp PYTHONWARNINGS=ignore
L=data/interim/dalia/prep.log
echo "$(date +%H:%M:%S)    START" >> "$L"
.venv/Scripts/python.exe scripts/dalia_prep.py >> "$L" 2>&1
echo "$(date +%H:%M:%S)    EXIT $?" >> "$L"
