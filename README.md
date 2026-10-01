# 이마 PPG·IMU 기반 졸음 감지 SoC — 판정 블록

2026 부산대 IDEC 반도체설계 경진대회 · 팀 쿵쿵딱 · 판정 블록 담당 유지현

제출한 설계설명서: [docs/쿵쿵딱_설계설명서.pdf](docs/쿵쿵딱_설계설명서.pdf) (참가신청서 쪽은 개인정보가 있어 뺐습니다)

## 개요

자율주행 보조가 조향을 맡으면 차선 이탈이나 조향 입력으로 졸음을 알아내던 방식은 쓸 수 없고, 카메라는 역광과 선글라스에 약합니다. 이 과제는 장거리 화물 운전자의 각성도 저하를 운전 행동이 아닌 몸의 신호로 알아낼 수 있는가라는 질문에서 출발해, 이마의 PPG(광용적맥파)와 IMU(관성 측정 장치)로 각성도 저하를 감지하는 졸음 감지 SoC를 설계했습니다. 센서 읽기부터 신호처리, 판정, 경보 송신까지를 범용 프로세서 없이 전용 회로로 처리하고, 칩 밖으로는 경보 한 바이트만 내보냅니다.

시스템은 네 블록으로 나뉩니다. 이 저장소는 그중 `<<` 표시한 **판정 블록**(설명서 3.4절)의 근거 자료와 구현입니다. 하드웨어·신호처리·통신 블록은 다른 팀원 담당이라 들어 있지 않습니다.

```
하드웨어 블록   이마 센서 보드: LED·PD → AFE → ADC(MCP3421, 12비트 240 SPS), IMU(ICM-42670-P)
                 └ I²C 버스 하나
신호처리 블록   PPG: 기저선 제거·FIR → 신호 품질 검사 → 피크 검출 → 박동 간격 → 60초 창 합 (5초마다)
                IMU: 가속도 전달, 자이로 끄덕임 검출
판정 블록  <<   심박 판정: 창 품질 확인 → 개인 기준선 대비 비율 ≥ 문턱 → 경보 간격 30초
                고개 떨굼 판정: 가속도 자세 규칙
                두 결과를 OR → 경보 펄스
통신 블록       UART → BLE 모듈(JDY-23) → 스마트폰, 경보마다 0x01 한 바이트
```

칩 전체는 Verilog RTL로 설계해 FPGA(Cmod A7-35T, 12 MHz)에 구현했고 LUT의 17.5%를 씁니다. 판정 블록은 그중 약 6%(LUT 207)입니다.

## 판정 블록의 설계

**학습 데이터.** PPG와 졸음 라벨을 함께 기록한 공개 데이터는 찾지 못했습니다. 라벨이 촘촘하고, 객관적 판독에 근거하며, 원시 심박 파형이 칩의 표본화율(240 Hz) 이상으로 기록된 데이터는 MPD-DF(운전 시뮬레이터 50명, 의사의 뇌파 판독으로 30초마다 피로 단계, ECG 1024 Hz)였습니다. 칩은 이마 PPG를 보므로 ECG와 PPG에 공통인 박동 간격을 매개로 삼았고, 같은 사람의 흉골 ECG와 이마 PPG를 동시 기록한 WildPPG 15명에서 두 신호의 판정이 97.4% 일치하는 것을 확인했습니다. 학습용 박동 간격을 뽑는 검출기는 파이썬으로만 있고, 칩에는 신호처리 블록의 PPG용 검출기가 들어갑니다.

| 데이터 | 쓴 곳 | 졸음 라벨 |
|---|---|---|
| MPD-DF (50명) | 모델 학습과 판정 성능 평가 | 피로 단계 (뇌파 판독, 30초) |
| WildPPG (15명) | 이마 PPG와 ECG의 판정 일치, 창 품질·기준선 규칙 | 없음 |
| PPG-DaLiA (15명) | 고개 떨굼 규칙의 헛경보 (가슴 가속도로 이마 대용) | 없음 |

