# [PRD] Agent Builder QA Test Automation App

## 1. 개요 (Overview)

본 애플리케이션은 Agent Builder를 통해 생성된 Prompt, Graph, App의 무결성을 검증하기 위한 **End-to-End(E2E) 테스트 자동화 도구**입니다. YAML 기반 시나리오를 통해 복잡한 API 호출 연쇄를 자동화하고, LLM을 활용해 결과의 적절성을 판단합니다.

## 2. 목표 및 핵심 가치

* **리소스 관리 효율화**: 테스트 후 생성된 리소스를 `auto-delete` 옵션으로 자동 정리.
* **검증 신뢰도 향상**: 단순 상태 코드 확인을 넘어 LLM을 통한 정성적 응답 결과 판정.
* **개발 생산성**: 반복적인 Graph/App 생성 및 배포 테스트 과정을 Streamlit 화면에서 원클릭으로 수행.

---

## 3. 애플리케이션 구조 (Application Structure)

동일한 테스트 시나리오(YAML)를 공유하며, 실행 환경에 따라 두 가지 모드로 동작합니다.

```
agent-builder-qa/
├── scenarios/                  # 공유 테스트 시나리오 (YAML + JSON)
│   ├── 01_simple_chat/
│   │   ├── scenario.yaml
│   │   └── ...
│   └── ...
├── core/                       # 공유 핵심 로직
│   ├── engine.py               # 시나리오 실행 엔진 (Scenario Pipeline)
│   ├── judge.py                # LLM Judge 로직
│   └── models.py               # Pydantic 데이터 모델
├── app_streamlit/              # [Mode 1] Streamlit UI 앱
│   └── main.py
└── app_cli/                    # [Mode 2] CLI / CronJob 앱
    └── main.py
```

### Mode 1: Streamlit (Interactive UI)

개발·검증 환경에서 브라우저 기반 UI로 테스트를 수동 실행합니다.

| 기능 | 설명 |
| --- | --- |
| **Environment Setup** | Sidebar에서 LLM API Key, Base URL, Admin Token 등 설정 |
| **Scenario Reload** | YAML 파일 수정 후 UI에서 즉시 재로드하여 재실행 가능 |
| **Single / Batch 선택** | Multi-select box로 특정 시나리오만 실행하거나 전체 일괄 실행 |
| **실시간 진행 상황** | `st.status`로 단계별 진행 노출 |
| **결과 리포트** | `st.dataframe` / `st.expander`로 LLM 판정 결과 및 상세 로그 표시 |

```bash
# 실행
streamlit run app_streamlit/main.py
```

### Mode 2: K8s CronJob (CLI / 자동화)

CI 또는 Kubernetes CronJob 환경에서 터미널로 실행하고, 결과를 표준 출력(stdout)에 출력한 뒤 종료합니다.

| 기능 | 설명 |
| --- | --- |
| **Environment 주입** | ConfigMap 또는 Job spec의 환경변수(`LLM_API_KEY`, `BASE_URL` 등)로 설정 주입 |
| **Single / Batch 선택** | 환경변수 또는 Job spec 인자(`--scenario`, `--all`)로 실행 범위 지정 |
| **결과 출력** | 시나리오별 PASS/FAIL 및 LLM 판정 사유를 shell stdout에 출력 후 종료 |
| **Exit Code** | 하나 이상 실패 시 exit code `1` 반환 (CI 연동 지원) |

```bash
# 단건 실행
python app_cli/main.py --scenario 01_simple_chat

# 전체 실행
python app_cli/main.py --all
```

```yaml
# Kubernetes CronJob 예시
apiVersion: batch/v1
kind: CronJob
metadata:
  name: agent-builder-qa
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: qa-runner
              image: agent-builder-qa:latest
              args: ["--all"]
              env:
                - name: LLM_API_KEY
                  valueFrom:
                    secretKeyRef:
                      name: qa-secret
                      key: llm-api-key
                - name: BASE_URL
                  valueFrom:
                    configMapKeyRef:
                      name: qa-config
                      key: base-url
                - name: SCENARIO
                  valueFrom:
                    configMapKeyRef:
                      name: qa-config
                      key: scenario   # "all" 또는 특정 시나리오 디렉토리명
```

---

## 4. 시스템 아키텍처 및 워크플로우 (Scenario Pipeline)

### **주요 프로세스**

