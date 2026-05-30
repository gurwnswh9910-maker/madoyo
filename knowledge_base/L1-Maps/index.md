---
tags: [architecture, map, l1]
summary: 시스템 전체 조망 및 각 엔진별 역할 정의서
status: stable
last_updated: 2026-05-06
---
# 📍 Madoyo 지식 허브 (L1-Map)

이 문서는 Madoyo Threads 자동화 시스템의 전체 아키텍처와 핵심 설계 철학을 조망하는 **최상위 인덱스**입니다.

## 🏗️ 마스터 가이드
- **[[L1-Maps/reconstruction_blueprint|🚀 시스템 재구축 블루프린트]]**: 소실 시 100% 복구를 위한 마스터 가이드
- **[[L1-Maps/user_operation_sop|📋 사용자 운영 매뉴얼 (SOP)]]**: 일간 워크플로우 및 비상 대응

## 📁 지식 계층 구조

### 1. 엔진 (Engines)
- [[L2-Atomic/engines/mss_scoring_system|🧠 MSS 채점 시스템]]: MAB 알고리즘, 가중치 튜닝, 폴백 공식
- [[L2-Atomic/engines/pipeline_flow|🔄 MAB 파이프라인 7단계]]: Selection Hurdle 3.6x, Semantic Penalty 3제곱, 전체 흐름
- [[L2-Atomic/engines/scraping_engine|🕸️ 수집 엔진 및 기술 구조]]: DOM 분석, 섀도우 밴 방지, 세션 관리
- [[L2-Atomic/engines/visual_context_engine|👁️ 시각 분석 엔진]]: 객관적 묘사 vs 마케팅 인사이트 분리 로직
- [[L2-Atomic/engines/media_engine|🚀 미디어 엔진]]: 획득 즉시 박제(Rehosting) 전략
- [[L2-Atomic/engines/embedding_engine|🧠 임베딩 엔진]]: 캐시 무결성 및 품질 관리

### 2. 마케팅 (Marketing)
- [[L2-Atomic/marketing/prompt_engineering_tactics|✍️ 프롬프트 전술]]: 대조 학습(High/Low), 실패 패턴, 태그 파싱
- [[L2-Atomic/marketing/copy_optimization_formulas|🎯 카피 최적화 공식]]: Cliffhanger·Sensory Twist·Solution Hook + 마이크로 패턴
- [[L2-Atomic/marketing/category_strategies|📊 카테고리별 전략]]: Otter 데이터 기반 패션/뷰티/라이프 성공·실패 규칙
- [[L2-Atomic/marketing/fatigue_and_contrast_patterns|🔁 피로도와 한 끗 차이]]: 반복 노출 50-90% 급감, Win/Loss 격차 분석
- [[L2-Atomic/marketing/dataset_benchmark|📈 데이터셋 벤치마크]]: Elite/2seo_log/dotori 3대 비교, 블루오션 카테고리
- [[L2-Atomic/marketing/persona_and_tone|🎭 페르소나 및 톤]]: 호기심 유발, 금지어, 20대 친구 컨셉
- [[L2-Atomic/marketing/mss_formula_philosophy|💡 MSS 공식 철학]]: 제곱 가중 근거, 감쇠율 튜닝

### 3. 플랫폼 (Platforms)
- [[L2-Atomic/platforms/threads_content_patterns|📝 Threads 콘텐츠 패턴]]: 바이럴 유형, 첫 댓글 문화
- [[L2-Atomic/platforms/threads_ecosystem|🧵 Threads 운영 전략]]: 고전환 카테고리, 정지 사례
- [[L2-Atomic/platforms/threads_technical_structure|🔧 Threads DOM 구조]]: 셀렉터, 미디어 필터링, JSON 메타데이터
- [[L2-Atomic/platforms/coupang_ecosystem|🛒 Coupang 유통 지식]]: 딥링크, 아카마이 차단, 수익화

### 4. 운영 및 인프라 (Ops & Infra)
- [[L2-Atomic/accounts/multi_account_strategy|👥 다중 계정 운영 전략]]: SEHEEHX, DOTORI 등 계정별 페르소나 및 배포 전략
- [[L2-Atomic/accounts/arch_dotori_config|⚙️ DOTORI 계정 설정]]: 개별 계정 특화 설정 기록
- [[L2-Atomic/infrastructure/server_deployment_lore|🌐 서버 구축 및 배포 (Lore)]]: Render, Redis, Celery 트러블슈팅
- [[L2-Atomic/infrastructure/api_async_constraint|⚠️ API 비동기 강제 규칙]]: Task ID 패턴, 블로킹 금지, Render 30초 Timeout
- [[L2-Atomic/constraints/micro_rules|⚖️ 미시적 운영 규칙]]: stop.txt, WinError 32 대응 등
- [[L2-Atomic/constraints/akamai_limits|🛡️ Akamai 및 플랫폼 제약]]: 차단 우회 및 도메인 신뢰도 관리

### 5. 검증 (Validation)
- [[L2-Atomic/validation/data_consistency_check|✅ 무결성 검증]]: `run_validation` 및 물리적 박제