**모델 선정.** 처음 보는 사람에 대한 성능과 함께 칩에 올릴 파라미터 크기와 판정당 곱셈 수를 선정 기준으로 두었습니다. 사람 단위 교차검증(LOSO, 50회)으로 규칙·얕은 결정트리·로지스틱 회귀·랜덤포레스트·부스팅을 비교한 결과, 개인 기준선 대비 60초 평균 박동 간격의 비율 하나를 쓰는 로지스틱 회귀가 가장 좋았습니다. 특징이 하나라 문턱 비교와 같아서, 칩에 들어가는 학습 값은 문턱 하나(`T_FIX` = 1086, 소수 10비트)입니다. 졸음에 따른 변화(중앙값 0.9%)가 같은 사람이 깨어 있을 때의 흔들림(3.3%)보다 작아, 판별력은 이 신호로 도달할 수 있는 이론적 상한(AUC 0.57)에 가깝습니다(실측 0.60).

**판정 보류.** 통과 박동이 30개 미만이거나 통과 비율이 75% 미만인 창, 그리고 기준선이 확정되기 전(좋은 1분 창 3개)에는 심박 판정을 보류합니다. 보류 중에도 고개 떨굼은 따로 감시합니다.

**고개 떨굼.** 이마 가속도의 앞쪽 축이 sin 35° 이상이고 세로축이 cos 35° 이하인 상태가 0.5초 이어지면 경보합니다. 두 축을 함께 보아 급제동과 구별하고, 신호처리 블록의 자이로 끄덕임 검출(착용 방향 부호가 확정된 뒤)과 OR로 합칩니다.

**정수 구현.** 기준선 대비 비율을 구하는 나눗셈은 양변에 양수를 곱한 교차 곱셈 `2^10 · S · N_b ≥ T_FIX · S_b · n`으로 바꿔, 곱셈 셋과 비교만으로 판정합니다. 근사는 문턱의 반올림 하나이고, 나눗셈기와 블록 메모리가 없습니다.

## 결과

| 항목 | 값 |
|---|---|
| 판정 성능, 학습에 쓰지 않은 사람 (헛경보 시간당 4회) | 구간 민감도 0.413 [0.28–0.53], 피로 2단계 이상 구간 0.633 [0.48–0.80] |
| 칩이 실제로 내보내는 경보 (50명, 30초 경보 간격 포함) | 구간 민감도 0.406, 피로 2단계 이상 구간 0.600, 헛경보 시간당 4.36회 |
| RTL과 파이썬 정수 기준 모델 대조 | 50명 75,186블록 + 경계 278블록 불일치 0 |
| 판정 → 통신 연결 | 경보 3,154개 = UART 수신 3,154바이트, 프레이밍 오류 0 |
| 보류 중 고개 떨굼 | 14건 모두 경보 |
| 고개 떨굼 헛경보 (PPG-DaLiA 운전 3.8시간) | 0회 |
| 합성 (xc7a35t, Vivado 2026.1, 12 MHz) | 판정 블록 단독 LUT 305·FF 107·DSP 3·블록 메모리 0, WNS 72.3 ns. 칩 전체에 통합하면 LUT 207 |

구간 민감도는 연속된 피로 1단계 이상 라벨을 한 구간으로 보고, 경보가 걸린 구간의 비율로 셉니다. 판정 성능 줄은 모델 비교와 같은 조건(30초마다 판정 하나)이고, 칩 줄은 5초마다 내린 판정에 경보 간격을 적용한 실제 출력입니다.

## 한계

모든 결과는 센서 보드를 제작하기 전 단계에서 얻었습니다. 판정 성능은 기준을 충족한 유일한 공개 데이터인 MPD-DF(시뮬레이터, 수면 박탈 없음)에서 나온 값이고, 이마 PPG는 ECG와의 판정 일치까지, 고개 떨굼은 합성 시나리오와 가슴 가속도까지 확인했습니다. 판정은 출발 시 깨어 있는 운전을 전제로 하며, 운행이 길어지면 깨어 있어도 심박이 느려져 헛경보가 늘어납니다. 창 품질 기준과 떨굼 문턱은 착용 실측 뒤 조정하도록 파라미터로 두었습니다.

## 저장소 구조

