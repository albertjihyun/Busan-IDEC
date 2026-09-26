# 설계설명서 초안

대회 양식(참가신청서 + 설계설명서)의 설명서 부분 초안이다. 절마다 파일을 나눴고, 합칠 때는 아래 순서대로 이어 붙인다. 그림은 전부 `docs/figures/`에 있다.

## 목차와 파일

| 절 | 파일 | 작성 |
|---|---|---|
| 1. 작품명 | [1-title.md](1-title.md) | 공동 |
| 2.1 배경 | [2-1-background.md](2-1-background.md) | 공동 |
| 2.2 문제 정의 | [2-2-problem.md](2-2-problem.md) | 공동 |
| 2.3 설계 기준 | [2-3-criteria.md](2-3-criteria.md) | 공동 |
| 2.4 핵심 설계 결정 | [2-4-decisions.md](2-4-decisions.md) | 공동 |
| 2.5 범위 | [2-5-scope.md](2-5-scope.md) | 공동 |
| 2.6 차별점 | [2-6-differentiation.md](2-6-differentiation.md) | 공동 |
| 3.1 전체 구조 | [3-1-architecture.md](3-1-architecture.md) | 공동 |
| 3.2 아날로그 프론트엔드 | 담당이 작성 | 하드웨어 |
| 3.3 신호처리 블록 | 담당이 작성 | 하드웨어 |
| 3.4 판정 블록 | [3-4-inference.md](3-4-inference.md) | ML |
| 3.5 통신 블록 | 담당이 작성 | 통신 |
| 3.6 통합 검증과 결과 | [3-6-integration.md](3-6-integration.md) | 공동 |
| 3.7 기대 효과 | [3-7-impact.md](3-7-impact.md) | 공동 |
| 3.8 한계와 후속 과제 | [3-8-limitations.md](3-8-limitations.md) | 공동 |
| 참고문헌 | [references.md](references.md) | 공동 |

3.2, 3.3, 3.5는 각 담당이 쓴다. 다른 절이 이 세 절을 가리키는 번호(3.3.5 등)는 담당 원고가 들어오면 맞춘다.

## 그림

| 그림 | 파일 | 쓰는 절 |
|---|---|---|
| 전체 구조 | `sys_architecture.png` (원본 `.svg`) | 3.1 |
| 판정 블록 구조 | `infer_top.png` (원본 `.svg`) | 3.4.1 |
| 모델 크기 대 성능 | `model_size.png` | 3.4.2 |
| 이마 PPG 전이 | `ppg_transfer.png` | 3.4.2 |
| 기준선과 경보 간격 | `baseline_alert_timeline.png` | 3.4.3 |
| 숙임 판정 평면 | `tilt_plane.png` | 3.4.4 |

구조도 두 장은 SVG를 고친 뒤 브라우저로 PNG를 다시 뽑는다. 수치 그림 네 장은 `python scripts/make_submission_figures.py`로 다시 만든다.

## 표기

- 본문에서 `> 확인:`으로 시작하는 줄은 제출 전에 지울 작성 메모다. 사실 확인이나 팀 결정이 필요한 곳에 달았다.
- 참고문헌 번호는 [references.md](references.md)의 번호를 따른다. 합칠 때 처음 나오는 순서로 다시 매긴다.
- 문체는 "~다", 수치는 측정 조건과 함께 적는다.

## 팀 결정이 필요한 것

1. 전체를 관통하는 메시지(2.4 첫 문단). 초안은 "믿을 수 있는 신호로만, 필요한 만큼의 회로로 판단한다"로 썼다.
2. 전용 하드웨어의 근거(2.4 결정 3). FPGA 시제품 전력이 저전력 MCU 계산치보다 커서 전력을 근거로 쓰지 않고 연산량·결정적 지연·펌웨어 불필요·ASIC 이식성으로 바꿨다. 설계 기준 ④의 표현도 함께 정해야 한다.
3. 시스템 최상위(3.6)를 제출물에 넣을지. 핀 배정의 줄 방향은 실물 확인 전이다.
4. 작품명(1).
