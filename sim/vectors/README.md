# 채점 파일

테스트벤치가 읽는 입력과 정답. 정답은 라벨이 아니라 파이썬 정수 기준 모델의 출력이고, 회로가 이것과 비트 단위로 같으면 통과다.

## `infer/` — 판정 블록 채점 파일

MPD-DF 50명의 RR로 5초 블록마다 60초 창 합(n60, sum_rr60, bad60)을 뽑고, 정수 판정 기준 모델(infer_ref)로 정답을 붙였다. 만드는 스크립트는 make_infer_vectors.py.

| 파일 | 내용 |
|---|---|
| `NN.txt` (01~50) | `block n60 sum_rr60 bad60 hold drowsy alert`. 사람마다 리셋부터 시작. 앞 넷이 입력, 뒤 셋이 정답(`alert`는 30초 간격 규칙을 적용한 심박 경보) |
| `edge.txt` | `case block n60 sum_rr60 bad60 hold drowsy alert`. 손으로 만든 경계 사례 5벌(판정 경계, 창 품질 경계, 나쁜 창을 건너뛰는 기준선, 최대값, 경보 간격). `case`가 바뀌면 리셋 |

tb_classifier.v가 51개 파일을 전부 읽어 블록마다 hold·drowsy·alert를 대조한다. tb_infer_uart.v는 50명 파일을 판정 블록과 통신 블록에 넣어 UART 바이트 수가 alert와 같은지 센다.

## `imu/` — 고개 떨굼 규칙 채점 파일

make_imu_vectors.py가 만든 합성 가속도(100 Hz, ±2 g 정수) 16 시나리오. 정답은 정수 규칙 기준 모델(imu_ref).

| 파일 | 내용 |
|---|---|
| `cases.txt` | `case k ax ay az nod lp_f lp_v cnt`. `case`가 바뀌면 리셋. `k`는 샘플 번호, `ax ay az`가 입력, `nod`는 그 샘플의 펄스, 뒤 셋은 필터·카운터 레지스터 정답 |

tb_imu_rule.v가 샘플마다 레지스터와 펄스 수를 대조한다. `+vec=파일`로 다른 벡터 파일(예: PPG-DaLiA 가슴 가속도)도 돌릴 수 있다.
