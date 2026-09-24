# PPG 기반 온디바이스 졸음 감지 SoC — ML 파트

2026 부산대 IDEC 반도체설계 경진대회 · 팀 쿵쿵딱 · 담당 유지현(ML)

이마 착용형 PPG 센서에서 얻은 심박 간격(RR)으로 각성도 저하를 판정하는 모델을 만들고, **고정소수점 Verilog 모듈로 구현**하는 저장소입니다. 학습은 PC에서 오프라인으로 하고 칩에는 추론만 올립니다.

카메라 기반 DMS는 선글라스·야간에 취약하고 조향 패턴 방식은 자율주행 중에 작동하지 않습니다. 행동으로 나타나기 전의 각성도 저하를 생리 신호로 보는 경로를 전용 하드웨어로 구현하는 것이 팀의 접근이고, 대회 성격상 승부처도 기능이 아니라 구현 방식입니다. 그래서 ML 파트는 정확도만이 아니라 **하드웨어 비용(파라미터 수·곱셈 횟수·메모리)을 모델 선정 기준에 포함**합니다.

## 저장소의 범위

전체 경로 중 `<<` 표시 구간이 ML 파트입니다. 아날로그 회로·PCB 설계 파일은 다른 팀원 담당이라 포함하지 않습니다. 제출용 설계 개요(`docs/design-overview.md`)는 팀 문서라 하드웨어 절의 부품 목록이 들어 있습니다.

```
PPG 센서(KT-0805G LED + TEMD6200 PD) → AFE(OPA2333) → ADC(MCP3421, 12bit / 240 SPS)
  → [FPGA: Cmod A7-35T]
       [하드웨어 팀] HPF → LPF → SQI → 피크 검출 → RR → 5초 블록 누산
       → 60초 창 합 (N, ΣRR, 탈락 박동 수)
       → 특징 mean_rb (창 평균 RR ÷ 첫 3분 평균 RR)           <<
       → 문턱 판정 mean_rb ≥ T (정수 교차 곱셈, 나눗셈 없음)   <<
       → IMU(ICM-42670-P) 고개 떨굼 규칙과 OR → alert 펄스     <<
  → [통신] UART → BLE
```

이 구간을 파이썬으로 먼저 구현·검증합니다. 피크 검출과 누산 Verilog는 하드웨어 팀이 짜고, 60초 창 합을 받아 기준선·판정·IMU 결합을 하는 **추론 Verilog는 ML이 구현**합니다. 피크 검출 규칙의 ML 쪽 참조 구현(`rtl/peak_detect.v` 등)은 학습용 RR을 뽑는 데 쓰고 칩에는 들어가지 않습니다(`docs/detector-comparison.md` 7절). 인계 명세는 `docs/datapath-request.md`.

## 접근

PPG와 졸음 라벨이 함께 있는 공개 데이터는 없습니다. 그래서 **RR 간격이라는 공통 표현으로 ECG 데이터에서 학습하고, ECG와 PPG를 동시 기록한 데이터로 둘의 차이를 정량화**하는 구조를 택했습니다.

| 데이터 | 역할 | 라벨 |
|---|---|---|
| MPD-DF (50명) | 주 학습·평가 | 30초 단위 뇌파 판독 5단계 |
| WildPPG (16명) | 이마 PPG 전이 검증: 같은 사람의 ECG·이마 PPG에서 `mean_rb` 비교, 기준선·창 품질 규칙 근거 | 졸음 라벨 없음 |
| PPG-DaLiA (15명) | 움직임 게이팅 필요성 검증(SQI만으로 충분함을 확인), IMU 자세 규칙 헛울림 참고 | 졸음 라벨 없음 |

처음에는 AdVitam Exp4(63명, 30분 단위 KSS)를 외부 검증에 쓰려 했으나 9/30 범위에서 뺐습니다(`docs/data-notes.md`).

모델은 미리 정하지 않고 규칙 기반 단일 문턱부터 결정트리·로지스틱 회귀·랜덤포레스트·부스팅까지 피험자 단위 교차검증(LOSO)으로 비교했습니다. 특징 후보 14개 중 새 사람에게 통한 것은 `mean_rb` 하나였고, 특징이 하나라 로지스틱 회귀는 곧 문턱 규칙이 됩니다. 칩에 들어가는 파라미터는 문턱 T 하나(10비트 정수 `T_FIX` 1086, 헛경보 시간당 4회 동작점)입니다. 결과와 한계는 `docs/model-results.md`, 결정 과정은 `docs/model-comparison-design.md` 11·12절.

단계별 계획은 [docs/ml-plan.md](./docs/ml-plan.md), 특징 후보와 근거는 [docs/feature-rationale.md](./docs/feature-rationale.md), 제출용 설계 개요 초안은 [docs/design-overview.md](./docs/design-overview.md)에 있습니다.

## 저장소 구조

