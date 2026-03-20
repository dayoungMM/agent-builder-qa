# Streamlit App Dev Workboard

## 상태 범례
- `[ ]` 미완료
- `[x]` 완료
- `[-]` 진행 중

---

## Phase 1: Core Layer (공유 로직)

### 1-1. `core/models.py` — Pydantic 데이터 모델
- [x] `PromptConfig` 모델 (id, name, json_path, auto-delete, update-if-exists)
- [x] `GraphConfig` 모델 (id, name, file_path, auto-delete, update-if-exists, force-create)
- [x] `AppConfig` 모델 (name, auto-delete, force-create) — Task 7
- [x] `LLMConfig` 모델 (placeholder_in_graph, replace_to) — Task 1
- [x] `ToolConfig` 모델 (name, id, json_path, auto-delete, update-if-exists) — Task 2
- [x] `MCPConfig` 모델 (name, id, json_path, auto-delete, update-if-exists) — Task 3
- [x] `KnowledgeConfig` 모델 (name, id, json_path, auto-delete, update-if-exists) — Task 4
- [x] `AnswerJudge` 모델 (questions, criteria, request-json-path) — Task 5
- [x] `Scenario` 모델 (scenario_name, graph, app, llms, prompts, tools, mcps, knowledges, answer-judge)
- [x] `StepResult` 모델 (step명, status, response, elapsed_time, judge_result, judge_reason)
- [x] `ScenarioResult` 모델 (scenario_name, steps: list[StepResult], final_status)

### 1-2. `core/judge.py` — LLM Judge 로직
- [x] LLM 클라이언트 초기화 (OpenAI / Anthropic 지원, LangChain 기반)
- [x] `judge(response: str, question: str, criteria: list[str]) -> JudgeResult` 함수
  - criteria를 LLM에게 전달하여 PASS/FAIL 및 사유 반환
  - Structured output (pydantic) 으로 결과 파싱
- [x] Judge prompt 템플릿 정의

### 1-3. `core/engine.py` — 시나리오 실행 엔진
- [x] `ScenarioEngine` 클래스 설계
  - 생성자: `base_url`, `admin_token`, `judge` 인스턴스 수신
- [x] `load_scenario(yaml_path: str) -> Scenario` 함수
  - YAML 파일 파싱 → Scenario 모델로 변환
- [x] `scan_scenarios(scenarios_dir: str) -> list[str]` 함수
  - 지정 디렉토리 내 모든 scenario.yaml 탐색
- [x] **Prompt Stage** 실행 로직
  - JSON 파일 로드 (json_path)
  - `update-if-exists: false` → 이미 존재 시 기존 ID 재사용
  - POST `/prompts` API 호출 → `prompt_id` 추출 및 컨텍스트 저장
- [x] **Tool Stage** 실행 로직 — Task 2
  - POST `/api/v1/agent/tools/import?tool_uuid={id}` 또는 POST `/api/v1/agent/tools`
- [x] **MCP Stage** 실행 로직 — Task 3
  - POST `/api/v1/mcp/catalogs/import?mcp_id={id}` 또는 POST `/api/v1/mcp/catalogs`
- [x] **Knowledge Stage** 실행 로직 — Task 4
  - POST `/api/v1/rag/repos/import?repo_id={id}` 또는 POST `/api/v1/rag/repos`
- [x] **Graph Stage** 실행 로직
  - JSON 파일 로드 (file_path)
  - `@@placeholder@@` LLM 치환 (이전 LLM 단계 결과로) — Task 1
  - `{prompt_name}` 변수 치환 (이전 단계 결과로)
  - `force-create: true` 시 이름에 `{datetime}` 접미사 부여
  - `update-if-exists: false` → 이미 존재 시 기존 ID 재사용
  - POST/PUT `/graphs` API 호출 → `graph_id` 추출
  - `request_json_path` 있으면 해당 JSON을 stream request body로 사용 — Task 5
  - `HTTP Status {code}` criteria 자동 검증 (별도 step) — Task 6
  - LLM Judge 호출 → 판정 결과 저장 (나머지 criteria만)
- [x] **App Stage** 실행 로직
  - `force-create: true` 시 타임스탬프 suffix로 항상 신규 생성 — Task 7
  - Graph 기반 App 배포 API 호출
  - `request_json_path` 있으면 해당 JSON을 stream request body로 사용 — Task 5
  - `HTTP Status {code}` criteria 자동 검증 (별도 step) — Task 6
  - LLM Judge 호출 → 판정 결과 저장 (나머지 criteria만)
