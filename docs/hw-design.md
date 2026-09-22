# Verilog 구현 설계

담당: 유지현 | 대상: Cmod A7-35T (xc7a35t, 12 MHz) | 작성: 2026-09-10

이 문서는 ML 파트가 Verilog로 구현하는 구간의 설계 근거를 적는다. 어떤 블록을 만들고, 경계에서 무엇을 주고받고, 숫자를 몇 비트로 다루며, 어떻게 검증하는지를 정한다. 피크 검출 규칙과 분류기 파라미터처럼 파이썬 실험이 끝나야 정해지는 값은 "미정"으로 두고 해당 단계에서 채운다.

## 전체 경로에서의 위치

```
MCP3421 (12bit, 240 SPS, I2C)
  → [하드웨어 팀] I2C 마스터 → FIR 대역통과 → SQI → 피크 검출 → RR → 5초 블록 누산
  → 재료 5개 (N, ΣRR, ΣRR², Σd, Σd²)
  → [ML 파트]    특징 → 분류기 → IMU 결합 → 판정
  → [하드웨어 팀] UART TX → 통신 모듈
ICM-42670-P (I2C) → [하드웨어 팀] I2C 마스터 → [ML 파트] 고개 떨굼 규칙

2026-09-14 분담 변경: 피크 검출·RR·누산은 하드웨어 팀이 짠다. 피크 검출 규칙과 SQI 기준은 ML 파트가 정해서 넘긴다.
경계와 인계 일정은 [datapath-request.md](./datapath-request.md).
```

보드는 없다. 완성의 정의는 다음 세 가지다.

1. PPG-DaLiA의 실제 손목 PPG를 테스트벤치로 재생했을 때 RTL 출력이 파이썬 고정소수점 정답지와 비트 단위로 일치한다.
2. Vivado로 xc7a35t를 목표로 합성·구현하여 LUT, FF, DSP, BRAM 사용량과 타이밍 리포트를 뽑는다.
3. 같은 리포트에서 전력 추정치(`report_power`)와 판정 1회당 클럭 수를 뽑아, MCU 데이터시트 기반 계산과 판단 1회당 에너지·지연을 비교한다. 보드가 없으므로 실측은 후속이다.
4. 위 자원·전력 숫자와 ML 민감도·헛경보를 한 표에 놓는다.

## 경계 신호

[datapath-request.md](./datapath-request.md) 3절이 정본이다. 요지: 하드웨어 팀이 5초마다 `o_win_valid`와 함께 30초·60초 창의 재료 5개(N, ΣRR, ΣRR², Σd, Σd²)와 `o_sqi_bad`, IMU 3축을 준다. ML 블록은 `alert` 펄스 하나를 낸다(9/22, 같은 문서 ⑧ 절. 그전에는 `drowsy`·`hold`·`head_nod`·`changed` 넷).

## 숫자 표현

단위는 전부 **샘플 수**로 통일한다. 240 SPS이므로 1샘플 = 4.1667 ms. 밀리초로 바꾸는 나눗셈은 칩에서 하지 않고, 파이썬 쪽에서 임계값을 샘플 단위로 미리 변환한다. 특징 후보와 선정 근거는 [feature-rationale.md](./feature-rationale.md)에 있다. pNN50은 후보에서 뺐으므로 50 ms 문턱 비교기는 필요 없다. 240 SPS에서 SDNN·RMSSD 오차가 1% 미만이라는 근거도 같은 문서에 있다.

