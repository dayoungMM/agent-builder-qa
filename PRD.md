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
3. **Prompt Stage**: JSON 페이로드 로드 → Prompt Import/Create API 호출 → `prompt_id` 추출 및 변수 저장.
4. **Graph Stage**: JSON 내 변수 치환(e.g., `{prompt_name}`) → Graph Import/Create API 호출 → Stream API 호출 → **LLM 판정**.
5. **App Stage**: 생성된 Graph 기반 App 배포 API 호출 → Stream API 호출 → **LLM 판정**.
6. **Cleanup**: `auto-delete: true` 항목에 대해 Delete API 순차 실행 (App → Graph → Prompt).

---

## 4-1. API 엔드포인트 명세

> Base URL: `{adxp-endpoint}` (환경 설정의 Agent Builder Base URL)

### Prompt
| 동작 | Method | Path |
|------|--------|------|
| 생성 (id 미지정) | POST | `/api/v1/agent/inference-prompts` |
| Import (id 지정) | POST | `/api/v1/agent/inference-prompts/import?prompt_uuid={id}` |
| 업데이트 | PUT | `/api/v1/agent/inference-prompts/{id}` |
| 삭제 | DELETE | `/api/v1/agent/inference-prompts/{id}` |

### Graph
| 동작 | Method | Path |
|------|--------|------|
| 생성 (id 미지정) | POST | `/api/v1/agent/agents/graphs` |
| Import (id 지정) | POST | `/api/v1/agent/agents/graphs/import?agent_id={id}` |
| 업데이트 | PUT | `/api/v1/agent/agents/graphs/{id}` |
| 삭제 | DELETE | `/api/v1/agent/agents/graphs/{id}` |
| Stream 테스트 | POST | `/api/v1/agent/agents/graphs/stream` |

### App
| 동작 | Method | Path |
|------|--------|------|
| 생성 | POST | `/api/v1/agent/agents/apps` |
| 삭제 | DELETE | `/api/v1/agent/agents/apps/{id}` |
| Stream 테스트 | POST | `/api/v1/agent_gateway/{app_id}/stream` |

### Import API 동작 규칙
1. 해당 id가 **존재하지 않으면** → 신규 생성. 응답: `{detail: "Created", code: 1}`
2. 해당 id가 존재하고 **내용이 일치하면** → 검증 통과. 응답: `{detail: "Validated", code: 1}`
3. 해당 id가 존재하지만 **내용이 다르면** → 에러 발생
   - `update-if-exists: true` → PUT으로 업데이트
   - `update-if-exists: false` → skip (기존 ID 재사용)

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
  * `graph.file_path`의 JSON 내용을 읽어 `{prompt_name}` 등을 이전 단계에서 확보한 ID로 자동 Replace.
  * 중복 방지를 위해 이름 뒤에 `{datetime}` 접미사 부여 (단, `force-create: true`인 경우).

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
  force-create: false
app:
  name: "[QA]simple_chatbot_app"
  auto-delete: true
prompts:
  - name: "[QA]generator_basic"
    json_path: "./scenarios/01_simple/prompt_generator_basic.json" # 실제 body가 담긴 파일
    auto-delete: true
answer-judge:
  questions:
    - "안녕"
  criteria:
    - "인사말에 적절히 대답해야 함"
    - "HTTP Status 200"

```

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

**다음 단계로 이 PRD를 바탕으로 Streamlit의 기본 레이아웃 코드 초안을 작성해 드릴까요?**