---
name: using-playwright
description: "Use for QA workflow: login to Streamlit app, run a test, and capture error messages using Playwright MCP tools. Triggers: playwright, 로그인, 실행, 에러 확인, 브라우저 테스트, app 실행, streamlit 테스트, e2e, QA 실행, 앱 열어서"
---

# Playwright QA 워크플로우

Streamlit 앱에 로그인하고, 기능을 실행하고, 화면의 에러 메시지를 수집하는 skill입니다.

---

## 워크플로우 개요

```
Step 1: Streamlit 앱 접속 및 현재 상태 확인
    ↓
Step 2: 로그인 (ID/PW 폼 입력)
    ↓
Step 3: 실행 (버튼 클릭)
    ↓
Step 4: 에러 메시지 수집 및 정리
```

---

## Step 1: 앱 접속

```
browser_navigate → url: "http://localhost:8501"
browser_snapshot → 현재 페이지 상태 확인
```

- 로그인 폼이 보이면 → Step 2
- 이미 로그인된 상태면 → Step 3
- 앱이 로드 중이면 → `browser_wait_for` 로 "로딩" 사라질 때까지 대기

---

## Step 2: 로그인

```
browser_snapshot → ID, PW 입력창 ref 확인
browser_fill_form → fields:
  - { name: "아이디", type: "textbox", ref: "<id_ref>", value: "<ID>" }
  - { name: "비밀번호", type: "textbox", ref: "<pw_ref>", value: "<PW>" }
browser_click → 로그인 버튼 ref
browser_wait_for → 로그인 완료 후 나타나는 텍스트 또는 화면 변화 대기
browser_snapshot → 로그인 성공 여부 확인
```

**주의:**
- ID/PW는 사용자에게 직접 물어볼 것. 하드코딩 금지.
- 로그인 실패 메시지가 보이면 사용자에게 알리고 중단.

---

## Step 3: 실행

```
browser_snapshot → 실행 버튼 ref 확인
browser_click → 실행 버튼 ref, element: "실행 버튼"
browser_wait_for → 실행 완료 신호 대기
  - 완료 텍스트 나타남 (예: "완료", "Done", "Success")
  - 또는 로딩 스피너 사라짐: browser_wait_for → textGone: "..."
browser_snapshot → 실행 후 화면 상태 확인
```

**실행 완료 판단 기준 (우선순위):**
1. 성공 메시지 텍스트 나타남
2. 에러 메시지 텍스트 나타남
3. 스피너/로딩 표시 사라짐

---

## Step 4: 에러 메시지 수집

실행 후 화면에서 에러 여부를 확인한다.

### 4-1. 화면 스냅샷으로 에러 텍스트 확인

```
browser_snapshot → 전체 페이지 접근성 트리에서 에러 관련 텍스트 탐색
```

Streamlit 에러 표시 패턴:
- `st.error()` → 빨간 박스 "Error: ..."
- `st.exception()` → 스택 트레이스 포함 에러 박스
- `st.warning()` → 노란 박스 경고
- Python traceback 텍스트 (Error, Traceback, Exception 등)

### 4-2. 콘솔 에러 확인

```
browser_console_messages → level: "error"
```

### 4-3. 스크린샷 저장 (에러 상태 기록)

```
browser_take_screenshot → type: "png", filename: "error-capture.png"
```

### 4-4. 에러 정리 및 보고

수집한 에러 정보를 아래 형식으로 정리해서 사용자에게 보여줄 것:

```
## 에러 발견

**화면 에러 메시지:**
<snapshot/screenshot에서 발견한 에러 텍스트>

**콘솔 에러:**
<console_messages 결과>

**에러 캡처:** error-capture.png 저장됨
```

---

## 이후 단계 (Claude Code)

Playwright 작업(Step 1-4)이 완료된 후, 다음 작업은 코드 분석으로 이어진다:

```
→ 에러 메시지 기반으로 관련 코드 파일 탐색 (Grep, Read)
→ API 스펙 확인 (필요시)
→ 문제 원인 분석 후 사용자에게 해결 방안 제시
→ 사용자 피드백 반영하여 코드 수정
→ 사용자 승인 후 git commit
```

### API 스펙 확인 방법

에러가 API request/response 구조 문제인 경우 다음 순서로 확인한다:

**1. Swagger UI 먼저 확인**
```
WebFetch → url: "https://aip.sktai.io/api/v1/agent/openapi.json"
           prompt: "해당 엔드포인트의 request body와 response 스키마 알려줘"
```

**2. Swagger에서 스키마가 비어있거나 불완전한 경우 → echoapi.json 확인**

`.claude/skills/adxp-agent-e2e-test-helper/echoapi.json` 파일에 실제 요청/응답 예시가 있다.

```python
# 특정 엔드포인트의 request body 예시 확인
python3 -c "
import json
with open('.claude/skills/adxp-agent-e2e-test-helper/echoapi.json') as f:
    data = json.load(f)
for path, methods in data.get('paths', {}).items():
    if '<엔드포인트 키워드>' in path:
        for method, spec in methods.items():
            rb = spec.get('requestBody', {}).get('content', {})
            for ct, cs in rb.items():
                print(cs.get('example', ''))
"
```

**Post-response 스크립트에서 응답 구조 파악:**
- echoapi.json의 각 API 항목에 `x-echoapi-postresponse` 또는 post-response 스크립트에 JSONPath 표현식이 있으면 응답 구조를 역으로 추론할 수 있다.
- 예: `$.data.app_id` → 응답이 `{"data": {"app_id": "..."}}`임을 의미

---

## 자주 쓰는 대기 패턴

| 상황 | 도구 |
|------|------|
| 특정 텍스트 나타날 때까지 | `browser_wait_for → text: "..."` |
| 로딩 사라질 때까지 | `browser_wait_for → textGone: "Loading"` |
| 일정 시간 대기 | `browser_wait_for → time: 3` |

---

## 멈춰야 하는 경우

- 로그인 실패 → 사용자에게 ID/PW 확인 요청
- 앱이 로드되지 않음 → Streamlit 서버 실행 여부 확인 요청
- 실행 버튼을 찾을 수 없음 → snapshot 결과 사용자에게 공유 후 확인 요청