| 양 | 범위 근거 | 폭 |
|---|---|---|
| ADC 코드 (MCP3421, 240 SPS) | 240 SPS 모드는 12비트. ±2047, PGA 1이면 1 mV/코드. Vin−가 1 V 가상 접지라 0 중심 | 12 signed. `rr_frontend` 파라미터 `W_SAMPLE`(노치 출력이 넓으면 올림) |
| RR (샘플) | 0.3~1.5 s = 72~360 | 10 unsigned |
| 윈도우 박동 수 N | 60 s / 0.3 s = 최대 200 | 8 unsigned |
| ΣRR | 200 × 360 = 72,000 | 17 unsigned |
| ΣRR² | 200 × 360² = 25.9 M | 25 unsigned |
| 연속 차 d = RR[i] − RR[i−1] | ±288 | 10 signed |
| Σd | ±199 × 288 = ±57,312 | 17 signed |
| Σd² | 199 × 288² = 16.5 M | 24 unsigned |
| 기준선 N_base (첫 3분) | 180 s / 0.3 s = 594 | 10 unsigned |
| 기준선 ΣRR_base | 180 s × 240 + 360 = 43,560 | 16 unsigned |
| T_FIX (T × 1024, 헛경보 4회/h 이하 최소 정수) | 1086 | 11 unsigned |
| 판정 좌변 (ΣRR60 × N_base) << 10 | 17 + 10 + 10 | 37 unsigned |
| 판정 우변 (T_FIX × ΣRR_base) × N60 | 11 + 16 + 8 | 35 unsigned |

창은 60초로 확정됐다(9/19). 위 폭은 60초 기준.

## 제곱근과 나눗셈을 없애는 방법

분류기는 3단계 비교 결과로 정한다. 결정트리나 단일 임계값이 되면 "특징 > 임계값" 비교만 한다. 그러면 특징을 정의대로 계산할 필요 없이, 부등식을 정수 곱셈만 남도록 변형할 수 있다.

| 특징 | 정의 | 칩에서 비교하는 식 |
|---|---|---|
| mean RR > T | ΣRR / N > T | ΣRR > T · N |
| SDNN > T | √(ΣRR²/N − (ΣRR/N)²) > T | N · ΣRR² − (ΣRR)² > T² · N² |
| RMSSD > T | √(Σd² / (N−1)) > T | Σd² > T² · (N−1) |
| CVNN > T | SDNN / meanRR > T | N · ΣRR² − (ΣRR)² > T² · (ΣRR)² |
| SDSD > T | √(Σd²/(N−1) − (Σd/(N−1))²) > T | (N−1) · Σd² − (Σd)² > T² · (N−1)² |

SDNN 식의 좌변은 최대 200 × 25.9 M ≈ 5.2 G로 33비트, 우변은 T가 50샘플(208 ms)이라면 2500 × 40,000 = 100 M로 27비트다. 34비트 비교기 하나와 곱셈 세 번이면 된다. 판정은 30초에 한 번이므로 곱셈기를 하나만 두고 여러 클럭에 걸쳐 순차로 계산해도 된다. 임계값 T²은 파이썬이 미리 제곱해서 넘긴다.

로지스틱 회귀를 고르면 특징값 자체가 필요하므로 이 변형이 통하지 않는다. 그 경우 제곱근 회로나 근사가 추가된다. 3단계 모델 비교 표에 이 차이를 비용으로 기록한다.

## 윈도우를 버퍼 없이 만드는 방법 (하드웨어 팀 구현, 구조는 여기서 정함)

판정 갱신은 5초마다, 창 길이는 30초와 60초를 3단계에서 비교해 정한다. 어느 쪽이든 RR 값을 저장하지 않는다. **5초마다 누산기 다섯 개(N, ΣRR, ΣRR², Σd, Σd²)를 닫아 최근 12벌을 보관하고**, 30초 창은 최근 6벌, 60초 창은 12벌을 더한다. 갱신이 5초라 창 경계가 사건과 어긋나는 문제가 사라진다. 경계를 넘는 연속 차 하나는 직전 벌의 마지막 RR을 한 개만 기억해 처리한다. 이렇게 하면 BRAM이 필요 없고 레지스터 수십 개로 끝난다.

median NN은 정렬이 필요해 이 구조로 만들 수 없으므로 회로 후보에서 뺐다(9/14). 하드웨어 팀이 지금 설계 중이라 나중에 추가 요청하지 않기로 했다. 파이썬 비교에는 남겨 mean 대비 이점을 기록만 한다. 개인 기준선 대비 특징은 운전 시작 후 첫 N개 창의 누산값을 레지스터에 보관하면 되고, 직전 창 대비 변화는 직전 창 값 한 벌만 보관하면 된다.

5초는 240 SPS 기준 1,200샘플이라 11비트 카운터로 센다.

## 블록 목록

