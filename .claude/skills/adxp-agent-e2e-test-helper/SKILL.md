---
name: adxp-agent-e2e-test-helper
description: "Use for creating or modifying adxp-agent E2E test scenario files. Triggers: scenario yaml, scenario json, e2e test scenario, graph json, prompt json, test case, adxp test, agent builder test, scenario 만들기, 시나리오 생성, 시나리오 수정"
---

# adxp-agent E2E Test Helper

adxp-agent E2E 테스트를 위한 **시나리오 YAML** 및 **JSON 페이로드 파일**을 생성하거나 수정하는 skill입니다.

---

## 파일 구조

```
scenarios/
└── 01_simple/
    ├── scenario.yaml
    ├── graph_<name>.json
    ├── prompt_<name>.json      # 필요한 경우
    ├── tool_<name>.json        # 필요한 경우
    └── mcp_<name>.json         # 필요한 경우
```

폴더 이름은 `{숫자두자리}_{설명}` 형식. (예: `01_simple`, `02_multi_prompt`)

---

## 새 시나리오 만들기 — 단계별 워크플로우

### Step 1: echoapi.json 확인

skills 폴더(`.claude/skills/adxp-agent-e2e-test-helper`) 안에 `echoapi.json` 이 있는지 확인한다.

- **있으면** → Step 2로 진행
- **없으면** → 사용자에게 안내:
  ```
  .claude/skills/ 폴더에 echoapi.json (Postman/EchoAPI export 파일)이 없습니다.
  echoapi.json 파일이 있으면 .claude/skills/ 폴더에 넣어주시고, 없으면 skip이라고 해주세요.
  ```
  파일이 추가되거나 skip이라고 사용자가 입력하면 계속 진행.

---

### Step 2: graph.json 만들기

`echoapi.json`을 읽어 **Graph 생성 API**의 request body 예시를 찾는다.

- **있으면** → 사용자에게:
  ```
  echoapi.json가 있습니다. 어떤 폴더의 어떤 이름(summary)로 테스트 생성하시겠습니까?
  예:agents_backend/graph_test_v2 중에서 이름: llm_parameter 
  ```
  graph_test_v2의 llm_parameter 라고 사용자가 입력했을 때
  -> ehoapi.json에서 summary:llm_parameter 인 것 중에서 tags:["A.XPlatform - agents_backend_api/agents_backend/graph_test_v2"] 이고  인것을 찾아서 읽어와서 requestBody 중 example을 json 파일로 생성
- **없으면** → 사용자에게:
  ```
  echoapi.json에서 Graph 생성 API request body를 찾지 못했습니다.
  Graph 생성 API의 request body를 직접 입력해주세요.
  ```
  사용자 입력을 받아 `scenarios/{폴더}/graph_<name>.json` 파일 생성.

---

### Step 3: 연관 파일 생성 및 graph.json 플레이스홀더 치환

생성된 `graph.json`을 읽어 아래 필드 값을 확인한다.

| graph.json 필드 | 비어있지 않으면 | 생성할 파일 |
|------|----------------|------------|
| `serving_name` | llm 치환 필요 | JSON 파일 없음 (scenario.yaml llms 섹션에만 추가) |
| `prompt_id` | `prompt.json` 생성 필요 | `prompt_{identifier}.json` |
| `tool_ids` | `tool.json` 생성 필요 | `tool_{identifier}.json` |
| `mcp_catalogs[].id` | `mcp.json` 생성 필요 | `mcp_{identifier}.json` |
| `repo_id` | `knowledge.json` 생성 필요 | `know_{identifier}.json` |

**3-1. 플레이스홀더 치환**

감지된 각 값을 `@@{identifier}@@` 형식으로 교체하고, graph.json을 업데이트한다.

- `identifier` 규칙: 해당 노드의 `name` 필드(예: `agent__generator_1`)를 기반으로 자동 생성
  - prompt: `prompt_{node_name}` → 예: `@@prompt_agent__generator_1@@`
  - tool: `tool_{node_name}_{idx}` (tool_ids는 배열이므로 idx 포함)
  - mcp: `mcp_{catalog_name}` (mcp_catalogs의 name 필드 사용)
  - knowledge: `know_{node_name}`
  - llm serving_name: `llm_{node_name}` → 예: `@@llm_agent__generator_1@@`

사용자에게 변경 내역을 아래 형식으로 알린다:

```
graph.json 플레이스홀더 치환 완료:

[LLM]
- "serving_name": "GIP/gpt-4.1"  →  "serving_name": "@@llm_agent__generator_1@@"

[Prompt]
- "prompt_id": "6f772e24-..."  →  "prompt_id": "@@prompt_agent__generator_1@@"

[Tool]
- "tool_ids": ["7d141228-..."]  →  "tool_ids": ["@@tool_agent__generator_1_0@@"]

[MCP]
- mcp_catalogs[0].id: "400a47a5-..."  →  "@@mcp_takeoff_news@@"

[Knowledge]
- "repo_id": "557daeb4-..."  →  "repo_id": "@@know_agent__retriever_1@@"
```

**3-2. 연관 JSON 파일 생성**

