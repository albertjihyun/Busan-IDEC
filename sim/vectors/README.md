# 채점 파일

출처: MPD-DF 02번 ECG, 60초부터 120초. 아날로그 프론트엔드 대역(0.16~16 Hz, 1차 RC 두 개) 흉내 → 1024 Hz → 240 Hz → mV × 400 → 정수 코드.
실제 칩에서는 ADC 출력(FPGA 노치 필터 뒤)이 `in`에 해당한다. AC 결합 덕에 0 중심이다.

| 파일 | 내용 |
|---|---|
| `in.txt` / `in.hex` | 입력 28800샘플. 16비트 부호 있는 정수. hex는 2의 보수, `$readmemh`용 |
| `peaks.txt` | 확정된 봉우리 147개. `peak_i`는 봉우리 위치, `confirm_i`는 급하강 확인이 끝나 확정된 샘플(최대 24 늦음) |
| `rr.txt` | 확정마다 RR(샘플 수)과 SQI 통과 여부. 첫 봉우리는 RR 없음 |
| `blocks.txt` | 5초 블록마다 그 블록의 누산값 5개. SQI 통과 RR만 |
| `windows.txt` | 5초 블록마다 최근 6벌 합(30초)과 12벌 합(60초) |

규칙과 상수는 `src/peak_simple.py`, `src/window_acc.py`. 회로가 이 파일들과 같은 값을 내면 통과.

검증 순서: `peaks.txt`의 `peak_i`가 맞는지 → `rr.txt` → `blocks.txt` → `windows.txt`. 앞에서 틀리면 뒤는 볼 필요 없다.