| 모듈 | 하는 일 | 담당 | 상태 |
|---|---|---|---|
| `sqi` | RR 72~360, 직전 대비 25% 이내, 첫 RR 탈락 | 하드웨어 | 참조 구현 `rtl/sqi.v` (9/15, 채점 통과) |
| `peak_detect` | 꺾임 + 문턱 3/5 + 불응기 96 + 급하강 확인 | 하드웨어 | 참조 구현 `rtl/peak_detect.v` (9/15, 채점 통과) |
| `rr_counter` | 봉우리 사이 샘플 수 | 하드웨어 | `rtl/sqi.v` 안에 포함 |
| `window_acc` | 5초 블록 누산기, 12벌 보관, 6벌·12벌 합산 | 하드웨어 | 참조 구현 `rtl/window_acc.v` (9/15, 채점 통과) |
| `classifier` | `mean_rb ≥ T` 를 교차 곱셈으로. 워밍업 3분 기준선, hold, 5초 판정 | ML | `rtl/classifier.v` (9/20, 50명 채점 통과). 설계 [integer-inference-design.md](./integer-inference-design.md) |
| `imu_rule` | 3축 가속도 임계값으로 고개 떨굼과 움직임 과다 | ML | 6단계. 문헌값 환산 |
| `combine` | 세 재료(판정·보류·떨굼)를 모아 `alert` 펄스 하나로. 떨굼 → 즉시, 보류 → 삼킴, 아니면 분류기 | ML | `infer_top` 안 한 줄 (9/22). IMU 항은 6단계 |
| `infer_top` | ML 블록 최상위. 재료 2개(`n60`, `sum_rr60`) 입력, `alert` 펄스·`ready` 출력 | ML | `rtl/infer_top.v` (9/20, 포트 정리 9/22). IMU 결합은 6단계 |

## 검증 흐름

1. 4단계에서 고정소수점 파이썬 정답지를 **정수 연산만으로** 짠다. numpy float를 쓰지 않는다. RTL과 한 줄씩 대응돼야 한다.
2. 정답지가 MPD-DF 파형(240 Hz 다운샘플)을 처리하면서 두 종류 벡터를 떨군다. ① 파형 → 봉우리 위치 → 재료 5개 (하드웨어 팀 검증용, 9/15, `sim/vectors/`) ② 재료 2개 → 판정 (ML 블록 검증용, 9/20, `sim/vectors/infer/`, 50명 전부 + 경계 사례).
3. Verilog 테스트벤치가 `$readmemh`로 입력을 읽어 240 SPS 간격으로 밀어 넣고, 출력을 기대값과 비교해 불일치를 세어 출력한다.
4. 중간값까지 대조하므로 틀리면 어느 블록에서 갈라졌는지 바로 보인다.

## 도구

| 용도 | 도구 | 상태 |
|---|---|---|
| 시뮬레이션 | Icarus Verilog + GTKWave | OSS CAD Suite 2026-09-09판, `C:\oss-cad-suite` (9/10 설치). `sim/tb_rr_frontend.v`로 실사용 확인 |
| 자원 추정 (초기) | Yosys `synth_xilinx -family xc7` | 위 묶음에 포함. 동작 확인 |
| 공식 합성·구현 리포트 | Vivado 2026.1 BASIC 티어 (무료) | `C:\AMDDesignTools\2026.1\Vivado`, Artix-7만 설치 (9/10 설치, xc7a35t 배치 합성 확인). **한글 경로에서 돌리면 죽는다**(9/20, 힙 손상 0xC0000374). `rtl/`·`sim/`을 `C:\tmp` 아래에 복사해 돌리고 리포트만 가져온다 |
| 기존 설치 | Quartus II 9.1sp2 | Altera 전용이라 Artix-7 합성 불가. 쓰지 않음 |

Vivado 라이선스. 2026.1부터 무료 BASIC 티어도 라이선스 파일이 있어야 실행된다. 발급은 License Manager의 Connect Now로 amd.entitlenow.com에 들어가 "Vivado Basic Tier License, Node Locked License"를 고르고 이 PC의 와이파이 MAC을 Host ID로 넣으면 이메일로 온다. 1년마다 같은 절차로 재발급한다.

