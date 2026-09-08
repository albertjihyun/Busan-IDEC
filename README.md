# PPG 기반 온디바이스 졸음 감지 SoC — ML 파트

2026 부산대 IDEC 반도체설계 경진대회 · 팀 쿵쿵딱 · 담당 유지현(ML)

이마 착용형 PPG 센서에서 얻은 심박 간격(RR)으로 졸음을 판단하는 모델을 만들고, **고정소수점 Verilog 모듈로 구현**하는 저장소입니다. 학습은 PC에서 오프라인으로 하고 칩에는 추론만 올립니다.

카메라 기반 DMS는 선글라스·야간에 취약하고 조향 패턴 방식은 자율주행 중에 작동하지 않습니다. 생리 신호로 졸음의 전조를 보는 경로를 전용 하드웨어로 구현하는 것이 팀의 접근이고, 대회 성격상 승부처도 기능이 아니라 구현 방식입니다. 그래서 ML 파트는 정확도만이 아니라 **하드웨어 비용(파라미터 수·곱셈 횟수·메모리)을 모델 선정 기준에 포함**합니다.

## 저장소의 범위

전체 경로 중 `<<` 표시 구간이 ML 파트입니다. 아날로그 회로·PCB는 다른 팀원 담당이라 포함하지 않습니다.

```
PPG 센서(BPW34) → AFE(OPA333) → ADC(MCP3421, 12bit / 240 SPS)
  → [FPGA: Cmod A7-35T]
       FIR 대역통과 필터
       → SQI (신호 품질 검사)                              <<
       → 피크 검출 → RR 간격                               <<
       → 시간영역 HRV 특징 (mean RR, SDNN, RMSSD, pNN50)    <<
       → 분류기 (모델 비교 후 확정, 고정소수점 이식)         <<
       → IMU(MPU6050) 규칙 결합 → 졸음 판정                 <<
  → UART 출력
```

이 구간을 파이썬으로 먼저 구현·검증한 뒤, 고정소수점으로 옮겨 **Verilog로 구현**합니다. 하드웨어 팀에는 **테스트 벡터 · IMU 결합 규칙 · 인터페이스 명세**를 함께 넘깁니다.

## 접근

PPG와 졸음 라벨이 함께 있는 공개 데이터는 없습니다. **RR 간격이라는 공통 표현으로 ECG 데이터(AdVitam)에서 학습하고, ECG와 PPG를 동시 기록한 PPG-DaLiA로 둘의 차이를 정량화**하는 구조를 택했습니다.

모델은 미리 정하지 않고 규칙 기반부터 소형 MLP까지 비교해 정확도-하드웨어비용 표로 고릅니다. 평가는 피험자 단위 분할(leave-one-subject-out)로만 합니다.

단계별 계획과 참고 문헌은 [docs/ml-plan.md](./docs/ml-plan.md)에 있습니다.

## 저장소 구조

```
docs/ml-plan.md           ML 파트 구현 계획 (0~7단계)
docs/data-notes.md        데이터셋 포맷 조사 결과
scripts/download_data.py  데이터셋 내려받기
data/raw/                 원본 데이터 (git 제외)
```

## 시작하기

```bash
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_data.py   # AdVitam Exp4 + PPG-DaLiA, 약 5.6GB
```

## 진행 상황

| 단계 | 상태 |
|---|---|
| 0. 환경 준비·데이터 확보 | 진행 중 |
| 1. RR 간격 추출 | 대기 |
| 2~7 | 대기 |

하드웨어 파트는 아날로그 프론트엔드·ADC 설계와 브레드보드 실측(심박 82 bpm, dicrotic notch 확인)을 마쳤고 통합 프로토타입 PCB 아트웍이 진행 중입니다. 일정은 예선 서류 마감 9/30, 발표 10/29입니다.