1. **Environment Setup**: LLM 설정 및 API Base URL 로드.
2. **Scenario Loading**: 특정 디렉토리 내 모든 `.yaml` 스캔.
3. **리소스 준비 단계** (Prompts → Graph 순서로 처리):
   - **Prompts/Tools/MCPs Stage**: 아래 리소스 처리 로직에 따라 각 리소스를 준비하고 ID 맵 구성.
   - **LLM 치환값 맵 구성**: `scenario.yaml`의 `llm` 항목에서 `placeholder_in_graph`를 key, `replace_to`를 value로 맵에 추가.
   - **Graph Stage**: ID 맵 기반으로 graph JSON 내 `@@...@@` 변수 치환 후 Graph 생성/업데이트.
4. **App Stage**: 생성된 Graph 기반 App 배포 API 호출 → Stream API 호출 → **LLM 판정**.
5. **Cleanup**: `auto-delete: true` 항목에 대해 Delete API 순차 실행 (App → Graph → Prompt).

### **리소스 처리 로직 (Prompts / Tools / MCPs 공통)**

```
1. GET API로 동일한 name을 가진 리소스 검색
2. 검색 결과가 있으면:
   a. update-if-exists == true → PUT API로 업데이트
   b. update-if-exists == false → 기존 리소스 재사용 (업데이트 생략)
3. 검색 결과가 없으면: POST API로 신규 생성
4. 확보한 리소스의 id를 ID 맵에 추가
   - key: placeholder_in_graph 값
   - value: 리소스 id
   - 예시: {"generator_01_prompt": "w3sgb-..."}
```

### **Graph JSON 변수 치환 로직**

```
1. graph.file_path의 JSON 파일 로드
2. JSON 내 @@...@@ 형식으로 감싸진 모든 플레이스홀더 탐색
3. ID 맵(prompts/tools/mcps ID + llm 치환값)에서 해당 키를 찾아 값으로 교체
4. 치환 완료된 JSON으로 Graph 생성(POST) 또는 업데이트(PUT)
```

---

## 4-1. API 엔드포인트 명세

> Base URL: `{adxp-endpoint}` (환경 설정의 Agent Builder Base URL)

### Prompt
| 동작 | Method | Path |
|------|--------|------|
| 이름으로 검색 | GET | `/api/v1/agent/inference-prompts?name={name}` |
| 생성 | POST | `/api/v1/agent/inference-prompts` |
| 업데이트 | PUT | `/api/v1/agent/inference-prompts/{id}` |
| 삭제 | DELETE | `/api/v1/agent/inference-prompts/{id}` |

### Graph
| 동작 | Method | Path |
|------|--------|------|
| 이름으로 검색 | GET | `/api/v1/agent/agents/graphs?name={name}` |
| 생성 | POST | `/api/v1/agent/agents/graphs` |
| 업데이트 | PUT | `/api/v1/agent/agents/graphs/{id}` |
| 삭제 | DELETE | `/api/v1/agent/agents/graphs/{id}` |
| Stream 테스트 | POST | `/api/v1/agent/agents/graphs/stream` |

### App
| 동작 | Method | Path |
|------|--------|------|
| 생성 | POST | `/api/v1/agent/agents/apps` |
| 삭제 | DELETE | `/api/v1/agent/agents/apps/{id}` |
| Stream 테스트 | POST | `/api/v1/agent_gateway/{app_id}/stream` |

---

## 5. 세부 기능 요구사항

### 5.1. 설정 관리 (Config Management)

* **Default LLM 세팅**: 판정용 LLM(OpenAI, Anthropic 등)의 모델명, API Key, Temperature 설정.
* **Endpoint 설정**: Agent Builder 서비스의 Base URL 및 Admin Token 관리.

### 5.2. 시나리오 탐색 및 선택

* **Directory Scan**: 지정된 폴더(예: `./scenarios`) 내의 YAML 파일을 리스트업.
* **Execution Mode**:
  * **Single**: 특정 시나리오만 선택 실행.
  * **Batch**: 전체 시나리오를 `queue`에 담아 순차 실행.

### 5.3. 테스트 엔진 (Execution Logic)

* **변수 치환 시스템**:
  * Prompts/Tools/MCPs는 GET으로 이름 검색 → 존재 시 `update-if-exists` 확인 후 PUT 또는 재사용, 없으면 POST 생성.
  * 각 리소스의 id를 `{placeholder_in_graph: id}` 형태의 ID 맵으로 관리.
  * LLM 항목은 `scenario.yaml`에서 직접 읽어 `{placeholder_in_graph: replace_to}` 형태로 ID 맵에 추가.
  * Graph 생성/업데이트 시 JSON 내 `@@...@@` 플레이스홀더를 ID 맵의 값으로 일괄 치환.