```
docs/쿵쿵딱_설계설명서.pdf          제출한 설계설명서 (2장 설계 개요, 3장 설계기술 설명)
docs/design-overview.md          설계 개요 초안 (배경·타깃·설계 기준·검증). 제출 전 팀 문서
docs/background-trucking.md      설계 개요의 타깃 근거 자료조사 (화물차·자율주행·규제)
docs/ml-plan.md                  판정 블록 구성, 문제 정의와 평가 지표
docs/data-notes.md               데이터셋 포맷, 라벨 통계, 졸음 사건 통계
docs/feature-rationale.md        특징 후보 14종의 선정 기준과 문헌 근거
docs/feature-table-design.md     특징 표 설계. features.md 는 그 결과
docs/detector-comparison.md      학습 검출기와 칩 검출기 비교, 역할 분리
docs/model-comparison-design.md  모델 비교 설계, 최종 결정, 예상 질문
docs/model-results.md            모델 비교 결과 (자동 생성). stage3-literature.md 는 문헌 근거
docs/integer-inference-design.md 정수 판정식·기준선·비트 폭·시뮬·합성 결과
docs/stage5-ppg-transfer.md      이마 PPG 전이 검증, 기준선·창 품질 규칙
docs/imu-rule-design.md          IMU 고개 떨굼 규칙
docs/interface-spec.md           신호처리·판정·통신 블록 사이 인터페이스, 회로도 대조
rtl/classifier.v                 기준선·창 품질·비율 판정 (정수, 나눗셈 없음)
rtl/imu_rule.v                   IMU 고개 떨굼 자세 규칙
rtl/infer_top.v                  판정 블록 최상위: 심박 판정 + 고개 떨굼 결합 → 경보 펄스
sim/tb_classifier.v, tb_imu_rule.v   파이썬 정답과 비트 대조하는 테스트벤치
sim/tb_infer_uart.v              판정 → 통신 블록(data/communication_module) 연결 채점
sim/vectors/                     테스트 벡터 (판정 infer/, IMU imu/)
sim/vivado_infer_top.tcl, reports/   Vivado 합성 스크립트와 자원·타이밍·전력 리포트
src/infer_ref.py, imu_ref.py     판정·IMU 규칙의 파이썬 정수 기준 모델
src/features.py, src/stage3/     특징 계산, 모델 비교 실행기·채점기
src/mpd_io.py, peak_simple.py, window_acc.py, peak_eval.py   MPD-DF 읽기, 학습 검출기, 5초 블록 누산, 검출 평가
scripts/                         데이터 내려받기, RR 추출, 특징 표, 벡터 생성, 설명서 그림, 검증 스크립트
data/                            원본·중간 산출물 (git 제외)
```

## 시작하기

```bash
python -m venv .venv
.venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_data.py   # 스크립트 docstring 참고. WildPPG 는 참가자당 1.1 GB, 따로 받음
```

## 개발 도구

| 용도 | 도구 |
|---|---|
| 시뮬레이션 | Icarus Verilog (OSS CAD Suite). 통신 블록 테스트벤치는 `-g2012` 필요 |
| 자원 추정 | Yosys `synth_xilinx -family xc7` (OSS CAD Suite) |
| 합성·구현 리포트 | Vivado 2026.1 BASIC 티어, Artix-7 (xc7a35tcpg236-1), 내부 블록은 `-mode out_of_context` |

```bash
iverilog -g2012 -o infer.vvp rtl/classifier.v rtl/imu_rule.v rtl/infer_top.v sim/tb_classifier.v && vvp -n infer.vvp
iverilog -g2012 -o imu.vvp rtl/imu_rule.v sim/tb_imu_rule.v && vvp -n imu.vvp
iverilog -g2012 -o infer_uart.vvp rtl/classifier.v rtl/imu_rule.v rtl/infer_top.v data/communication_module/uart_tx.v data/communication_module/uart_tx_ble.v sim/tb_infer_uart.v && vvp -n infer_uart.vvp
```

사용자 폴더 경로에 한글이 있는 Windows에서는 다음을 지켜야 도구가 돈다.

- OSS CAD Suite는 `bin`과 `lib`를 둘 다 PATH에 넣고, 임시 폴더를 ASCII 경로로 바꾼다: `export TMP=C:/tmp TEMP=C:/tmp PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"`.
- Vivado는 한글 경로에서 RTL 정교화 직후 힙 손상(0xC0000374)으로 죽는다. `rtl/`과 `sim/`을 ASCII 경로에 복사해 돌리고 리포트만 가져온다.
- Vivado 2026.1은 BASIC 티어도 라이선스 파일이 필요하다(amd.entitlenow.com에서 Node Locked 발급, Host ID는 MAC). 기본 위치가 한글 경로면 인식되지 않으므로 ASCII 경로에 두고 `XILINXD_LICENSE_FILE`로 지정한다.
- joblib 병렬 실행은 `JOBLIB_TEMP_FOLDER`도 ASCII 경로로 둔다.