- 기본 검색 위치 `C:\Users\<사용자>\.Xilinx`는 한글 경로라 인식되지 않았다. 파일을 `C:\Xilinx\Xilinx.lic`에 두고 사용자 환경변수 `XILINXD_LICENSE_FILE`로 그 경로를 지정해 해결했다.
- 배치 실행 예. 임시 폴더 설정은 OSS CAD Suite와 같은 이유로 필요하다.

```bash
export TMP=C:/tmp TEMP=C:/tmp
/c/AMDDesignTools/2026.1/Vivado/bin/vivado.bat -mode batch -nolog -nojournal -source run.tcl
```

```tcl
# run.tcl
read_verilog C:/path/rtl/drowsy_top.v
synth_design -top drowsy_top -part xc7a35tcpg236-1
opt_design
place_design
route_design
report_utilization -file util.rpt
report_timing_summary -file timing.rpt
```

`util.rpt`의 Slice LUTs, Slice Registers, DSPs, Block RAM Tile 줄이 서류에 넣을 자원 숫자다. 칩 전체는 LUT 20,800개, 레지스터 41,600개, DSP 90개, BRAM 50개다.

OSS CAD Suite 실행 조건. 이 PC는 사용자 폴더 이름에 한글이 있어서 기본 설정으로는 yosys가 실패한다.

- `bin`과 `lib`를 둘 다 PATH에 넣는다. `lib`가 없으면 yosys가 DLL을 못 찾는다.
- 임시 폴더를 한글 없는 경로로 바꾼다. 기본값 `AppData\Local\Temp`는 한글 경로라 abc9 단계가 파일을 못 연다.
- 프로젝트 파일도 한글 없는 경로에 두는 게 안전하다.

Git Bash에서 한 번에 설정하는 줄:

```bash
mkdir -p /c/tmp
export TMP=C:/tmp TEMP=C:/tmp PATH="/c/oss-cad-suite/bin:/c/oss-cad-suite/lib:$PATH"
```

확인용 명령과 기대 출력:

```bash
iverilog -o sim.vvp rtl/*.v sim/tb.v && vvp -n sim.vvp
yosys -p "read_verilog rtl/*.v; synth_xilinx -top drowsy_top -family xc7; stat"
```

두 번째 명령 끝에 LUT, FDRE, CARRY4, DSP48E1, RAMB 개수가 표로 나온다. Vivado 리포트가 나오기 전까지 이 숫자를 자원 추정치로 쓴다.

## 일정 (2026-09-19 밤 ML 파트 완료 기준)

9/14 팀 합의로 마감이 9/19로 당겨졌고 분담이 위와 같이 바뀌었다.

| 날짜 | 작업 | 준용에게 |
|---|---|---|
| 9/14 | 데이터패스 요청서. 1단계 착수(피험자 1명 RR, 봉우리 규칙 초안) | 요청서 |
| 9/15 | 1단계 완료. 50명 놓침 1.0%·오검출 3.2%(pooled), 240 Hz 오차 2.2 ms. 봉우리·SQI·누산 Verilog 참조 구현, 4명 채점 통과, 합성 LUT 852 | 피크·SQI 규칙, 채점 파일, 참조 RTL (완료) |
| 9/16 | 2단계: 특징 15개, 창 30/60, 라벨, 분포 | |
| 9/17 | 3단계: 모델 6종 LOSO, 특징 선택, 비교 표, 창 확정 | 특징 목록(참고) |
| 9/18 | 4단계: 정수 변환, 정답지. 추론 Verilog 착수 | 재료→판정 벡터 |
| 9/19 | 3단계 완료(PR #10). 로지스틱 특징 1개·창 60초 확정 | ⑥ 절(재료 둘, 인터페이스 선택지) |
| 9/20 | 4단계 정수 변환·정답지, 7단계 판정 Verilog·시뮬·합성 | 추론 모듈 + 테스트벤치 + 검증 파일 |
| 9/22 | 회로도 검토(요청서 ⑨). ADC 12비트에 맞춰 `rr_frontend` 입력 폭 12비트로(LUT 852→801), 채점 파일 12비트 형식 | ⑨절 질문 5개, 12비트 `in.hex` |

9/30 범위에서 뺀 것: PPG-DaLiA 5단계(여유 시), AdVitam 외부 검증, IMU 착용 검증, Vivado 전력 리포트는 준용 통합 후.
