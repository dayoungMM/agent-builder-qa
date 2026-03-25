# Agent Builder QA — 개발자 가이드

이 문서는 Agent Builder QA 프로젝트에 기여하는 개발자를 위한 실무 가이드입니다.
Claude Code를 활용한 시나리오 추가, 코어 로직 수정, Streamlit UI 개선 방법을 다룹니다.

---

## 목차

1. [개발 환경 세팅](#1-개발-환경-세팅)
2. [프로젝트 구조 이해](#2-프로젝트-구조-이해)
3. [새 시나리오 추가 방법](#3-새-시나리오-추가-방법)
4. [코어 로직 수정 가이드](#4-코어-로직-수정-가이드)
5. [Streamlit UI 수정 가이드](#5-streamlit-ui-수정-가이드)
6. [검증 방법](#6-검증-방법)
7. [자주 쓰는 Claude Code 팁](#7-자주-쓰는-claude-code-팁)
8. [Playwright MCP로 브라우저 테스트 자동화](#8-playwright-mcp로-브라우저-테스트-자동화)

---

## 1. 개발 환경 세팅

### 요구사항

- Python 3.10+

### 패키지 설치

```bash
pip install -r requirements.txt
```

주요 의존성:

| 패키지 | 용도 |
|--------|------|
| `pydantic>=2.0` | 데이터 모델 (models.py) |
| `pyyaml>=6.0` | scenario.yaml 파싱 |
| `httpx>=0.27` | Agent API HTTP 호출 |
| `langchain-core/openai/anthropic` | LLM Judge |
| `streamlit>=1.35` | Streamlit UI |

### 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하거나, Streamlit Sidebar에서 직접 입력합니다.

```bash
# Agent Backend API 기본 URL
BASE_URL=http://agent-backend.aiplatform.svc.cluster.local

# 인증 토큰 (Sidebar에서 로그인하거나 직접 입력)
# AUTH_URL, AUTH_USERNAME, AUTH_PASSWORD, AUTH_CLIENT_ID 로 자동 로그인도 가능

# LLM Judge 설정
LLM_PROVIDER=adxp          # adxp | openai | anthropic
LLM_API_KEY=your-api-key
LLM_MODEL=GIP/gpt-4.1
ADXP_JUDGE_ENDPOINT=http://agent-gateway.aiplatform.svc.cluster.local/api/v1/agent_gateway

# SSL 검증 비활성화 (내부망 환경)
SSL_VERIFY=false
```

### 로컬 실행

```bash
streamlit run app_streamlit/main.py
```

브라우저에서 `http://localhost:8501` 접속 후 Sidebar에서 설정을 입력합니다.

---

## 2. 프로젝트 구조 이해

```
agent-builder-qa/
├── scenarios/              # 테스트 시나리오 (YAML + JSON)
│   ├── 01_simple_chat/
│   ├── 02_llm_parameter/
│   ├── 03_rag_tool_mcp/
│   └── 04_translator/
├── core/                   # 공유 핵심 로직
│   ├── models.py           # Pydantic 데이터 모델
│   ├── engine.py           # 시나리오 실행 엔진
│   └── judge.py            # LLM Judge 로직
├── app_streamlit/          # Streamlit UI 앱 (← 개발 대상)
│   └── main.py
├── app_cli/                # CLI / K8s CronJob 앱 (← 수정 금지)
│   └── main.py
└── CLAUDE.md               # Claude Code 개발 지침
```

### `core/` 3개 파일 역할

| 파일 | 역할 |
|------|------|
| `models.py` | 시나리오 구조를 표현하는 Pydantic 모델. `Scenario`, `GraphConfig`, `PromptConfig` 등 정의. |
| `engine.py` | `ScenarioEngine` 클래스. 시나리오 YAML을 읽어 API를 순서대로 호출 (리소스 생성 → Graph 생성 → App 생성 → 채팅 → 정리). |
| `judge.py` | `LLMJudge` 클래스. LLM을 호출해 채팅 응답이 criteria를 충족하는지 PASS/FAIL 판정. |

**데이터 흐름**: `scenario.yaml` → `models.py` (파싱) → `engine.py` (실행) → `judge.py` (판정)

### `scenarios/` 디렉토리 구조 및 네이밍 규칙

```
scenarios/
└── {NN}_{name}/            # 두 자리 숫자 + 설명 (예: 01_simple_chat)
    ├── scenario.yaml        # 시나리오 메타데이터 및 실행 설정
    ├── graph_{name}.json    # Graph 생성 API payload
    ├── prompt_{uuid}.json   # Prompt 생성 API payload (있을 때만)
    ├── tool_{uuid}.json     # Tool 생성 API payload (있을 때만)
    ├── mcp_{uuid}.json      # MCP 생성 API payload (있을 때만)
    └── know_{uuid}.json     # Knowledge 참조 정보 (있을 때만)
```

### `app_streamlit/main.py` 역할

- **Sidebar**: API 설정 (BASE_URL, Admin Token, LLM Judge 설정), 로그인
- **Tab 1 — Test Runner**: 시나리오 선택 및 실행, 단계별 진행 현황 실시간 표시, 결과 요약
- **Tab 2 — Scenario Editor**: 시나리오 파일 직접 편집 UI

### 개발 범위 안내

> **수정 가능**: `app_streamlit/`, `core/`, `scenarios/`
> **수정 금지**: `app_cli/` (Cursor 담당)

---

## 3. 새 시나리오 추가 방법

### Claude Code Skill 사용 (권장)

Claude Code에서 `/adxp-agent-e2e-test-helper` 명령어를 실행하면 대화형으로 시나리오를 생성할 수 있습니다.

```
/adxp-agent-e2e-test-helper
```

Skill이 단계별로 안내합니다:
1. `echoapi.json` (EchoAPI/Postman export) 확인
2. `graph.json` 생성 (자동 추출 or 직접 제공)
3. UUID 확인 및 연관 JSON 파일 생성
4. `scenario.yaml` 생성

---

### 수동 추가 절차

#### Step 1: 디렉토리 생성

```bash
mkdir -p scenarios/05_my_scenario
```

폴더명 규칙: `{두자리숫자}_{설명}` (예: `05_my_scenario`)

#### Step 2: graph.json 작성

Graph 생성 API의 request body를 JSON으로 저장합니다.

```bash
# 파일명: graph_{name}.json
scenarios/05_my_scenario/graph_my_scenario.json
```

**중요 규칙**:
- `id` 필드는 UUID로 하드코딩 (테스트 간 리소스 식별용)
- LLM `serving_name`은 `@@llm_{node_name}@@` 형식의 플레이스홀더로 교체

```json
// Before (실제 모델명 직접 지정)
"serving_name": "GIP/gpt-4.1"

// After (플레이스홀더로 교체)
"serving_name": "@@llm_agent__generator_1@@"
```

UUID 생성이 필요하면:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

#### Step 3: 리소스 JSON 파일 작성

각 리소스 유형에 맞는 API payload JSON 파일을 생성합니다.
파일명은 반드시 `{type}_{uuid}.json` 형식을 따릅니다.

| 리소스 | 파일명 예시 | graph.json 연결 필드 |
|--------|-----------|-------------------|
| Prompt | `prompt_{uuid}.json` | `prompt_id` |
| Tool | `tool_{uuid}.json` | `tool_ids[]` |
| MCP | `mcp_{uuid}.json` | `mcp_catalogs[].id` |
| Knowledge | `know_{uuid}.json` | `repo_id` |

**Prompt JSON 예시**:
```json
{
  "name": "[QA]my_prompt",
  "desc": null,
  "release": true,
  "messages": [
    { "message": "You are a helpful assistant.", "mtype": 1 },
    { "message": "{{query}}", "mtype": 2 }
  ],
  "tags": [],
  "variables": [
    {
      "variable": "query",
      "token_limit": 0,
      "token_limit_flag": false,
      "validation": "",
      "validation_flag": false
    }
  ]
}
```

> `release`는 항상 `true`. `uuid`, `version_id`, `sequence` 필드는 포함하지 않습니다.

#### Step 4: request.json 작성 (선택)

채팅 API 호출 시 커스텀 request body가 필요한 경우 별도 JSON 파일로 작성하고 `scenario.yaml`의 `request-body-path`에 경로를 지정합니다.

#### Step 5: scenario.yaml 작성

```yaml
scenario_name: "My Scenario E2E Test"

graph:
  id: <uuid>                           # UUID 하드코딩 필수
  name: "[QA]my_scenario"              # [QA] 접두사 필수
  file_path: "./scenarios/05_my_scenario/graph_my_scenario.json"
  auto-delete: true
  update-if-exists: false

app:
  name: "[QA]my_scenario_app"          # [QA] 접두사 필수
  auto-delete: true                    # app은 항상 true 권장

llms:
  - placeholder_in_graph: llm_agent__generator_1   # @@는 제외
    replace_to: "GIP/gpt-4.1"

prompts:
  - id: <uuid>                         # graph.json의 prompt_id와 동일
    name: "[QA]my_prompt"
    json_path: "./scenarios/05_my_scenario/prompt_<uuid>.json"
    auto-delete: true
    update-if-exists: false

answer-judge:
  - question: "테스트 질문"
    criteria:
      - "응답 판정 기준"
      - "HTTP Status 200"
```

---

### scenario.yaml 체크리스트

| 항목 | 확인 사항 |
|------|----------|
| `graph.id` | UUID가 graph.json 내 id와 일치하는가 |
| `prompts[].id` | graph.json의 `prompt_id`와 일치하는가 |
| `tools[].id` | graph.json의 `tool_ids[]` 값과 일치하는가 |
| `mcps[].id` | graph.json의 `mcp_catalogs[].id`와 일치하는가 |
| `auto-delete` | 테스트 환경 오염 방지를 위해 임시 리소스는 `true` |
| `update-if-exists` | 서버 기존 리소스 덮어쓰기 여부 의도 확인 |
| `criteria` | 실제 검증 의도를 반영하는가 |
| `[QA]` 접두사 | 모든 `name` 필드에 `[QA]` 접두사가 있는가 |

---

### Placeholder `@@` 포함/제외 규칙

| 리소스 | scenario.yaml `placeholder_in_graph` | graph.json |
|--------|--------------------------------------|------------|
| **LLM** | `@@` **제외** (예: `llm_agent__generator_1`) | `@@llm_agent__generator_1@@` |
| **Knowledge** | `@@` **포함** (예: `@@select_knowledge@@`) | `@@select_knowledge@@` |

---

### 기존 시나리오 패턴 비교

| 시나리오 | LLM | Prompt | Tool | MCP | Knowledge | 특징 |
|----------|-----|--------|------|-----|-----------|------|
| `01_simple_chat` | ✅ | ✅ | - | - | - | 가장 단순한 챗봇 |
| `02_llm_parameter` | ✅ | ✅ | - | - | - | LLM 파라미터(temperature 등) 테스트 |
| `03_rag_tool_mcp` | ✅ (2개) | ✅ | ✅ | ✅ | ✅ | RAG + Tool + MCP 복합 |
| `04_translator` | - | ✅ (2개) | - | - | - | 다중 Prompt 노드 |

---

## 4. 코어 로직 수정 가이드

### `core/models.py` — Pydantic 모델 추가/변경

모든 모델은 `pydantic.BaseModel`을 상속하며, YAML의 kebab-case 필드명을 alias로 처리합니다.

```python
class PromptConfig(BaseModel):
    auto_delete: bool = Field(default=False, alias="auto-delete")
    update_if_exists: bool = Field(default=False, alias="update-if-exists")

    model_config = {"populate_by_name": True}  # alias와 field명 모두 허용
```

**새 필드 추가 시 주의사항**:
- YAML에서 kebab-case로 쓰이는 필드는 반드시 `alias` 지정
- `model_config = {"populate_by_name": True}` 필수 (없으면 alias로만 접근 가능)
- `Optional` 필드에는 항상 `default=None` 또는 `default_factory` 지정

### `core/engine.py` — 새 리소스 타입 추가

현재 엔진이 처리하는 리소스 타입: `prompts` → `tools` → `mcps` → `knowledges` → `graph` → `app`

새 리소스 타입을 추가할 때는 기존 패턴을 따릅니다:
1. `core/models.py`에 Config 모델 추가 (예: `NewResourceConfig`)
2. `Scenario` 모델에 필드 추가
3. `engine.py`에서 해당 리소스의 생성/조회/업데이트/삭제 메서드 추가
4. `run()` 메서드의 단계 순서에 삽입

### `core/judge.py` — LLM Provider 추가

현재 지원 provider: `adxp`, `openai`, `anthropic`

새 provider 추가 방법:

```python
def _build_llm(self, api_key: str, model: str, temperature: float):
    if self.provider == "openai":
        ...
    elif self.provider == "anthropic":
        ...
    elif self.provider == "my_provider":           # 추가
        from langchain_myprovider import ChatMyProvider
        return ChatMyProvider(api_key=api_key, model=model, temperature=temperature)
    else:
        raise ValueError(f"Unsupported provider: '{self.provider}'.")
```

`adxp` provider는 LangChain을 사용하지 않고 직접 HTTP 요청을 보내는 `_judge_adxp()` 메서드를 사용합니다. 유사한 커스텀 엔드포인트가 필요하면 동일 패턴으로 구현합니다.

---

## 5. Streamlit UI 수정 가이드

### `app_streamlit/main.py` 전체 구조

```
main.py
├── _render_copy_table()         # 클립보드 복사 기능이 있는 테이블 렌더링 함수
├── Session State 초기화 (_DEFAULTS)
├── Auth helpers                 # 토큰 로그인/갱신
├── Sidebar                      # 설정 입력 (API URL, 토큰, LLM Judge)
├── Tab 1: Test Runner
│   ├── 시나리오 파일 목록 로드
│   ├── 시나리오 선택 및 실행 버튼
│   ├── 실시간 진행 현황 (on_step_update 콜백)
│   └── 결과 요약 테이블
└── Tab 2: Scenario Editor
    ├── 시나리오 파일 선택
    └── YAML/JSON 파일 편집기
```

### 콜백 패턴: 실시간 진행 상황 노출

`ScenarioEngine`은 각 단계 완료 시 `on_step_update` 콜백을 호출합니다.
Streamlit에서는 이 콜백으로 화면을 실시간 업데이트합니다.

```python
def on_step_update(step_result: StepResult):
    st.session_state.results.append(step_result)
    # st.rerun() 또는 placeholder 업데이트로 화면 갱신

engine = ScenarioEngine(
    base_url=st.session_state.base_url,
    admin_token=st.session_state.admin_token,
    ...
    on_step_update=on_step_update,
)
```

### 세션 상태 관리 패턴

```python
# 초기화 패턴 (main.py 상단에서 일괄 처리)
_DEFAULTS = {
    "base_url": os.getenv("BASE_URL", "..."),
    "running": False,
    ...
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# 값 접근
st.session_state.base_url
st.session_state["base_url"]  # 동일

# 실행 중 플래그
st.session_state.running = True   # 버튼 비활성화 등에 활용
```

**주의**: Streamlit은 매 인터랙션마다 스크립트 전체를 재실행합니다. 상태를 유지해야 하는 값은 반드시 `st.session_state`에 저장합니다.

---

## 6. 검증 방법

### Streamlit UI에서 단건 시나리오 실행

1. `streamlit run app_streamlit/main.py` 실행
2. Sidebar에서 BASE_URL, Admin Token 입력
3. Sidebar에서 LLM Judge 설정 입력 (Provider, API Key, Model)
4. Tab 1 (Test Runner) → 실행할 시나리오 선택
5. "실행" 버튼 클릭

### 단계별 PASS/FAIL 확인

실행 중 각 단계 결과가 실시간으로 표시됩니다:

| 단계 | 내용 |
|------|------|
| `create_prompt` | Prompt 등록 API 성공 여부 |
| `create_tool` | Tool 등록 API 성공 여부 |
| `create_graph` | Graph 생성 API 성공 여부 |
| `create_app` | App 생성 API 성공 여부 |
| `chat` | 채팅 API 응답 수신 여부 |
| `judge` | LLM Judge criteria 판정 결과 |
| `cleanup` | 리소스 삭제 (auto-delete=true인 경우) |

### LLM Judge 판정 결과 확인

- `PASS`: 모든 criteria 충족
- `FAIL`: 하나 이상의 criteria 미충족 (reason 필드에 이유 포함)
- `ERROR`: Judge 호출 자체 실패 (API Key 오류, 네트워크 문제 등)

---

## 7. 자주 쓰는 Claude Code 팁

### `/adxp-agent-e2e-test-helper` Skill 활용

```
/adxp-agent-e2e-test-helper
```

시나리오 파일 생성의 복잡한 절차(UUID 관리, placeholder 치환, 파일 연결)를 자동화합니다.
Skill 파일 위치: `.claude/skills/adxp-agent-e2e-test-helper/SKILL.md`

**언제 쓰면 좋은가**:
- 새 시나리오를 처음 만들 때
- EchoAPI export 파일(echoapi.json)에서 graph.json을 추출할 때
- UUID 변경이나 placeholder 치환이 복잡할 때

**사용 팁**:
- `.claude/skills/adxp-agent-e2e-test-helper/` 폴더에 `echoapi.json`을 넣으면 API 스펙에서 자동 추출 가능
- 파일이 없으면 "skip"이라고 입력해 수동 모드로 전환

### `.claude/streamlit_dev_workboard.md` 작업 기록

작업 계획과 진행 내용을 이 파일에 기록합니다.
세션이 바뀌어도 작업 맥락이 유지되어 Claude Code가 이전 작업을 이어받을 수 있습니다.

```
# 오늘 할 일
- [ ] 05_my_scenario 시나리오 추가
- [ ] Streamlit 결과 테이블 개선

# 진행 중
- [x] graph_my_scenario.json 작성 완료
```

### `CLAUDE.md` 역할

`CLAUDE.md`는 Claude Code의 행동 범위를 제한하는 프로젝트 지침입니다.

- 개발 범위: `app_streamlit/`, `core/`, `scenarios/`만 수정
- `app_cli/`는 수정하지 않도록 명시

새로운 규칙이 생기면 `CLAUDE.md`에 추가해 세션 간에 일관성을 유지합니다.

---

## 8. Playwright MCP로 브라우저 테스트 자동화

Claude Code에 Playwright MCP를 연결하면, **Claude Code가 직접 브라우저를 열어서** Streamlit 앱을 실행하고 결과를 확인한 뒤 코드를 수정하는 전체 사이클을 자동화할 수 있습니다.

```
Claude Code → 브라우저 열기 → Streamlit 앱 조작 → 에러 캡처 → 코드 수정 → 재검증
```

---

### MCP 설치 및 설정

#### 1. Node.js 확인

Playwright MCP는 `npx`로 실행하므로 Node.js(18+)가 필요합니다.

```bash
node --version   # v18 이상
npx --version
```

#### 2. Claude Code 설정 파일에 MCP 추가

`~/.claude/settings.json`을 열어 `mcpServers` 항목을 추가합니다.

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

> 파일이 없으면 새로 생성합니다. 기존 설정이 있으면 `mcpServers` 키만 추가합니다.

#### 3. 브라우저 설치 (최초 1회)

```bash
npx playwright install chromium
```

#### 4. Claude Code 재시작

설정 변경 후 Claude Code를 재시작해야 MCP가 활성화됩니다.

```bash
# Claude Code 재시작 후 MCP 연결 확인
/mcp
```

`playwright` 서버가 목록에 보이면 연결 성공입니다.

---

### 사용 방법: `/using-playwright` Skill

Playwright MCP가 연결된 상태에서 `/using-playwright` 명령어를 실행하면 됩니다.

```
/using-playwright
```

Claude Code가 아래 워크플로우를 자동으로 수행합니다.

---

### 자동화 워크플로우

#### Step 1: Streamlit 앱 접속

```
# Streamlit이 로컬에서 실행 중이어야 합니다
streamlit run app_streamlit/main.py
```

Claude Code가 `http://localhost:8501`에 접속해 현재 상태를 확인합니다.

#### Step 2: 설정 입력 및 로그인

Sidebar의 BASE_URL, Admin Token, LLM 설정을 입력합니다.
로그인 폼이 있으면 ID/PW를 Claude Code에 알려주면 자동으로 입력합니다.

#### Step 3: 시나리오 실행

실행 버튼 클릭 → 완료 대기 → 결과 화면 캡처까지 자동으로 수행합니다.

#### Step 4: 에러 수집 및 코드 수정

실행 결과에서 에러가 발견되면:

1. 화면 에러 메시지 수집 (`st.error()`, traceback 등)
2. 브라우저 콘솔 에러 수집
3. 에러 스크린샷 저장 (`.claude/skills/using-playwright/snapshots/`)
4. 관련 코드 파일 탐색 및 원인 분석
5. 수정 방안 제시 → 승인 후 코드 수정
6. 재실행으로 수정 결과 검증

---

### 실전 예시: 시나리오 추가 후 전체 검증

```
# 1. 새 시나리오 파일 작성 (Skill 활용)
/adxp-agent-e2e-test-helper

# 2. Streamlit 앱 실행
streamlit run app_streamlit/main.py   # 터미널에서 별도 실행

# 3. 브라우저로 앱 열어서 방금 만든 시나리오 실행하고 결과 확인해줘
/using-playwright
```

Claude Code가 브라우저를 열어 시나리오를 실행하고 PASS/FAIL 여부를 확인한 뒤,
FAIL이면 원인을 분석해 `scenario.yaml`이나 `graph.json`을 수정합니다.

---

### 에러 캡처 저장 위치

```
.claude/skills/using-playwright/snapshots/
└── error-capture.png    # 에러 발생 시 자동 저장
```

이 경로는 `.gitignore`에 포함되어 있어 커밋되지 않습니다.

---

### 자주 쓰는 Playwright MCP 도구 요약

| 도구 | 용도 |
|------|------|
| `browser_navigate` | URL로 페이지 이동 |
| `browser_snapshot` | 현재 화면 접근성 트리 캡처 (요소 ref 확인용) |
| `browser_click` | 버튼/링크 클릭 |
| `browser_fill_form` | 폼 필드 일괄 입력 |
| `browser_wait_for` | 특정 텍스트 나타날 때까지 대기 |
| `browser_take_screenshot` | 화면 스크린샷 저장 |
| `browser_console_messages` | 브라우저 콘솔 에러 수집 |

---

### 주의사항

- Playwright MCP는 로컬 브라우저를 제어하므로 **Streamlit 앱이 먼저 실행 중**이어야 합니다.
- ID/PW 같은 민감 정보는 Claude Code에 직접 전달하지 말고, 세션 중에만 사용합니다.
- `SSL_VERIFY=false` 환경에서는 브라우저가 인증서 경고를 표시할 수 있습니다.

---

### graph.json 트러블슈팅: query가 전달되지 않는 문제

Generator 노드의 `input_keys[name=query].keytable_id`가 비어있으면 사용자 질문이 LLM에 전달되지 않습니다.

```json
// input__basic 노드에서 keytable_id 확인
{ "name": "query", "keytable_id": "query_b153394d" }

// agent__generator 노드에 동일 값 설정
{ "name": "query", "keytable_id": "query_b153394d" }
```

`keytable_id` 형식: `{field_name}_{node_id}` (예: `query_b153394d`)