```
docs/design-overview.md        제출용 설계 개요 초안 (배경·타깃·설계 기준·검증). 팀 문서
docs/background-trucking.md    설계 개요의 타깃 근거 자료조사 (화물차·자율주행·규제)
docs/ml-plan.md                ML 파트 구현 계획 (0~7단계), 문제 정의와 평가 지표
docs/data-notes.md             데이터셋 포맷 조사, 라벨 통계, 졸음 사건 통계
docs/feature-rationale.md      특징 후보 14종의 선정 기준과 문헌 근거, 뺀 것의 이유
docs/feature-table-design.md   2단계 특징 표 설계, features.md 는 그 결과
docs/model-comparison-design.md  3단계 모델 비교 설계와 최종 결정 (11절), 사용자 고민 (12절)
docs/model-results.md          3단계 결과 보고서 (자동 생성), stage3-literature.md 는 문헌 근거
docs/integer-inference-design.md 4·7단계 정수 판정식·기준선·비트 폭·시뮬·합성 결과
docs/stage5-ppg-transfer.md    5단계 이마 PPG 전이 검증, 기준선·창 품질 규칙
docs/imu-rule-design.md        6단계 IMU 고개 떨굼 규칙
docs/detector-comparison.md    우리 검출기와 준용 검출기 비교, 역할 분리 결정 (7절)
docs/datapath-request.md       하드웨어 팀 인계 명세: 받는 신호, 판정식, UART 인계, 회로도 검토
docs/hw-design.md              Verilog 구현 설계: 비트 폭, 부등식 변형, 블록 목록, 검증 흐름, 도구
rtl/classifier.v               기준선·창 품질·mean_rb 판정 (정수, 나눗셈 없음)
rtl/imu_rule.v                 IMU 고개 떨굼 자세 규칙
rtl/infer_top.v                ML 블록 최상위: 판정 + IMU 결합 → alert 펄스
rtl/peak_detect.v, sqi.v, window_acc.v, rr_frontend.v   봉우리·SQI·누산 참조 구현 (학습용, 칩 미탑재)
sim/tb_classifier.v, tb_imu_rule.v, tb_rr_frontend.v    파이썬 정답과 비트 대조하는 테스트벤치
sim/vivado_*.tcl, sim/reports/ Vivado 합성 스크립트와 자원·타이밍·전력 리포트
sim/vectors/                   채점 파일 (봉우리·RR·창, 판정 infer/, IMU imu/)
src/infer_ref.py, imu_ref.py   판정·IMU 규칙의 파이썬 정수 기준 모델
src/features.py, src/stage3/   특징 계산, 3단계 모델 비교 실행기·채점기
src/mpd_io.py, peak_simple.py, window_acc.py, peak_eval.py   MPD-DF 읽기, 봉우리·SQI, 누산, 평가
scripts/                       데이터 내려받기, RR 추출, 특징 표, 벡터 생성, 검증 스크립트
data/                          원본·논문·중간 산출물 (git 제외)
```

## 시작하기

```bash
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_data.py   # 스크립트 docstring 참고. WildPPG 는 참가자당 1.1 GB, 따로 받음
```

## 진행 상황

| 단계 | 상태 |
|---|---|
| 0. 환경 준비·데이터 확보 | 완료 (9/7) |
| 도구 (iverilog, yosys, Vivado 2026.1) | 완료 (9/10) |
| 문제 정의·평가 지표·특징 후보 확정 | 완료 (9/12~13) |
| 데이터패스 요청서 (하드웨어 팀 인계) | 완료 (9/14) |
| 1. RR 간격 추출 | 완료 (9/15). 규칙·채점 파일·Verilog 참조 구현 인계 |
| 2. 특징 표 | 완료 (9/18, PR #9) |
| 3. 모델 비교·창 길이 | 완료 (9/19, PR #10). 로지스틱 `mean_rb` 하나, 60초 창 |
| 4. 정수 변환·정답지 | 완료 (9/20, PR #11). `T_FIX` 1086 |
| 5. 이마 PPG 전이 검증 | 완료 (9/24, PR #18). 기준선·창 품질 규칙 추가 |
| 6. IMU 고개 떨굼 규칙 | 완료 (9/23, PR #15) |
| 7. 추론 Verilog·시뮬·합성 | 완료. `infer_top` 불일치 0, Vivado LUT 299·FF 103·DSP 3 (PR #11·#15·#20) |

하드웨어 파트는 아날로그 프론트엔드·ADC 회로 설계와 손가락 부위 브레드보드 측정(심박 82 bpm, dicrotic notch 확인), PCB 아트웍까지 마쳤습니다. PCB 제작과 이마 실측은 제출 범위 밖이며 후속 과제입니다. 일정은 예선 서류 마감 9/30, 발표 10/29이며, **Verilog 구현까지 포함해 9/30에 완성**하는 것을 목표로 합니다. 보드 없이 시뮬레이션과 합성 리포트로 완성을 정의합니다.