* **LLM Judge**:
  * `answer-judge`에 정의된 `question`을 전달.
  * 출력 응답과 `criteria`를 LLM에게 전달하여 PASS/FAIL 및 사유 도출.

### 5.4. 리포트 및 결과 표시

  * **Real-time Log**: 현재 수행 중인 단계(Prompt 생성 중, Graph 테스트 중...)를 실시간 노출.
  * **Result Table**: 시나리오별 최종 결과(Success/Fail), 응답 시간, LLM 판정 사유 표시.

---

## 6. 데이터 스키마 (YAML/JSON)

### 6.1. 시나리오 YAML 

제공해주신 구조에 흐름 제어를 위한 필드를 유지합니다.



```yaml
scenario_name: "Simple Chatbot E2E Test"
graph:
  name: "[QA]simple_chatbot"
  file_path: "./scenarios/01_simple/graph_simple_chatbot.json"
  auto-delete: true
  update-if-exists: false
app:
  name: "[QA]simple_chatbot_app"
  auto-delete: true
llms:
  - placeholder_in_graph: gerator_01_serving_name 
    replace_to: "GIP/gpt-4.1" #환경별로 달라질 수 있습니다.
  - placeholder_in_graph: multiquery_01_serving_name 
    replace_to: "GIP/gpt-4o" #환경별로 달라질 수 있습니다.
prompts:
  - name: "[QA]generator_basic"
    placeholder_in_graph: generator_01_basic
    json_path: "./scenarios/01_simple/prompt_generator_01_basic.json"
    auto-delete: true 
    update-if-exists: false
tools:
  - name: "tavily_search"
    placeholder_in_graph: generator_01_tavily
    json_path: "./scenarios/01_simple/tool_generator_01_tavily.json"
    auto-delete: false
    update-if-exists: false
mcps:
  - name: "cinema-search"
    placeholder_in_graph: generator_01_cinema
    json_path: "./scenarios/01_simple/mcp_generator_01_cinema.json"
    auto-delete: false
    update-if-exists: false
knowledges:
  - name: "test-knowledge"
    placeholder_in_graph: retriever_01_repo
    json_path: "./scenarios/01_simple/know_retriever_01_repo.json"
    auto-delete: false
    update-if-exists: false


answer-judge:
  request_json_path: "./scenarios/01_simple/request.json"
  criteria: 
    - "인사말에 적절히 대답해야 함"
    - "HTTP Status 200"

```

**필드 설명**
- json_path: 생성 및 업데이트 할 때 사용할 request body가 담긴 json
- placeholder_in_graph : graph.json에서 대치할 대상. value로 `@@gerator_01_serving_name@@ `이렇게 이중 골뱅이로 되어있어야 대치 가능합니다.
- auto-delete: 테스트 완료 후 자동으로 삭제할지 여부
- update-if-exists: 동일한 이름의 프롬프트가 이미 존재하면 update 할지 여부. default 는 false 입니다.

---

## 7. UI/UX 상세 (Streamlit)

| 페이지 섹션 | 주요 컴포넌트 |
| --- | --- |
| **Sidebar** | LLM API Key, Base URL, 테스트 디렉토리 경로 설정 |
| **Scenario Control** | Multi-select box (시나리오 선택), 'Run All' 버튼, 'Stop' 버튼 |
| **Progress Area** | `st.status`를 활용한 단계별 진행 상황 시각화 |
| **Result Report** | `st.dataframe` 또는 `st.expander`를 이용한 상세 로그 및 LLM 판정 결과 |

---

## 8. 기술 스택 제안

* **Frontend**: Streamlit
* **Language**: Python 3.10+
* **LLM Framework**: LangChain (for LLM Judge logic)
* **API Client**: `httpx` (비동기 처리가 필요할 경우 유용)
* **Data Parsing**: `PyYAML`, `pydantic` (데이터 검증용)

---

## 9. 향후 확장성

* 테스트 결과를 Slack/Teams로 전송하는 Webhook 기능.
* 실패한 시나리오만 재실행하는 'Retry' 기능.
* GitHub Actions와 연동하여 CI 단계에서 자동 실행.

