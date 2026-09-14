# PPG 기반 온디바이스 졸음 감지 SoC — ML 파트

2026 부산대 IDEC 반도체설계 경진대회 · 팀 쿵쿵딱 · 담당 유지현(ML)

이마 착용형 PPG 센서에서 얻은 심박 간격(RR)으로 각성도 저하를 판정하는 모델을 만들고, **고정소수점 Verilog 모듈로 구현**하는 저장소입니다. 학습은 PC에서 오프라인으로 하고 칩에는 추론만 올립니다.

카메라 기반 DMS는 선글라스·야간에 취약하고 조향 패턴 방식은 자율주행 중에 작동하지 않습니다. 행동으로 나타나기 전의 각성도 저하를 생리 신호로 보는 경로를 전용 하드웨어로 구현하는 것이 팀의 접근이고, 대회 성격상 승부처도 기능이 아니라 구현 방식입니다. 그래서 ML 파트는 정확도만이 아니라 **하드웨어 비용(파라미터 수·곱셈 횟수·메모리)을 모델 선정 기준에 포함**합니다.

## 저장소의 범위

전체 경로 중 `<<` 표시 구간이 ML 파트입니다. 아날로그 회로·PCB 설계 파일은 다른 팀원 담당이라 포함하지 않습니다. 제출용 설계 개요(`docs/design-overview.md`)는 팀 문서라 하드웨어 절의 부품 목록이 들어 있습니다.

```
PPG 센서(KT-0805G LED + TEMD6200 PD) → AFE(OPA2333) → ADC(MCP3421, 12bit / 240 SPS)
  → [FPGA: Cmod A7-35T]
       FIR 대역통과 필터
       → SQI → 피크 검출 → RR → 5초 블록 누산            (규칙은 ML이 정함) <<
       → 재료 5개 (N, ΣRR, ΣRR², Σd, Σd²)
       → 시간영역 HRV 특징 (후보 15종, 3단계에서 선택)      <<
       → 분류기 (모델 비교 후 확정, 고정소수점 이식)         <<
       → IMU(ICM-42670-P) 규칙 결합 → 판정                  <<
  → UART 출력
```

이 구간을 파이썬으로 먼저 구현·검증합니다. 피크 검출과 누산 Verilog는 하드웨어 팀이 짜고 ML은 **규칙과 테스트 벡터**를 넘기며, 재료 5개를 받아 특징·분류·판정을 내는 **추론 Verilog는 ML이 구현**합니다. 인계 명세는 `docs/datapath-request.md`.

## 접근

PPG와 졸음 라벨이 함께 있는 공개 데이터는 없습니다. 그래서 **RR 간격이라는 공통 표현으로 ECG 데이터에서 학습하고, ECG와 PPG를 동시 기록한 데이터로 둘의 차이를 정량화**하는 구조를 택했습니다.

| 데이터 | 역할 | 라벨 |
|---|---|---|
| MPD-DF (50명) | 주 학습·평가 | 30초 단위 뇌파 판독 5단계 |
| AdVitam Exp4 (63명) | 외부 검증 | 30분 단위 KSS 자기보고 |
| PPG-DaLiA (15명) | ECG↔PPG 차이 정량화, 움직임 게이팅 기준 | 졸음 라벨 없음 |

MPD-DF는 라벨이 30초 단위라 "언제 졸렸는지"를 학습하고 평가할 수 있습니다. AdVitam은 라벨이 성겨 시점 평가는 못 하지만 장비·인구·주행 방식이 전부 다르고 **수면부족을 실험적으로 조작한 유일한 공개 데이터**라, 확정한 모델을 손대지 않고 적용하는 일반화 검증에 씁니다.

모델은 미리 정하지 않습니다. 규칙 기반 단일 임계값(기준선)부터 결정트리·로지스틱 회귀·SVM·랜덤포레스트·소형 MLP까지 **scikit-learn으로 전부 돌려** 민감도·헛경보·하드웨어비용 표로 고릅니다. 평가는 피험자 단위 분할(leave-one-subject-out)로만 하고, 놓침 방지를 우선하므로 주 지표는 사건 단위 민감도입니다. 특징은 국제 표준 지표 전체를 후보로 놓고 창 길이·센서 공통성·샘플링 조건으로 거른 뒤 데이터로 고릅니다.

단계별 계획은 [docs/ml-plan.md](./docs/ml-plan.md), 특징 후보와 근거는 [docs/feature-rationale.md](./docs/feature-rationale.md), 제출용 설계 개요 초안은 [docs/design-overview.md](./docs/design-overview.md)에 있습니다.

## 저장소 구조

```
docs/design-overview.md        제출용 설계 개요 초안 (배경·타깃·설계 기준·검증). 팀 문서
docs/background-trucking.md    설계 개요의 타깃 근거 자료조사 (화물차·자율주행·규제)
docs/ml-plan.md                ML 파트 구현 계획 (0~7단계), 문제 정의와 평가 지표
docs/feature-rationale.md      특징 후보 15종의 선정 기준과 문헌 근거, 뺀 것의 이유
docs/datapath-request.md       하드웨어 팀 인계 명세: 재료 5개, 5초 블록 구조, 신호, 날짜별 인계
docs/hw-design.md              Verilog 구현 설계: 비트 폭, 부등식 변형, 검증 흐름, 도구, 일정
docs/data-notes.md             데이터셋 포맷 조사, 라벨 통계, 졸음 사건 통계
rtl/, sim/                     Verilog 모듈과 테스트벤치 (예정)
scripts/download_data.py       데이터셋 내려받기
scripts/inspect_mpd_labels.py  MPD-DF 라벨 에폭 집계
scripts/inspect_mpd_events.py  MPD-DF 졸음 사건(연속 피로 구간) 통계
data/                          원본·논문·중간 산출물 (git 제외)
```

## 시작하기

```bash
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_data.py   # MPD-DF + AdVitam Exp4 + PPG-DaLiA, 약 6.5GB
```

## 진행 상황

| 단계 | 상태 |
|---|---|
| 0. 환경 준비·데이터 확보 | 완료 (9/7) |
| 도구 (iverilog, yosys, Vivado 2026.1) | 완료 (9/10) |
| 문제 정의·평가 지표·특징 후보 확정 | 완료 (9/12~13) |
| 데이터패스 요청서 (하드웨어 팀 인계) | 완료 (9/14) |
| 1. RR 간격 추출 | 진행 중, 9/15 |
| 2~7 | 대기 |

하드웨어 파트는 아날로그 프론트엔드·ADC 회로 설계와 손가락 부위 브레드보드 측정(심박 82 bpm, dicrotic notch 확인), PCB 아트웍까지 마쳤습니다. PCB 제작과 이마 실측은 제출 범위 밖이며 후속 과제입니다. 일정은 예선 서류 마감 9/30, 발표 10/29이며, **Verilog 구현까지 포함해 9/30에 완성**하는 것을 목표로 합니다. 보드 없이 시뮬레이션과 합성 리포트로 완성을 정의합니다.
