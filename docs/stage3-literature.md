# 모델 비교 문헌 조사

모델 비교·특징 선택·창 길이 설계의 근거로 두 가지를 조사했다. (1) HRV 졸음 검출 문헌이 쓴 분류기와 피험자 독립 성적, 칩에 올릴 수 있는 분류기. (2) 사건 단위 민감도 + 시간당 헛경보 평가법의 출처. 웹 검색과 공개 원문 기준이며, 확인 못 한 것은 [미확인]으로 표시했다.

## A. 분류기

### A1. HRV 졸음 검출 논문의 분류기와 피험자 독립 성적

피험자 독립(LOSO)으로 평가한 논문은 Vicente 2016, Kundinger 2020a, Persson 2021 셋뿐이고 셋 다 성적이 크게 떨어진다(Lu 2022 리뷰 명시). 특징 표에서 본 "사람 안 효과가 작다"는 관찰은 문헌과 일치한다.

| 논문 | 분류기 | 창 | 평가 | 성적 | 개인 기준선 |
|---|---|---|---|---|---|
| Vicente 2016 | LDA 7특징 [2011 CinC 선행 초록으로 확인, 2016 본문 미확인] | 1분(수면부족 판정은 첫 3분) | LOSO | 졸음 에피소드 PPV 0.96, Sen 0.59, Spe 0.98 (3475분) | 첫 3분 |
| Persson 2021 | 여러 후보 중 Random Forest 최고 [후보 목록 미확인] | 5분 | 10-fold와 LOSO | 10-fold 이진 85% → 3클래스 64% → LOSO 3클래스 44% (Sen 33, Spe 66). 실도로 86명 | KSS<5 구간 |
| Kundinger 2020a | RF, Random Tree, Decision Stump, Decision Table, kNN, BN, NB, SVM, MLP (Weka), HRV 26특징 | 5분, 2초 슬라이딩 | 10-fold(UDT)와 LOSO(UIT), 27명 | UDT: kNN 92%(손목) RF 97%(ECG). LOSO: Decision Stump 손목 73.4%(F2 0.65), ECG 78.9%(**F2 0.17**); RF 손목 62%(F2 0.20), ECG 71%(F2 0.13). 라벨은 관찰자 비디오 등급 4~6 = 졸음, 비졸음 79.7%라 **ECG 78.9%는 전부 비졸음이라 찍은 수준**. 저자도 "drowsy 클래스 분류가 UIT에서 특히 나빴다(낮은 F2)"고 인정. 30명 × 45분(약 22.5시간), 6단계 관찰자 등급(κ 0.69) + 1초 이상 눈 감김 | 없음 |
| Fujiwara 2019 | 지도학습 아님. MSPC(PCA T²/Q 이상 검출), 8 HRV 특징, 운전자별 모델 | 3분 이동창 | 운전자별(피험자 독립 개념 없음) | 34명. pre-N1 에피소드 12/13 검출, 헛경보 1.7회/시간(Q), T²는 2.6회/시간 | 개인 각성 구간 |
| Li & Chung 2013 | SVM(linear, RBF) 웨이블릿 특징 | 1분 | 4명 80표본 pooled leave-one-sample-out → 피험자 독립 아님 | 95%. LF/HF 단일 문턱 68.8% | 없음 |

Lu 2022: "같은 피험자·같은 세션 데이터는 학습/시험에서 분리해야 한다. LOSO는 셋뿐, 나머지는 10-fold/holdout이라 성적이 부풀려졌을 수 있다."

시사점: Kundinger LOSO에서 깊이 1 트리가 정확도로는 RF·SVM·MLP를 이겼지만, 정확도가 다수 클래스 비율(79.7%)과 같아 F2로 보면 손목 stump(0.65)만 의미가 있다. 정확도 단독 보고의 함정을 보여 주는 사례이자, 효과가 작고 사람 간 편차가 크면 단순 모델이 일반화에 유리하다는 사례다.

