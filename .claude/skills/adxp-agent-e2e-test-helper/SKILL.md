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
  Graph 생성 API의 request body 구조를 파악하기 위해 필요합니다.
  해당 파일을 .claude/skills/ 폴더에 넣어주시겠어요?
  ```
  파일이 추가되면 계속 진행.

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

### Step 3: 연관 파일 필요 여부 확인

생성된 `graph.json`을 읽어 아래 필드 값을 확인한다.

| 필드 | 비어있지 않으면 |
|------|----------------|
| `prompt_id` | `prompt.json` 생성 필요 |
| `tool_id` | `tool.json` 생성 필요 |
| `mcp_catalogs` | `mcp.json` 생성 필요 |

비어있지 않은 필드가 있으면 사용자에게 안내:

```
graph.json을 읽었습니다. 아래 파일 생성이 필요합니다:
- prompt.json (prompt_id 필드 감지)
- tool.json   (tool_id 필드 감지)      ← 해당되는 것만 표시
- mcp.json    (mcp_catalogs 필드 감지)

각각 어떤 값을 넣으시겠어요?
```

`echoapi.json`에서 각각의 생성 API request body 예시를 찾아 옵션으로 제시하고, 없으면 직접 입력 요청.

사용자 입력을 받아 해당 JSON 파일들 생성.

---

### Step 4: scenario.yaml 만들기

**4-1. graph / app / prompts 섹션 자동 구성**

- `graph` 섹션: `graph.json`의 내용 기반으로 채움
- `app.name`: graph name과 동일하게 설정
- `prompts`: `prompt.json`이 생성된 경우에만 섹션 추가

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

```yaml
scenario_name: "<시나리오 이름>"

graph:
  id: "<uuid>"                              # 필수: Import API에 사용할 고정 UUID
  name: "[QA]<graph_name>"
  file_path: "./scenarios/<folder>/graph_<name>.json"
  auto-delete: true
  update-if-exists: false

app:                                        # id 없음 — Create API만 사용
  name: "[QA]<app_name>"
  auto-delete: true

prompts:                                    # prompt.json이 있는 경우만
  - id: "<uuid>"                            # 필수: Import API에 사용할 고정 UUID
    name: "[QA]<prompt_name>"
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

### Import API 동작 규칙
| 상황 | 결과 |
|------|------|
| id 미존재 | 신규 생성 (`detail: "Created"`) |
| id 존재 + 내용 일치 | 검증 통과 (`detail: "Validated"`) |
| id 존재 + 내용 불일치 + `update-if-exists: true` | PUT으로 업데이트 |
| id 존재 + 내용 불일치 + `update-if-exists: false` | skip (기존 ID 재사용) |

---

## 기존 시나리오 수정하기

1. 수정 대상 파일을 먼저 Read로 확인
2. 사용자가 변경할 내용을 명확히 파악한 뒤 수정
3. `auto-delete`, `update-if-exists` 설정이 의도에 맞는지 재확인
4. `answer-judge.criteria`가 변경된 동작을 반영하는지 확인
