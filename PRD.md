# [PRD] Agent Builder QA Test Automation App

## 1. 개요 (Overview)

본 애플리케이션은 Agent Builder를 통해 생성된 Prompt, Graph, App의 무결성을 검증하기 위한 **End-to-End(E2E) 테스트 자동화 도구**입니다. YAML 기반 시나리오를 통해 복잡한 API 호출 연쇄를 자동화하고, LLM을 활용해 결과의 적절성을 판단합니다.

## 2. 목표 및 핵심 가치

* **리소스 관리 효율화**: 테스트 후 생성된 리소스를 `auto-delete` 옵션으로 자동 정리.
* **검증 신뢰도 향상**: 단순 상태 코드 확인을 넘어 LLM을 통한 정성적 응답 결과 판정.
* **개발 생산성**: 반복적인 Graph/App 생성 및 배포 테스트 과정을 Streamlit 화면에서 원클릭으로 수행.

---

## 3. 시스템 아키텍처 및 워크플로우

### **주요 프로세스 (Scenario Pipeline)**

1. **Environment Setup**: LLM 설정 및 API Base URL 로드.
2. **Scenario Loading**: 특정 디렉토리 내 모든 `.yaml` 스캔.
3. **Prompt Stage**: JSON 페이로드 로드 → Prompt 생성 API 호출 → `prompt_id` 추출 및 변수 저장.
4. **Graph Stage**: JSON 내 변수 치환(e.g., `{prompt_id}`) → Graph 생성/조회 → Stream API 호출 → **LLM 판정**.
5. **App Stage**: 생성된 Graph 기반 App 배포 API 호출 → Stream API 호출 → **LLM 판정**.
6. **Cleanup**: `auto-delete: true` 항목에 대해 Delete API 순차 실행.

---

## 4. 세부 기능 요구사항

### 4.1. 설정 관리 (Config Management)

* **Default LLM 세팅**: 판정용 LLM(OpenAI, Anthropic 등)의 모델명, API Key, Temperature 설정.
* **Endpoint 설정**: Agent Builder 서비스의 Base URL 및 Admin Token 관리.

### 4.2. 시나리오 탐색 및 선택

* **Directory Scan**: 지정된 폴더(예: `./scenarios`) 내의 YAML 파일을 리스트업.
* **Execution Mode**:
  * **Single**: 특정 시나리오만 선택 실행.
  * **Batch**: 전체 시나리오를 `queue`에 담아 순차 실행.



### 4.3. 테스트 엔진 (Execution Logic)

* **변수 치환 시스템**:
  * `graph.file_path`의 JSON 내용을 읽어 `{prompt_name}` 등을 이전 단계에서 확보한 ID로 자동 Replace.
  * 중복 방지를 위해 이름 뒤에 `{datetime}` 접미사 부여 (단, `force-create: true`인 경우).


* **LLM Judge**:
  * `answer-judge`에 정의된 `question`을 전달.
  * 출력 응답과 `criteria`를 LLM에게 전달하여 PASS/FAIL 및 사유 도출.



### 4.4. 리포트 및 결과 표시

  * **Real-time Log**: Streamlit 화면에 현재 수행 중인 단계(Prompt 생성 중, Graph 테스트 중...)를 실시간 노출.
  * **Result Table**: 시나리오별 최종 결과(Success/Fail), 응답 시간, LLM 판정 사유 표시.

---

## 5. 데이터 스키마 (YAML/JSON)

### 5.1. 시나리오 YAML 

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

## 6. UI/UX 상세 (Streamlit)

| 페이지 섹션 | 주요 컴포넌트 |
| --- | --- |
| **Sidebar** | LLM API Key, Base URL, 테스트 디렉토리 경로 설정 |
| **Scenario Control** | Multi-select box (시나리오 선택), 'Run All' 버튼, 'Stop' 버튼 |
| **Progress Area** | `st.status`를 활용한 단계별 진행 상황 시각화 |
| **Result Report** | `st.dataframe` 또는 `st.expander`를 이용한 상세 로그 및 LLM 판정 결과 |

---

## 7. 기술 스택 제안

* **Frontend**: Streamlit
* **Language**: Python 3.10+
* **LLM Framework**: LangChain (for LLM Judge logic)
* **API Client**: `httpx` (비동기 처리가 필요할 경우 유용)
* **Data Parsing**: `PyYAML`, `pydantic` (데이터 검증용)

---

## 8. 향후 확장성

* 테스트 결과를 Slack/Teams로 전송하는 Webhook 기능.
* 실패한 시나리오만 재실행하는 'Retry' 기능.
* GitHub Actions와 연동하여 CI 단계에서 자동 실행.

**다음 단계로 이 PRD를 바탕으로 Streamlit의 기본 레이아웃 코드 초안을 작성해 드릴까요?**