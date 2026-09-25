# PPG 기반 온디바이스 졸음 감지 SoC — ML 파트

2026 부산대 IDEC 반도체설계 경진대회 · 팀 쿵쿵딱 · 담당 유지현(ML)

이마 착용형 PPG 센서에서 얻은 심박 간격(RR)으로 각성도 저하를 판정하는 모델을 만들고, **고정소수점 Verilog 모듈로 구현**하는 저장소입니다. 학습은 PC에서 오프라인으로 하고 칩에는 추론만 올립니다.

카메라 기반 DMS는 선글라스·야간에 취약하고 조향 패턴 방식은 자율주행 중에 작동하지 않습니다. 행동으로 나타나기 전의 각성도 저하를 생리 신호로 보는 경로를 전용 하드웨어로 구현하는 것이 팀의 접근이고, 대회 성격상 승부처도 기능이 아니라 구현 방식입니다. 그래서 ML 파트는 정확도만이 아니라 **하드웨어 비용(파라미터 수·곱셈 횟수·메모리)을 모델 선정 기준에 포함**합니다.

## 저장소의 범위

전체 경로 중 `<<` 표시 구간이 ML 파트입니다. 아날로그 회로·PCB 설계와 신호처리 블록 RTL은 다른 팀원 담당이라 포함하지 않습니다.

```
PPG 센서(KT-0805G LED + TEMD6200 PD) → AFE(OPA2333) → ADC(MCP3421, 12bit / 240 SPS)
  → [FPGA: Cmod A7-35T]
       [하드웨어 팀] HPF → LPF → SQI → 피크 검출 → RR → 5초 블록 누산
       → 60초 창 합 (N, ΣRR, 탈락 박동 수)
       → 특징 mean_rb (창 평균 RR ÷ 기준선 평균 RR)          <<
       → 문턱 판정 mean_rb ≥ T (정수 교차 곱셈, 나눗셈 없음)   <<
       → IMU(ICM-42670-P) 고개 떨굼 규칙과 OR → alert 펄스     <<
  → [통신] UART → BLE
```

이 구간을 파이썬으로 먼저 구현·검증하고, 60초 창 합을 받아 기준선·판정·IMU 결합을 하는 추론 Verilog를 구현합니다. 학습용 RR을 뽑는 봉우리 검출기는 파이썬으로만 있고 칩에는 하드웨어 팀의 PPG용 검출기가 들어갑니다. 두 검출기를 잇는 것은 특징 `mean_rb`이고, 같은 사람의 ECG와 이마 PPG에서 이 값이 같게 나오는지를 WildPPG로 확인했습니다.

## 접근

PPG와 졸음 라벨이 함께 있는 공개 데이터는 없습니다. 그래서 **RR 간격이라는 공통 표현으로 ECG 데이터에서 학습하고, ECG와 PPG를 동시 기록한 데이터로 둘의 차이를 정량화**하는 구조를 택했습니다.

| 데이터 | 역할 | 라벨 |
|---|---|---|
| MPD-DF (50명) | 주 학습·평가 | 30초 단위 뇌파 판독 5단계 |
| WildPPG (16명) | 이마 PPG 전이 검증: 같은 사람의 ECG·이마 PPG에서 `mean_rb` 비교, 기준선·창 품질 규칙 근거 | 졸음 라벨 없음 |
| PPG-DaLiA (15명) | 움직임 게이팅 필요성 검증(SQI만으로 충분함을 확인), IMU 자세 규칙 헛울림 참고 | 졸음 라벨 없음 |

모델은 미리 정하지 않고 규칙 기반 단일 문턱부터 결정트리·로지스틱 회귀·랜덤포레스트·부스팅까지 피험자 단위 교차검증(LOSO)으로 비교했습니다. 특징 후보 14개 중 새 사람에게 통한 것은 `mean_rb` 하나였고, 특징이 하나라 로지스틱 회귀는 곧 문턱 규칙이 됩니다. 칩에 들어가는 파라미터는 문턱 T 하나(10비트 정수 `T_FIX` 1086, 헛경보 시간당 4회 동작점)입니다.

## 결과 요약

| 항목 | 값 |
|---|---|
| 사건 민감도 (헛경보 4회/h, LOSO: 처음 보는 사람 기준) | 0.413 [0.28–0.53], 깊은 사건(피로2+) 0.633 [0.48–0.80] |
| 칩 재현 (T_FIX 1086 하나, 창 품질·기준선 규칙 포함, 50명) | 사건 민감도 0.379, 깊은 사건 0.567, 헛경보 3.94/h |
| 경보 수 (심박 경보 30초 간격, 50명) | 깨어 있을 때 시간당 26회, 피로1 이상일 때 45회. 경보 중 실제 피로1 이상 34% |
| 판정 블록 시뮬레이션 | 50명 75,186블록 + 경계 278블록, 파이썬 정수 정답과 불일치 0. 통신 블록을 붙이면 경보 3,154개 = UART 바이트 3,154개 |
| `infer_top` 합성 (xc7a35t, Vivado 2026.1) | 단독 LUT 305, FF 107, DSP 3, BRAM 0, 12 MHz에서 WNS 72.3 ns. 칩 최상위에 통합하면 LUT 207 |

보드 없이 시뮬레이션과 합성 리포트로 완성을 정의합니다. PCB 제작과 이마 실측은 후속 과제입니다.

## 저장소 구조

```
docs/design-overview.md          제출용 설계 개요 (배경·타깃·설계 기준·검증). 팀 문서
docs/background-trucking.md      설계 개요의 타깃 근거 자료조사 (화물차·자율주행·규제)
docs/ml-plan.md                  ML 파트 구성, 문제 정의와 평가 지표
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
rtl/classifier.v                 기준선·창 품질·mean_rb 판정 (정수, 나눗셈 없음)
rtl/imu_rule.v                   IMU 고개 떨굼 자세 규칙
rtl/infer_top.v                  판정 블록 최상위: 판정 + IMU 결합 → alert 펄스
sim/tb_classifier.v, tb_imu_rule.v   파이썬 정답과 비트 대조하는 테스트벤치
sim/tb_infer_uart.v              판정 → 통신 블록(data/communication_module) 연결 채점
sim/vectors/                     테스트 벡터 (판정 infer/, IMU imu/)
sim/vivado_infer_top.tcl, reports/   Vivado 합성 스크립트와 자원·타이밍·전력 리포트
src/infer_ref.py, imu_ref.py     판정·IMU 규칙의 파이썬 정수 기준 모델
src/features.py, src/stage3/     특징 계산, 모델 비교 실행기·채점기
src/mpd_io.py, peak_simple.py, window_acc.py, peak_eval.py   MPD-DF 읽기, 학습 검출기, 5초 블록 누산, 검출 평가
scripts/                         데이터 내려받기, RR 추출, 특징 표, 벡터 생성, 검증 스크립트
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