- [x] **Cleanup Stage** 로직
  - `auto-delete: true` 항목 (App → Graph → Prompt → Tool → MCP → Knowledge 순) DELETE API 호출
- [x] `run_scenario(yaml_path: str) -> ScenarioResult` 함수 (위 단계들 오케스트레이션)
- [x] 단계별 진행 상황을 콜백(callback)으로 외부에 노출 (Streamlit 실시간 연동용)

---

## Phase 2: Streamlit UI (`app_streamlit/main.py`)

### 2-1. Sidebar — 환경 설정
- [x] LLM Provider 선택 (OpenAI / Anthropic)
- [x] LLM API Key 입력 (`st.text_input`, type=password)
- [x] LLM Model명 입력
- [x] Agent Builder Base URL 입력
- [x] Admin Token 입력 (`st.text_input`, type=password)
- [x] Scenarios 디렉토리 경로 입력 (기본값: `./scenarios`)
- [x] 설정값 `st.session_state`에 저장

### 2-2. Scenario Control — 시나리오 선택 및 실행
- [x] **Scenario Reload** 버튼 → `scan_scenarios()` 재호출, 목록 갱신
- [x] Multi-select box → 실행할 시나리오 선택
- [x] **Run Selected** 버튼 → 선택한 시나리오만 실행
- [x] **Run All** 버튼 → 전체 시나리오 일괄 실행
- [x] **Stop** 버튼 → 실행 중단 (session_state 플래그 + InterruptedError 방식)

### 2-3. Progress Area — 실시간 진행 상황
- [x] `st.status` 컴포넌트로 단계별 진행 노출
- [x] 각 시나리오별 개별 status 블록 표시
- [x] 엔진 콜백 연동 → 단계 완료 시 status 업데이트

### 2-4. Result Report — 결과 표시
- [x] 전체 요약 테이블 (`st.dataframe`)
  - 컬럼: 시나리오명, 최종 결과(PASS/FAIL), 총 소요(s), LLM 판정 요약
- [x] 시나리오별 상세 로그 (`st.expander`)
  - 각 Step의 응답 raw data 표시
  - Judge 판정 사유 표시
- [x] PASS/FAIL 컬러링 (green/red)

---

## Phase 3: 통합 및 마무리

- [x] `requirements.txt` 의존성 정리
  - `streamlit`, `httpx`, `pyyaml`, `pydantic`, `langchain-core`, `langchain-openai`, `langchain-anthropic`
- [x] `scenarios/01_simple_chat/` 시나리오 완성 (graph_simple_chatbot.json, prompt_generator_basic.json)
- [ ] 전체 E2E 흐름 수동 테스트 (Streamlit 실행 → 시나리오 실행 → 결과 확인)
- [x] 엣지 케이스 처리
  - API 호출 실패 시 에러 표시: engine.py 각 Stage에서 Exception → StepStatus.ERROR, 이후 단계 스킵
  - 네트워크 타임아웃 처리: httpx.Client timeout=120s 설정
  - 중복 리소스 존재 시 `update-if-exists` 로직: HTTP 405 + update_if_exists=True → PUT, 그 외 → raise

---

## API 엔드포인트 파악 필요 목록 (구현 전 확인)
- [x] Prompt CRUD: `POST /api/v1/agent/inference-prompts/import?prompt_uuid={id}`, `DELETE /api/v1/agent/inference-prompts/{id}`, `PUT /api/v1/agent/inference-prompts/{id}`
- [x] Graph CRUD: `POST /api/v1/agent/agents/graphs/import?agent_id={id}`, `PUT /api/v1/agent/agents/graphs/{id}`, `DELETE /api/v1/agent/agents/graphs/{id}`
- [x] Graph Stream: `POST /api/v1/agent/agents/graphs/{id}/stream` (path에 ID 포함, engine._stream_graph 수정 완료)
- [x] App CRUD: `GET /api/v1/agent/agents/apps`, `POST /api/v1/agent/agents/apps`, `DELETE /api/v1/agent/agents/apps/{id}`
- [x] App Stream: `POST /api/v1/agent_gateway/{id}/stream`
- [x] 인증 방식:
      - App Stream: `GET /api/v1/agent/agents/apps/{app_id}/apikeys` → apikey를 Bearer로 인증 (engine._get_app_apikey + _stream_app 수정 완료)
      - 그 외 API: admin_token Bearer 인증
