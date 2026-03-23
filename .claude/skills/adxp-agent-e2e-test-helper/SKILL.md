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

`echoapi.json`이 있더라도, 사용자에게 아래 두 가지 옵션을 제시한다:

```
graph.json을 어떻게 생성하시겠어요?

A) echoapi.json에서 자동 추출
B) graph.json 파일을 직접 제공 (파일 경로 또는 내용 붙여넣기)
```

**옵션 A: echoapi.json에서 자동 추출**

`echoapi.json`을 읽어 **Graph 생성 API**의 request body 예시를 찾는다.

- **있으면** → 사용자에게:
  ```
  어떤 폴더의 어떤 이름(summary)로 테스트 생성하시겠습니까?
  예: agents_backend/graph_test_v2 중에서 이름: llm_parameter
  ```
  graph_test_v2의 llm_parameter 라고 사용자가 입력했을 때
  -> echoapi.json에서 summary:llm_parameter 인 것 중에서 tags:["A.XPlatform - agents_backend_api/agents_backend/graph_test_v2"] 인 것을 찾아서 읽어와서 requestBody 중 example을 json 파일로 생성
- **없으면** → 사용자에게:
  ```
  echoapi.json에서 해당 Graph 생성 API request body를 찾지 못했습니다.
  옵션 B(직접 제공)로 진행해주세요.
  ```

**옵션 B: graph.json 직접 제공**

사용자가 파일 경로 또는 JSON 내용을 직접 제공하면:
- 파일 경로인 경우: 해당 경로의 파일을 읽어 `scenarios/{폴더}/graph_<name>.json`으로 복사
- JSON 내용 붙여넣기인 경우: 입력받은 내용을 `scenarios/{폴더}/graph_<name>.json`으로 저장

시나리오 폴더명과 graph 이름을 사용자에게 확인 후 저장.

---

### Step 3: UUID 추출 및 연관 파일 생성

생성된 `graph.json`을 읽어 아래 필드 값을 확인한다.

| graph.json 필드 | 비어있지 않으면 | graph.json 처리 | scenario.yaml 반영 |
|------|----------------|-----------------|-------------------|
| `serving_name` | llm 치환 필요 | `@@llm_{node_name}@@`으로 수정 | `llms` 섹션에 `placeholder_in_graph` + `replace_to` 추가 |
| `prompt_id` | UUID 추출 | 수정 없음 (단, UUID 변경 요청 시 수정) | `prompts[].id` 에 UUID 추가 |
| `tool_ids` | UUID 추출 | 수정 없음 (단, UUID 변경 요청 시 수정) | `tools[].id` 에 UUID 추가 |
| `mcp_catalogs[].id` | UUID 추출 | 수정 없음 (단, UUID 변경 요청 시 수정) | `mcps[].id` 에 UUID 추가 |
| `repo_id` | UUID 추출 | 수정 없음 (단, UUID 변경 요청 시 수정) | `knowledges[].id` 에 UUID 추가 |

**3-1. LLM 플레이스홀더 치환 (graph.json 수정)**

`serving_name`이 감지되면 `@@llm_{node_name}@@` 형식으로 교체하고, graph.json을 업데이트한다.

- `node_name`은 해당 노드의 `name` 필드 사용 (예: `agent__generator_1`)
- 예: `"serving_name": "GIP/gpt-4.1"` → `"serving_name": "@@llm_agent__generator_1@@"`

**3-2. UUID 확인 및 변경 여부 결정**

`prompt_id`, `tool_ids`, `mcp_catalogs[].id`, `repo_id`의 UUID를 추출하여 사용자에게 알리고,
각 UUID를 유지할지 새로 생성할지 확인한다.

```
graph.json에서 감지된 UUID입니다. 변경이 필요한 항목이 있으면 알려주세요.

[Prompt]
- prompt_id: "6f772e24-4d0f-411d-a38e-645317a6802e"

[Tool]
- tool_ids[0]: "7d141228-4d0f-411d-a38e-645317a6802e"

[MCP]
- mcp_catalogs[0].id: "400a47a5-4d0f-411d-a38e-645317a6802e"

[Knowledge]
- repo_id: "557daeb4-4d0f-411d-a38e-645317a6802e"

변경할 항목이 없으면 "유지"라고 말씀해주세요.
```

사용자가 특정 UUID 변경을 요청하면:
1. 터미널에서 새 UUID 생성: `python3 -c "import uuid; print(uuid.uuid4())"`
2. 생성된 UUID로 graph.json의 해당 필드 값 수정
3. 새 UUID를 scenario.yaml에 반영

**3-3. 연관 JSON 파일 생성**

UUID가 확정되면 각 리소스에 대해 `{type}_{uuid}.json` 파일 생성이 필요한지 확인한다.
llm은 JSON 파일 생성 없이 scenario.yaml llms 섹션에만 추가.