### 1. L0-Core (원칙 및 헌법)
- **[[L0-Core/agent_operation_rules|⚖️ 에이전트 운영 수칙]]**: 터미널 가시성, 한국어 우선, 모델 선호도
- **[[L0-Core/user_rules|⚖️ 서비스 운영 원칙]]**: E드라이브 격리, Chesterton's Fence 방어
- **[[L0-Core/project_origins|🌱 프로젝트 기원]]**: Threads 자동화의 시작과 29MB 대란의 기록

## ⚙️ 시스템 핵심 파이프라인
1. **Queueing**: 엑셀 소스에서 링크 추출 (`threads_auto_pipeline.py`)
2. **Scraping**: Threads 원본 및 쿠팡 상세 페이지 분석 (`scraper.py`)
3. **Capture**: 미디어 만료 전 외부 서버로 즉시 이관
4. **Optimize**: AI(Gemini) 기반 마케팅 카피 최적화 (`작동중코드/`)
5. **Publish**: Threads API를 통한 자동 게시 (`publisher.py`)

## 💡 주요 설계 원칙 (Chesterton's Fence)
- 불필요해 보이는 재시도 루프와 우회 경로는 모두 과거의 시행착오를 통해 검증된 필수 로직입니다.
- 리팩토링 시 반드시 구현 의도 리포트를 먼저 확인하십시오.

### L3-Insights: 시행착오 (Caveats)
- [[L3-Insights/Caveats/ai_data_leak_hallucination|🤖 AI 데이터 누수/환각]]
- [[L3-Insights/Caveats/c_drive_storage_crisis|💾 C드라이브 29MB 대란]]
- [[L3-Insights/Caveats/credit_security_leak|🔓 크레딧 보안 누수]]
- [[L3-Insights/Caveats/threads_media_fetch_failure|🖼️ 미디어 403 차단]]
- [[L3-Insights/Caveats/ip_blocking_and_split_arch|🌐 IP 차단 및 분리 아키텍처]]
- [[L3-Insights/Caveats/ssl_cert_bypass|🔐 SSL 인증서 우회]]

- [[L3-Insights/Reasoning/coupang_dynamic_selectors|🛒 쿠팡 동적 셀렉터]]: 카테고리 리다이렉트 대응 로직
- [[L3-Insights/Reasoning/defensive_termination|🛑 방어적 종료]]
- [[L3-Insights/Reasoning/file_locking_retry|📂 파일 잠금 재시도]]
- [[L3-Insights/Reasoning/resource_isolation|💽 리소스 격리]]
- [[L3-Insights/Reasoning/rule_density_tradeoff|🧠 규칙 밀도 트레이드오프]]
- [[L3-Insights/Reasoning/semantic_erasure_dna|🧬 Semantic Erasure DNA]]
- [[L3-Insights/Reasoning/data_collection_reembedding_cleanup_20260522|🧹 2026-05-22 데이터 수집·재임베딩 정리]]
- [[L3-Insights/Reasoning/text_normalization_logic|📝 텍스트 정규화 로직]]
- [[L3-Insights/Reasoning/copy_prompt_parser_contract_20260506|🧩 카피 프롬프트-파서 계약]]: 프롬프트 출력 태그와 strict parser/content guard 동시 변경 규칙
- [[L3-Insights/Reasoning/copy_prompt_upgrade_rescore_20260507|🧪 카피 프롬프트 안전장치 재채점]]: v10 운영 채택 유지, 길이 효과와 안전장치 포함 scorer 기준 재검증
- [[L3-Insights/Reasoning/threads_body_cluster_extraction_20260518|🧵 Threads 본문 묶음 복원]]: 한 조각 선택에서 본문 묶음 복원으로 변경, 레시피 첫댓글 raw 보존, E드라이브 산출물 기준 검증

- [[L3-Insights/Reasoning/optimization_token_efficiency_0414|0414 Optimization Token Efficiency]]: 임베딩 재사용, 0.985 중복 필터, 형제 카피 3개 출력

- [[L3-Insights/Reasoning/runtime_media_order_fixes_0415|0415 Runtime Media Order Fixes]]: 실전 경량화, 로컬 미디어 캐시 제거, 혼합 미디어 순서 보존

## 0420 Research Shortcuts
- [[L1-Maps/copy_scorer_research_hub|Copy Scorer Research Hub]]
- [[L3-Insights/Reasoning/copy_scorer_research_0501_uploaded_pairwise_gate|0501 Uploaded Pairwise Copy Gate]]
- [[L3-Insights/Reasoning/copy_scorer_research_0502_auxiliary_metric_heads|0502 Auxiliary Metric Heads]]
- [[L3-Insights/Reasoning/copy_prompt_parser_contract_20260506|2026-05-06 Copy Prompt Parser Contract]]
- [[L3-Insights/Reasoning/copy_prompt_upgrade_rescore_20260507|2026-05-07 Prompt Upgrade Safety-Gated Rescore]]
- [[L3-Insights/Reasoning/copy_scorer_benchmarking_0420|0420 Copy Scorer Benchmarking Lessons]]
- [[L3-Insights/Reasoning/copy_scorer_research_0426_summary|0426 Copy Scorer Research Summary]]