- Vicente J, Laguna P, Bartra A, Bailón R. 2016. Med Biol Eng Comput 54:927–937. https://link.springer.com/article/10.1007/s11517-015-1448-7
- Persson A et al. 2021. IEEE T-ITS 22(6):3316–3325. https://ieeexplore.ieee.org/document/9055218/
- Kundinger T, Sofra N, Riener A. 2020. Sensors 20(4):1029. https://pmc.ncbi.nlm.nih.gov/articles/PMC7070962/
- Fujiwara K et al. 2019. IEEE TBME 66(6):1769–1778. https://ieeexplore.ieee.org/document/8520803/
- Li G, Chung WY. 2013. Sensors 13(12):16494–16511. https://pmc.ncbi.nlm.nih.gov/articles/PMC3892817/
- Lu K et al. 2022. Accid Anal Prev 178:106830. https://doi.org/10.1016/j.aap.2022.106830

### A2. 작은 표 데이터에서 어떤 분류기가 이기나

- Fernández-Delgado 2014 (JMLR 15:3133): 121 데이터셋 × 179 분류기. RF 최고, RBF SVM 2위, 둘 차이는 유의하지 않음. LR·kNN·NB는 상위권 아님. https://jmlr.org/papers/v15/delgado14a.html
- Grinsztajn 2022 (NeurIPS D&B): 45개 표 데이터셋, 1만 표본 규모에서 트리 앙상블이 MLP·트랜스포머를 이김. 이유: 정보 없는 특징에 강함, 축 정렬, 비매끈 함수. 우리 규모(12k행, 14특징)가 이 regime. https://arxiv.org/abs/2207.08815
- Benchekroun 2023 (Sensors 23:1807): HRV 스트레스, 5분 창, LOSO. LR vs RF는 데이터셋에 따라 엎치락뒤치락(F1 0.71 vs 0.63, 0.61 vs 0.75). 특징 10개 안팎 소규모에서 둘의 차이는 작다. https://www.mdpi.com/1424-8220/23/4/1807
- Saeb 2017 (GigaScience 6:gix019): 한 사람에게서 여러 표본이 나오면 subject-wise CV 필수. https://academic.oup.com/gigascience/article/6/5/gix019/3071704

### A3. 칩(정수 연산)에 올릴 수 있는 분류기