`echoapi.json`에서 각 리소스 생성 API의 request body 예시를 찾아 옵션으로 제시하고, 없으면 직접 입력 요청.

```
아래 파일 생성이 필요합니다. 각각 어떤 값을 넣으시겠어요?
- prompt_6f772e24-4d0f-411d-a38e-645317a6802e.json  (prompt_id)    ← 해당되는 것만 표시
- tool_7d141228-4d0f-411d-a38e-645317a6802e.json    (tool_ids)     ← 해당되는 것만 표시
- mcp_400a47a5-4d0f-411d-a38e-645317a6802e.json     (mcp_catalogs) ← 해당되는 것만 표시
- know_557daeb4-4d0f-411d-a38e-645317a6802e.json    (repo_id)      ← 해당되는 것만 표시
```

사용자 입력을 받아 해당 JSON 파일들 생성.

---

### Step 4: scenario.yaml 만들기

**4-1. graph / app / llms / prompts 섹션 자동 구성**

- `graph` 섹션: `graph.json`의 내용 기반으로 채움
- `app.name`: graph name과 동일하게 설정
- `llms` 섹션: Step 3에서 치환된 `@@llm_{node_name}@@` 플레이스홀더를 기반으로 항목 구성. `placeholder_in_graph`는 치환된 key, `replace_to` 값은 원본 `serving_name` 값으로 채우되 사용자에게 확인 (환경마다 다를 수 있음)
- `prompts` / `tools` / `mcps` / `knowledges`: Step 3에서 생성된 JSON 파일이 있는 경우에만 섹션 추가. `id`는 Step 3에서 확정된 UUID (원본 또는 새로 생성), `json_path`는 `{type}_{uuid}.json` 형식 사용

모든 name 값에 `[QA]` 접두사 필수.

**4-2. 사용자에게 옵션 질문**

아래 항목들을 사용자에게 확인:

```
시나리오 옵션을 설정해주세요.

1. auto-delete (테스트 후 생성된 리소스를 자동 삭제할까요?)
   - graph: yes / no
   - app: yes / no
   - prompts: yes / no  ← prompts 섹션이 있을 때만
   - tools: yes / no     ← tools 섹션이 있을 때만
   - mcps: yes / no      ← mcps 섹션이 있을 때만

2. update-if-exists (아래 설명 참고)
   - graph: yes / no
   - prompts: yes / no   ← prompts 섹션이 있을 때만
   - tools: yes / no     ← tools 섹션이 있을 때만
   - mcps: yes / no      ← mcps 섹션이 있을 때만
   
```

**update-if-exists — 이미 리소스가 존재하는 경우 업데이트 할지 여부**

시나리오에는 리소스마다 **`id`**(긴 고유 번호, UUID)가 붙어 있다. 테스트를 돌리면 프로그램이 **“이 번호로, 옆에 적힌 JSON 파일 내용을 서버에 반영해 달라”**고 요청한다.

- **서버에 그 번호가 아직 없으면** → 새로 등록되고 끝.
- **서버에 그 번호로 이미 뭔가 있으면** (다른 사람이 만들었거나 예전 테스트가 남은 경우):
  - **`update-if-exists: true`** → **지금 폴더에 있는 JSON 내용으로 서버 쪽을 갱신**한다. (시나리오 파일을 고치면 다음 실행에 반영되고 싶을 때)
  - **`update-if-exists: false`** → **서버에 이미 있는 걸 그대로 둔다.** 폴더의 JSON만 수정해도 서버 데이터는 안 바뀐다. (남이 만든 리소스를 건드리지 않고 테스트만 하고 싶을 때)

**`id`를 비워 둔 경우**는 “번호 정해 주지 말고 새로 하나 만들어 달라”에 가깝고, 그때는 서버가 새 번호를 붙여 준다.

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
> - `graph`, `prompts`, `tool`, `mcp` 등에는 보통 **UUID 형식의 `id`**를 둔다. (서버에서 “이 번호로 리소스를 맞추겠다”는 뜻.)
> - `id`가 있으면 테스트 실행 시 **그 번호로 JSON 파일 내용을 서버에 등록·맞춤**하는 흐름으로 간다.
> - `app`은 **`id` 없이 이름(`name`)만** 쓴다. (그래프와 붙이는 앱이라 번호 고정 방식이 다름.)
> - **`id`가 없으면**: 리소스마다 새 번호를 쓰려면 아래로 UUID를 만들어 scenario.yaml에 넣는다. (`graph`와 `prompts` 등은 **서로 다른 번호**여야 한다.)
>   ```bash
>   python3 -c "import uuid; print(uuid.uuid4())"
>   ```
>   리소스 종류에 따라 `id` 없이 실행해도 서버가 **새 번호를 붙여 주는** 경우가 있다.