llm은 JSON 파일 생성 없이 scenario.yaml llms 섹션에 추가할 정보만 메모.
나머지(prompt, tool, mcp, knowledge)는 각 JSON 파일을 생성해야 한다.

`echoapi.json`에서 각 리소스 생성 API의 request body 예시를 찾아 옵션으로 제시하고, 없으면 직접 입력 요청.

```
아래 파일 생성이 필요합니다. 각각 어떤 값을 넣으시겠어요?
- prompt_agent__generator_1.json  (prompt_id 감지)   ← 해당되는 것만 표시
- tool_agent__generator_1_0.json  (tool_ids 감지)    ← 해당되는 것만 표시
- mcp_takeoff_news.json           (mcp_catalogs 감지) ← 해당되는 것만 표시
- know_agent__retriever_1.json    (repo_id 감지)      ← 해당되는 것만 표시
```

사용자 입력을 받아 해당 JSON 파일들 생성.

---

### Step 4: scenario.yaml 만들기

**4-1. graph / app / llm / prompts 섹션 자동 구성**

- `graph` 섹션: `graph.json`의 내용 기반으로 채움
- `app.name`: graph name과 동일하게 설정
- `llms` 섹션: Step 3에서 치환된 `@@llm_...@@` 플레이스홀더를 기반으로 항목 구성. `replace_to` 값은 원본 `serving_name` 값으로 채우되 사용자에게 확인 (환경마다 다를 수 있음)
- `prompts` / `tools` / `mcps` / `knowledges`: Step 3에서 생성된 JSON 파일이 있는 경우에만 섹션 추가. `placeholder_in_graph`는 Step 3에서 결정된 identifier 사용

모든 name 값에 `[QA]` 접두사 필수.

**4-2. 사용자에게 옵션 질문**

아래 항목들을 사용자에게 확인:

```
시나리오 옵션을 설정해주세요.

1. auto-delete (테스트 후 생성된 리소스를 자동 삭제할까요?)
   - graph: yes / no
   - app: yes / no
   - prompts: yes / no  ← prompt.json이 있는 경우만

2. update-if-exists (동일한 이름의 리소스가 있고 body가 다를 경우 업데이트할까요?)
   - graph: yes / no
   - prompts: yes / no  ← prompt.json이 있는 경우만
```

**4-3. answer-judge 섹션 질문**

```
answer-judge 내용을 알려주세요.

1. questions: 테스트에 사용할 질문들을 입력해주세요. (예: 안녕, 날씨 알려줘)
2. criteria: 응답 판정 기준을 입력해주세요. (예: 인사말에 적절히 대답해야 함)
   ※ "HTTP Status 200" 기준은 자동으로 추가됩니다.
```

사용자 입력을 받아 `scenario.yaml` 생성.

---

## 시나리오 YAML 구조 (참고)

> **[중요] id 필드 규칙**
> - `graph`, `prompts`, `tool`, `mcp` 섹션에는 반드시 UUID 형식의 `id` 필드를 지정해야 합니다.
> - `id`가 있으면 Import API를 사용하여 해당 UUID로 리소스를 생성/검증합니다.
> - `app`은 id 필드 없이 name만 지정합니다 (Import API 미사용).
> - **`id`가 없는 섹션을 발견하면**: 터미널에서 UUID4를 생성하여 scenario.yaml에 추가한 뒤 진행한다.
>   ```bash
>   python3 -c "import uuid; print(uuid.uuid4())"
>   ```
>   graph, prompts 각각에 대해 UUID를 별도로 생성한다.

```yaml
scenario_name: "<시나리오 이름>"

graph:
  name: "[QA]<graph_name>"
  file_path: "./scenarios/<folder>/graph_<name>.json"
  auto-delete: true
  update-if-exists: false

app:
  name: "[QA]<app_name>"
  auto-delete: true

llm:                                        # graph JSON의 @@...@@ 플레이스홀더 직접 치환
  - placeholder_in_graph: <placeholder_key>
    replace_to: "<serving_name>"            # 예: "GIP/gpt-4o"

prompts:                                    # prompt.json이 있는 경우만
  - name: "[QA]<prompt_name>"
    placeholder_in_graph: <placeholder_key>
    json_path: "./scenarios/<folder>/prompt_<name>.json"
    auto-delete: true
    update-if-exists: false

answer-judge:
  questions:
    - "<테스트 질문>"
  criteria:
    - "<판정 기준>"
    - "HTTP Status 200"
```

### 리소스 처리 로직 (Prompts / Tools / MCPs 공통)
| 상황 | 동작 |
|------|------|
| GET 검색 결과 없음 | POST로 신규 생성 |
| GET 검색 결과 있음 + `update-if-exists: true` | PUT으로 업데이트 |
| GET 검색 결과 있음 + `update-if-exists: false` | 기존 리소스 재사용 (업데이트 생략) |

---

## 기존 시나리오 수정하기

1. 수정 대상 파일을 먼저 Read로 확인
2. 사용자가 변경할 내용을 명확히 파악한 뒤 수정
3. `auto-delete`, `update-if-exists` 설정이 의도에 맞는지 재확인
4. `answer-judge.criteria`가 변경된 동작을 반영하는지 확인