- Shoaran 2018 (IEEE JETCAS 8(4):693, 발작 검출 ASIC): SVM 비용은 서포트벡터 수 × 특징 수, RBF는 지수(CORDIC)까지 필요해 이식형에 부적합. kNN은 학습 데이터 전체 저장. LR/1층 NN은 곱셈-누산 + 시그모이드. 결정 트리/부스팅 트리는 비교기만 쓰고 곱셈 불필요. 자체 칩: 8트리 × 깊이 4 XGBoost, 65 nm, 41.2 nJ/분류, 트리 메모리 690 B, Sen 83.7/Spe 88.1. https://www.mics.caltech.edu/wp-content/uploads/2018/11/Mahsa_JETCAS_2018.pdf (선행: Shoaran 2016 EMBC, 얕은 트리 부스팅)
- Zhang 2018 (Front Syst Neurosci 12:43, MSP430에 RF): RF가 RBF-SVM보다 우세(AUC 0.90 vs 0.88). 트리는 정규화 불필요. 100트리는 256 kB 안에 안 들어가 외부 플래시 사용 → 트리 수·깊이 제한 필요. https://www.frontiersin.org/journals/systems-neuroscience/articles/10.3389/fnsys.2018.00043/full
- Jacob 2018 (CVPR, 8비트 양자화 표준): 가중치·활성 8비트, 누산 32비트.
- emlearn (https://github.com/emlearn/emlearn): sklearn RF/DT/작은 MLP → 정수 C 코드. Verilog 정답지 생성에 참고 가능.
- RBF SVM 결론: 4 KB·1만 곱셈 예산에서 비현실적. 선형 SVM은 LR과 비용 동일.
- 웨어러블 HRV 특정 FPGA 트리 구현 논문 [못 찾음].

### A4. 클래스 불균형: class_weight vs 임계값

- Provost 2000 (AAAI Workshop): "표준 알고리즘의 분류기를 출력 문턱 조정 없이 쓰는 것은 치명적 실수일 수 있다." 재표집으로 해결한 연구 대부분이 문턱만 잡아도 충분한지 묻지 않았다. https://pages.stern.nyu.edu/~fprovost/Papers/skew.PDF
- Elkan 2001 (IJCAI): 확률을 내는 분류기에서는 가중치 = 재표집 = 문턱 이동이 동치(Theorem 1). 결정 트리는 클래스 비율이 구조를 바꾸므로 완전 동치 아님. https://cseweb.ucsd.edu/~elkan/rescale.pdf
- scikit-learn classification_threshold 문서: 기본 0.5는 대부분 최적이 아님. 학습과 문턱 조정에 같은 데이터를 쓰면 안 됨. https://scikit-learn.org/stable/modules/classification_threshold.html

### A5. 최근 논문 (2023~2026) 확인

- AlArnaout et al. 2025, Sci Rep, "Exploiting heart rate variability for driver drowsiness detection using wearable sensors and machine learning" (PMC12246425). **AdVitam 데이터가 아니다.** 10명 레이싱 시뮬레이터의 스트레스 데이터(30초 PPG 6,300구간)를 재활용했고, 졸음 라벨은 KSS·뇌파가 아니라 **심박수 문턱(72.3~90.7 bpm)으로 저자들이 만든 것**이라 HRV로 HR 기반 라벨을 맞히는 순환 구조. 분할은 80/20 무작위 + 4-fold(창 단위, 사람 분리 없음). RF 정확도 86.05%, F1 89.02%. 개인 기준선 없음. 저자들도 "subject-wise validation 없음"을 한계로 적음. 우리 비교 대상이 못 된다.

2023~2026 논문은 검색 요약과 일부 원문으로 확인했다. 원문을 열지 못하고 초록·검색 요약만 본 것은 [초록만]으로 표시했다.

| 논문 | 센서 | 데이터 | 라벨 | 모델 | 사람 분리 | 성능 | 개인 기준선 |
|---|---|---|---|---|---|---|---|
| Vaussenat 2026, Sensors 26(4):1348 (PMC12944032) | 시트 용량성 ECG | 25명 49세션 75시간 | 충돌 60초 전 + PERCLOS·하품 | ViT 3.28M | LOSO 25명 | **HRV 도함수만 AUC 0.573, HRV 전체 AUC 0.863**, 전체 모델 AUC 1.000(라벨 순환 의심) | 참가자별 z-score |
| "Subject-independent multimodal drowsiness detection" 2026, BSPC (S174680942601061X) [초록만] | ECG(Polar H10) + 눈 | 시뮬 12명 | KSS + 관찰자 | SVM·ET·GB | LOSO(+10-fold 비교) | 생리신호만: 관찰자 라벨 F1 0.824, KSS F1 0.252. **10-fold가 LOSO보다 F1 최대 +0.566** | 미확인 |
| Meteier 2024, TRIP 26 [초록만] | ECG+EDA+호흡 | AdVitam 63명 | 수면박탈 + KSS | ML | 미확인 | 수면박탈 99%, 졸림 73%(정확도), EDA가 최고 | 미확인 |
| DrowsyDG-Phys 2026, AAP 228 [초록만] | ECG+EDA+호흡 | 공개 3종 + 자체 60명 | 미확인 | 도메인 일반화 | 교차 데이터셋·교차 피험자 | 정확도 78.5 / 88.4만 | 미확인 |
| UL-DD 2026, Sci Data (PMC13039290) | E4 HR + 맥박 + 영상 | 19명 1,400분 | KSS 4분마다 | SVM·RF·Transformer | **없음**(5-fold) | 다중모달 88%. 심박 단독 수치 없음 | 없음 |
| Wang 2025, arXiv 2506.06360 | ECG·EDA·호흡 | 데이터셋 4종 | 혼재 | 연관 분석 | — | 결론: 유발 방식이 다르면 생리 반응도 다름, 객관 라벨이 주관보다 나음 | — |

리뷰: El Sahmarany 2026 Sensors 26:3333 — HRV+SVM 58~59% 사례 인용, "PPG는 단독으로는 변화가 미미해 보조 지표". Penzel & Salanitro 2024 Sleep — HRV 감시가 EEG·PERCLOS보다 낫다는 근거 없음.

요점: (1) 2023~2026에도 **사람 분리 + HRV 단독**으로 높은 특이도에서 민감도 0.6을 넘는 결과는 못 찾음(Vaussenat HRV 도함수 AUC 0.573, KSS 라벨 F1 0.252). (2) 같은 데이터·모델에서 10-fold가 LOSO보다 F1을 최대 0.57 부풀림 → LOSO 선택의 직접 근거. (3) 라벨 종류가 모델보다 중요(관찰자 라벨 F1 0.82 vs 자가보고 0.25). MPD-DF의 전문의 뇌파 라벨은 관찰자 계열. (4) LOSO에서 쓸 만한 수치를 낸 논문은 개인별 z-score를 씀 → 우리 기준선 비율과 같은 계열. (5) **2023~2026 논문 중 시간당 헛경보를 보고한 HRV 졸음 논문은 없음.** 앞선 선례는 운전자별 모델인 Fujiwara 2019(1.7회/h)뿐이라 사람 분리 평가에서 직접 비교할 상대는 없다. (6) MPD-DF를 쓴 후속 ML 논문은 아직 없음.

**Li & Chung 2013 (PMC3892817)의 95%**: 피험자 4명, 1분 표본 80개(각성 40·졸음 40)를 표본 단위 leave-one-out. 같은 사람의 다른 구간이 학습에 들어감 → **피험자 독립 아님.** 비교 근거로 쓰지 않는다.

## B. 평가 지표

### B1. 출처: 뇌전증 발작 검출 채점법

- NEDC/Temple (Ziyabari, Shah, Picone 2017/2021, arXiv:1712.10107): Epoch(샘플) 채점과 Term(사건) 채점을 구분. Any-Overlap(OVLP): 가설이 정답 사건과 겹치면 TP 1, 안 겹치면 FP, 길이 무시. 한 사건 안 여러 경보는 헛경보로 안 셈. 헛경보는 24시간당 횟수. 임상가 피드백: "낮은 헛경보율이 사용자 수용의 가장 중요한 기준", "민감도 75% 이상이면 FA rate가 가장 중요". OVLP는 관대해서(90%를 놓쳐도 TP) TAES(겹친 비율 점수)를 제안. https://arxiv.org/abs/1712.10107
- SzCORE (Dan 2024, Epilepsia 65(11)): 커뮤니티 표준. 사건 채점: any overlap, 시작 전 허용 30 s, 끝난 뒤 60 s, 90 s 미만 간격 경보는 병합, 5분 넘는 사건은 분할. 지표: Sensitivity, Precision, F1, False alarms per day. "TN에 의존하는 specificity·accuracy는 명시적으로 피한다." 피험자 독립은 LOSO 또는 피험자 분리 K-fold. https://arxiv.org/abs/2402.13005
- Beniczky & Ryvlin 2018 (Epilepsia 59(S1):9, ILAE/IFCN 표준): phase 0~4 등급과 보고 항목. 본문 유료라 세부 [미확인]. https://onlinelibrary.wiley.com/doi/10.1111/epi.14049

### B2. 졸음 분야의 사건 단위 선례

- Fujiwara 2019: "pre-N1 에피소드 13건 중 12건 검출, 헛경보 1.7회/시간(각성 40.1 h에 FP 70건)". 검출 성공 = sleep onset 15분 전부터 직전까지 경보. 우리 설계와 가장 가까운 선례.
- Vicente 2016: 분 단위 이진(PPV 0.96, Se 0.59, Sp 0.98). 사건 단위·시간당 헛경보 없음.
- Malafeev 2021 (마이크로슬립, Frontiers Neurosci): Cohen's κ만. 피험자 단위 70/15/15 분할.
- MPD-DF 논문(Sci Data 2026): MSCNN-CAM 이진, ECG 10 s accuracy 0.824 / precision 0.556 / recall 0.595 / F1 0.563, "ECG-based model producing the weakest results"(Table 9). 분할 방식(피험자 독립 여부) 미기재, 권장 프로토콜 없음. "ECG 모델이 가장 약했다"는 말의 출처가 이 표다.
- 졸음 분야의 고정 FA/h 관례 [not found].

### B3. 폴드별 평균 vs pooled

- Forman & Scholz 2010 (SIGKDD Explorations 12(1):49): F-measure는 TP/FP/FN을 전 폴드 합산 후 한 번 계산(pooled)이 거의 유일하게 불편(unbiased). 폴드에 양성이 없으면 recall 미정의 → 0 대입은 음의 편향, 건너뛰면 양의 편향. AUC는 반대로 폴드별 평균 권장(폴드 섞으면 폴드 간 보정 요구). https://www.kdd.org/exploration_files/v12-1-p49-forman-sigkdd.pdf
- 우리 42·49번(사건 0), 22번(각성 0)이 정확히 이 경우. pooled 사건 민감도·헛경보가 근거 있는 선택. AUC를 낸다면 사건 없는 피험자 빼고 폴드별 평균.

### B4. 동작점: FROC

- FROC(free-response ROC, Bunch 1978; Chakraborty 2013 Acad Radiol 20:915): x축이 확률이 아니라 "단위당 헛경보 수"인 ROC. 우리 "사건 민감도 vs 시간당 헛경보" 곡선이 시간축 FROC다. https://pmc.ncbi.nlm.nih.gov/articles/PMC2230665/
- 발작 검출 관례: 전체 곡선 + 고정 동작점의 (민감도, FA/24h) 쌍을 함께 보고. 민감도 하한을 먼저 두고 그 안에서 헛경보 최소 동작점을 고르는 순서.

### B5. 신뢰구간: 피험자 단위 부트스트랩

- Field & Welsh 2007 (JRSS-B 69:369): cluster bootstrap. 사건이 아니라 피험자를 복원추출하고 그 피험자의 사건을 통째로 가져간다. 같은 사람의 사건은 독립이 아니라서 사건 단위 부트스트랩은 구간이 너무 좁다.
- Anglin 2026 (arXiv:2606.26422): 군집당 표본이 적으면 단순 cluster bootstrap이 무난. 50명 = 50 군집이라 구간이 넓게 나오는 것이 정직한 결과.

### B6. 교차검증·겹친 교차검증이 인정되는 근거

- Kohavi 1995 (IJCAI): k-fold 교차검증이 정확도 추정의 표준임을 실험으로 보임. 매 회차 모델은 자기 시험 조각을 보지 않으며, 회전 점수는 "같은 절차로 만든 모델의 새 데이터 성적" 추정치다. https://ai.stanford.edu/~ronnyk/accEst.pdf
- Varma & Simon 2006 (BMC Bioinformatics 7:91): 교차검증 점수로 손잡이를 고르면(안쪽 고리 없음) 추정이 낙관적으로 편향되고, 겹친 교차검증(nested CV)은 거의 불편. https://doi.org/10.1186/1471-2105-7-91
- Cawley & Talbot 2010 (JMLR 11:2079): 모델 선택 자체가 과적합의 원천. 선택에 쓴 점수를 성적으로 보고하면 부풀려짐. https://jmlr.org/papers/v11/cawley10a.html
- 규칙: 시험 사람은 "학습"만이 아니라 손잡이·특징·문턱·스케일링 상수 선택 전체에서 제외. 바깥 결과를 보고 절차를 고치면 바깥 점수도 선택에 쓰인 것이므로, 절차를 먼저 고정하고 바깥 고리는 한 번만 돌린다. 데이터셋 자체에 대한 의존은 교차검증으로 못 재며 졸음 라벨이 있는 외부 데이터셋만이 답이다. 이 검증은 하지 못했다.

## C. 동작점(헛경보 예산) 근거

### C1. 법·평가 기준

- **EU DDAW 규정** Commission Delegated Regulation (EU) 2021/1341(GSR 2019/2144 보충), 부속서 I. https://eur-lex.europa.eu/eli/reg_del/2021/1341/oj/eng
  - Part 1, 3.3.1: 경보는 **KSS 8 이상**에서 의무. KSS 7에서의 경보와 그 전 단계 정보성 표시는 허용.
  - Part 2, 8 합격 기준: **평균 민감도 40% 초과**(피험자별 민감도의 평균), **90% 신뢰구간 하한 20% 초과**. 시험 간격 15분 초과·시뮬레이터·공도 시험이면 ±5% 보정.
  - Part 1, 2.2: "system error rate를 피하거나 최소화하도록 설계" — **헛경보 수치 한도 없음.**
- **EU ADDW 규정** 2023/2590 Part 1, 2.2: "minimise the system error rate (false positive)" — 역시 수치 없음. https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A32023R2590
- **Euro NCAP**: Fredriksson et al. 2021, Front Neuroergonomics — "current GSR standards ... place sensitivity around 40%; this mark is achievable by several algorithms but bears room for improvement at **false-positive rates of 11–24%**". 이 11~24%는 현행 알고리즘의 관측값이지 규정 한도가 아니다. https://pmc.ncbi.nlm.nih.gov/articles/PMC10790826/ Euro NCAP 프로토콜 자체의 헛경보 감점 규칙은 [미확인].

### C2. 경보 피로("양치기 소년")

- Wickens & Dixon 2007, Theor Issues Ergon Sci 8(3): 20개 연구 메타분석. **신뢰도 0.70이 교차점** — 그 아래면 불완전한 자동화가 자동화 없느니만 못하다. https://www.tandfonline.com/doi/abs/10.1080/14639220500370105
- Manzey 그룹(Sci Direct S0003687020300570): 헛경보율 20% + **PPV 0.3**에서 작업자가 진짜 경보의 약 절반을 무시. **PPV 0.5 미만이면** 반응 지침이 따로 필요하다는 권고.
- Lees & Lee 2007, Ergonomics 50(8): 무작위 오경보는 신뢰를 떨어뜨리지만, "알고리즘은 위험으로 봤으나 운전자는 아닌" 납득 가능한 경보는 오히려 이후 신뢰·순응을 높였다. 헛경보의 **설명 가능성**이 숫자만큼 중요. https://www.tandfonline.com/doi/full/10.1080/00140130701318749
- Bliss & Acton 2003, Appl Ergon: 시뮬레이터 70명, 경보 신뢰도 50/75/100%. 신뢰도가 높을수록 반응·회피가 유의하게 나았다(조건별 수치는 [미확인]).
- Ayas, Donmez & Tang 2024, Human Factors 스코핑 리뷰: 한 현장 연구에서 운전자들이 경보를 무시하고 휴식을 미뤘다. "헛경보는 졸음 완화 시스템 사용에 치명적일 수 있다". https://pmc.ncbi.nlm.nih.gov/articles/PMC11344370/
- 졸음 경보 한정 "몇 회부터 끄는가" 수치는 [못 찾음].

### C3. 기저율과 다른 분야 앵커

- Fitzharris et al. 2017, Traffic Inj Prev: Seeing Machines Guardian 실차 상용 운송. 기저 **1000 주행시간당 43.65건**(시간당 0.044건 ≈ 23시간에 1건), 경보+관리자 피드백 후 2.97건/1000h. https://www.tandfonline.com/doi/full/10.1080/15389588.2017.1306855
- 발작 검출 웨어러블 메타분석 2026, Front Bioeng: 전신발작 민감도 89.9%, 헛경보 **24시간당 1.43회**. 부분발작 73.5% / 2.85회. https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2026.1833080/full
- ICU 경보 피로: Drew et al. 2014, PLoS ONE. 병상당 **하루 187건** 가청 경보, 부정맥 경보의 88.8%가 헛경보. 절대 가면 안 되는 쪽의 기준점. https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0110274
- 상용 시스템(Volvo DAC, Mercedes ATTENTION ASSIST, Bosch, SmartCap)의 헛경보율은 **공개 수치 없음**. 발표 자료에 숫자로 쓰면 안 된다.

### C4. 우리 데이터로 역산한 PPV (로지스틱 30초)

우리 기저율은 사건 443건 / 유효 주행 99.2시간 = **시간당 4.47건**으로, Fitzharris의 실차 기저율(0.044건)보다 100배 높다. 시뮬레이터 2시간 단조 주행이고 "피로1 이상"이 매우 가벼운 기준이라서다. 따라서 문헌의 절대 헛경보 예산을 그대로 옮길 수 없고, PPV는 우리 데이터로 다시 계산해야 한다.

| 헛경보/h | 사건 민감도 | 경보 PPV |
|---|---|---|
| 0.59 | 0.17 | 0.67 |
| 1.11 | 0.20 | 0.58 |
| 1.93 | 0.26 | 0.51 |
| 3.91 | 0.40 | 0.44 |
| 6.05 | 0.50 | 0.39 |
| 7.99 | 0.60 | 0.36 |

PPV ≥ 0.5(Manzey 권고선)를 지키는 최대 헛경보는 **2.1회/h, 민감도 0.27**. PPV ≥ 0.7(Wickens & Dixon 교차점)은 0.37회/h, 민감도 0.13. 이 PPV는 MPD-DF의 높은 기저율 덕이라 실차에서는 더 낮아진다는 점을 명시해야 한다.

### C5. KSS 8과 우리 라벨의 대응

**우리 라벨의 원 정의** (MPD-DF 논문, Sci Data 2026). 수면센터 의사 **1명**이 30초 에폭 단위로 뇌파를 보고 주석. 판독자 간 일치도 보고 없음.

| 라벨 | 뇌파 기준 (원문) | 논문이 붙인 이름 |
|---|---|---|
| 0 각성 | "dominant β rhythms and frequent rapid eye movements" | wakefulness |
| 1 피로1 | "the emergence of α waves alongside β waves ... indicating the onset of fatigue" | onset of fatigue |
| 2 피로2 | "significant or diffuse α rhythms with mixed low-frequency waves ... signifying the drowsy state" | **drowsy state** |
| 3 N1 | 확산 α 감소, 저진폭 혼합주파수, 느린 안구운동·vertex파 | 수면 1단계 |
| 4 N2 | K복합체, 수면방추 | 수면 2단계 |

**KSS는 주행 중 측정되지 않았다.** 사전 설문 3종(HSQ, MEQ, PSQI)뿐. 따라서 규정이 요구하는 "경험적 등가 증거"는 이 데이터로 만들 수 없다.

**주행 조건**: 오후 13:00~16:30, 2시간 단조 고속도로 시뮬레이터, 시속 35 km 1단 고정, 전날 7시간 이상 수면 요구, 의도적 수면 박탈 없음. 즉 밤샘 졸음이 아니라 **단조로움에서 오는 피로**다. 우리 성적이 낮은 이유의 후보이자, 실차 야간 졸음으로의 외삽 한계.

**KSS와 뇌파의 관계**

- Åkerstedt & Gillberg 1990, Int J Neurosci 52:29: KSS는 **각성 중 알파·세타 침입과 느린 안구운동(SEM)**에 대해 검증됐다. 눈 감은 조건에서는 구분력이 떨어진다. KSS 점수별 대응표는 없다. https://pubmed.ncbi.nlm.nih.gov/2265922/
- **Kaida et al. 2006, Clin Neurophysiol 117:1574** (가장 직접적): KSS를 1–3 / 4–5 / 6 / 7 / 8–9 다섯 구간으로 묶어 비교. **눈 뜬 상태 알파 파워는 8–9 구간에서만 각성 구간과 유의하게 갈린다.** 눈 감은 알파는 7부터, 세타는 어느 구간도 유의차 없음. 행동 지표(lapse, 반응시간)는 6부터. **대비분석에서 선형 성분만 유의 → 문턱·급변점은 관측되지 않았다.** https://pubmed.ncbi.nlm.nih.gov/16679057/
- KDS(Karolinska Drowsiness Score): 20초를 2초씩 10조각으로 나눠 알파·세타·SEM이 보이는 조각의 비율. Sandberg 2011 실도로 야간 주행에서 KSS 8~9까지 갔는데도 **KDS 평균은 11.5%**. 즉 "알파가 조금 보이는 것"은 KSS 8보다 한참 아래다. https://pmc.ncbi.nlm.nih.gov/articles/PMC3174834/
- Sandberg 2011: KSS ≤6에서는 차선 이탈이 거의 없고 **KSS ≥8에서 뚜렷이 증가**. 규정의 KSS 8 근거는 뇌파 단계가 아니라 **수행 저하**다.
- 마이크로수면은 주행 후 KSS 8 부근에서 갈린다. **KSS 8 = N1이라 쓴 문헌은 없다.**

**규정 확인**: 2021/1341 Part 2 §5.2.1은 EEG·PERCLOS를 대체 방법의 **예시로만** 언급하고, §5.2.2는 "그 문턱이 KSS와 등가임을 제조사가 증거로 제시하라"고만 한다. **부속서 어디에도 KSS 8의 뇌파 정의가 없다.** IDIADA 기술보고서도 등가성은 자체 지표와 KSS의 경험적 상관 제출로 증명한다고 적었다. https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021R1341

**판독 신뢰도**: AASM 판독자 간 일치(Rosenberg & Van Hout 2013, JCSM) N1 63.0%로 전 단계 중 최저. 메타분석(Lee 2022, JCSM) N1 κ=0.24로 "fair". 각성-피로 단계의 판독자 간 일치를 보고한 논문은 [못 찾음]. 단일 판독자인 우리 라벨의 재현성을 이보다 좋다고 주장할 근거가 없다.

**결론과 허용 가능한 문장**

피로2가 KSS 8의 가장 방어 가능한 대응이다. 근거는 (1) KSS가 각성 중 알파 침입으로 검증됐고, (2) 눈 뜬 알파가 KSS 8–9에서 비로소 유의해지며(Kaida 2006), (3) 알파가 조금 보이는 정도(피로1)는 야간 주행 KDS 11.5%가 시사하듯 KSS 8보다 아래이고, (4) N1은 마이크로수면·사고 시점이라 너무 늦고 판독 신뢰도도 최악이다.

다만 **등가 증명이 아니라 정성적 정합성 논증**이다. 쓸 수 없는 문장: "규정이 정한 뇌파 기준을 충족한다"(그런 기준이 없다), "피로2 = KSS 8"(Kaida는 8–9를 묶었고 급변점이 없다). Kaida 2006은 주간 실험실·비수면박탈·여성 16명·주행 아님이라 외삽도 가정이다.

권장 문구: "본 데이터셋의 피로2는 KSS 8 부근에서 유의해지는 뇌파 소견(각성 중 뚜렷한 알파 침입)과 정성적으로 일치한다. 이에 **피로1 이상을 탐지 목표로 학습하되(규정이 허용하는 KSS 7 선택 경고에 해당), 법정 필수 경고 기준(KSS 8)과의 비교는 피로2 이상 사건 민감도로 보고한다.**"

## 미확인 요약

1. Vicente 2016 본문의 분류기와 LOSO 세부.
2. Persson 2021 후보 목록과 이진 LOSO 수치.
3. Beniczky 2018 본문 보고 항목.
4. Golz/Sommer 마이크로슬립의 시간당 헛경보.
5. MPD-DF 기술 검증의 분할 방식.
6. 웨어러블 HRV용 FPGA 트리 구현 사례.
7. Euro NCAP 프로토콜의 헛경보 감점 규칙.
8. Bliss & Acton 2003의 신뢰도 조건별 수치.
9. 졸음 경보에서 운전자가 몇 번째 헛경보부터 끄는지에 대한 수치.
