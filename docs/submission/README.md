# 설계설명서 초안

대회 양식(참가신청서 + 설계설명서)의 설명서 부분 초안이다. 절마다 파일을 나눴고, 합칠 때는 아래 순서대로 이어 붙인다. 그림은 전부 `docs/figures/`에 있다.

## 목차와 파일

| 절 | 파일 | 작성 |
|---|---|---|
| 1. 작품명 | [1_title.md](1_title.md) | 공동 |
| 2.1 문제 인식 및 정의 | [2.1_background.md](2.1_background.md) | 공동 |
| 2.2 설계 목표 및 기준 | [2.2_goals_criteria.md](2.2_goals_criteria.md) | 공동 |
| 2.3 핵심 설계 방향 | [2.3_design_direction.md](2.3_design_direction.md) | 공동 |
| 2.4 구현 범위 및 기술적 차별성 | [2.4_scope_differentiation.md](2.4_scope_differentiation.md) | 공동 |
| 3.1 시스템 구성 | [3.1_architecture.md](3.1_architecture.md) | 공동 |
| 3.2 하드웨어 블록 | 담당이 작성 | 하드웨어 |
| 3.3 신호처리 블록 | 담당이 작성 | 하드웨어 |
| 3.4 판정 블록 | [3.4_inference.md](3.4_inference.md) | ML |
| 3.5 통신 블록 | 담당이 작성 | 통신 |
| 3.6 통합 검증 및 구현 결과 | [3.6_integration.md](3.6_integration.md) | 공동 |
| 3.7 결론 및 향후 과제 | [3.7_conclusion.md](3.7_conclusion.md) | 공동 |
| 참고문헌 | [references.md](references.md) | 공동 |

3.2, 3.3, 3.5는 각 담당이 쓴다. 다른 절이 이 세 절을 가리키는 번호(3.3.5 등)는 담당 원고가 들어오면 맞춘다.

## 그림

| 그림 | 파일 | 쓰는 절 |
|---|---|---|
| 전체 구조 | `3.1_sys_architecture.png` (원본 `src/3.1_sys_architecture.svg`) | 3.1 |
| 판정 블록 구조 | `3.4.1_infer_top.png` (원본 `src/3.4.1_infer_top.svg`) | 3.4.1 |
| 모델 크기 대 성능 | `3.4.2_model_size.png` | 3.4.2 |
| 이마 PPG 전이 | `3.4.2_ppg_transfer.png` | 3.4.2 |
| 기준선과 경보 간격 | `3.4.3_baseline_alert_timeline.png` | 3.4.3 |
| 숙임 판정 평면 | `3.4.4_tilt_plane.png` | 3.4.4 |

구조도 두 장은 `docs/figures/src/`의 SVG를 고친 뒤 브라우저로 PNG를 다시 뽑는다. 수치 그림 네 장은 `python scripts/make_submission_figures.py`로 다시 만든다.

## 표기

- 본문에서 `> 확인:`으로 시작하는 줄은 제출 전에 지울 작성 메모다. 사실 확인이나 팀 결정이 필요한 곳에 달았다.
- 참고문헌 번호는 [references.md](references.md)의 번호를 따른다. 합칠 때 처음 나오는 순서로 다시 매긴다.
- 문체는 "~다", 수치는 측정 조건과 함께 적는다.

## 팀 결정이 필요한 것

1. 전체를 관통하는 메시지(2.3 첫 문단). 초안은 "믿을 수 있는 신호로만, 필요한 만큼의 회로로 판단한다"로 썼다.
2. 전용 하드웨어의 근거(2.3 결정 3). FPGA 시제품 전력이 저전력 MCU 계산치보다 커서 전력을 근거로 쓰지 않고 연산량·결정적 지연·펌웨어 불필요·ASIC 이식성으로 바꿨다. 같은 이유로 2.2 설계 기준에서도 전력과 단가를 뺐다.
3. 시스템 최상위(3.6)를 제출물에 넣을지. 핀 배정의 줄 방향은 실물 확인 전이다.