```yaml
scenario_name: "<시나리오 이름>"

graph:
  name: "[QA]<graph_name>"
  id: <uuid>                                # graph.json에서 사용할 UUID
  file_path: "./scenarios/<folder>/graph_<name>.json"
  auto-delete: true
  update-if-exists: false

app:
  name: "[QA]<app_name>"
  auto-delete: true

llms:                                       # graph JSON의 serving_name @@...@@ 플레이스홀더 치환 (LLM만 해당)
  - placeholder_in_graph: <placeholder_key> # 예: llm_agent__generator_1
    replace_to: "<serving_name>"            # 예: "GIP/gpt-4o"

prompts:                                    # prompt.json이 있는 경우만
  - name: "[QA]<prompt_name>"
    id: <uuid>                              # graph.json의 prompt_id 값과 동일한 UUID
    json_path: "./scenarios/<folder>/prompt_<uuid>.json"
    auto-delete: true
    update-if-exists: false

tools:                                      # tool.json이 있는 경우만
  - name: "<tool_name>"
    id: <uuid>                              # graph.json의 tool_ids 값과 동일한 UUID
    json_path: "./scenarios/<folder>/tool_<uuid>.json"
    auto-delete: false
    update-if-exists: false

mcps:                                       # mcp.json이 있는 경우만
  - name: "<mcp_name>"
    id: <uuid>                              # graph.json의 mcp_catalogs[].id 값과 동일한 UUID
    json_path: "./scenarios/<folder>/mcp_<uuid>.json"
    auto-delete: false
    update-if-exists: false

knowledges:                                 # knowledge.json이 있는 경우만
  - name: "<knowledge_name>"
    id: <uuid>                              # graph.json의 repo_id 값과 동일한 UUID
    placeholder_in_graph: "@@select_knowledge"
    auto-delete: false # 무조건 false
    update-if-exists: false #무조건 false

answer-judge:
  - questions: "<테스트 질문>"
    criteria:
      - "<판정 기준>"
```

### 리소스 처리 로직 (Prompts / Tools / MCPs 공통)
| 상황 | 동작 |
|------|------|
| id(UUID)로 검색 결과 없음 | Import API(POST)로 해당 UUID를 id로 신규 생성 |
| id(UUID)로 검색 결과 있음 + `update-if-exists: true` | PUT으로 업데이트 |
| id(UUID)로 검색 결과 있음 + `update-if-exists: false` | 기존 리소스 재사용 (업데이트 생략) |

---

### Placeholder `@@` 포함/제외 규칙

| 리소스 | scenario.yaml `placeholder_in_graph` | graph.json |
|--------|--------------------------------------|------------|
| **LLM** | `@@` **제외** (예: `llm_agent__generator_1`) | `@@llm_agent__generator_1@@` |
| **Knowledge** | `@@` **포함** (예: `@@select_knowledge@@`) | `@@select_knowledge@@` |

- LLM: scenario.yaml에 `@@` 없이 key만 쓰면, 엔진이 자동으로 `@@key@@` 형식으로 치환
- Knowledge: scenario.yaml과 graph.json 모두 `@@` 포함한 동일 문자열 사용

---

## 기존 시나리오 수정하기

1. 수정 대상 파일을 먼저 Read로 확인
2. 사용자가 변경할 내용을 명확히 파악한 뒤 수정
3. `auto-delete`, `update-if-exists` 설정이 의도에 맞는지 재확인
4. `answer-judge.criteria`가 변경된 동작을 반영하는지 확인

---

## graph.json 트러블슈팅

### Generator에 query가 전달되지 않는 문제

**증상**: Generator 노드가 응답을 생성하지만 사용자의 질문과 무관한 답변이 나오거나, "메시지가 비어있다"는 식의 응답이 나오는 경우.

**원인**: `agent__generator` 노드의 `input_keys` 중 `name: "query"`의 `keytable_id`가 비어있거나 잘못 연결되어 있을 때 발생.

**확인 방법**: graph.json에서 아래 두 노드를 비교한다.

```json
// ✅ input__basic 노드 — query의 keytable_id 원본
{
  "type": "input__basic",
  "data": {
    "input_keys": [
      { "name": "query", "keytable_id": "query_b153394d" }  // ← 이 값을
    ]
  }
}

// ❌ agent__generator 노드 — query의 keytable_id가 비어있으면 연결 끊김
{
  "type": "agent__generator",
  "data": {
    "input_keys": [
      { "name": "query", "keytable_id": "" }  // ← 여기에 동일한 값이 들어가야 함
    ]
  }
}
```

**수정**: `agent__generator`의 `input_keys[name=query].keytable_id` 값을 `input__basic`의 `query` keytable_id와 동일하게 설정.

```json
// ✅ 수정 후
{ "name": "query", "keytable_id": "query_b153394d" }
```

> `keytable_id`는 `{field_name}_{node_id}` 형식 (예: `query_b153394d`에서 `b153394d`는 input 노드의 id).
