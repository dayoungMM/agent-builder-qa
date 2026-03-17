# CLI Dev Workboard

## 1. High-level Milestones

- [ ] CLI MVP 완성 (로컬에서 단건/전체 시나리오 실행 및 결과/exit code 정상 동작)
- [ ] CronJob/K8s 환경에서 주기 실행 검증 (환경 변수 기반 설정 및 시나리오 선택)
- [ ] CI 파이프라인(GitHub Actions 등)에 통합하여 PR 단위 자동 E2E 테스트

## 2. Implementation TODOs

### 2.1 Config & Environment Management

- [ ] `LLM_API_KEY`, `BASE_URL`, `ADMIN_TOKEN` 등 필수 환경 변수 목록 정리 및 기본값/필수 여부 정의
- [ ] CLI 실행 시 환경 변수 로딩 유틸리티 구현 (`core` 또는 `app_cli` 내 헬퍼 모듈)
- [ ] LLM 판정용 모델명, temperature 등 설정을 환경 변수 또는 설정 파일로부터 읽어오는 로직 구현
- [ ] 환경 변수 검증 및 누락 시 친절한 에러 메시지/exit code 정책 정의

### 2.2 Scenario Discovery & Selection

- [ ] 기본 시나리오 루트 디렉토리(`./scenarios`) 상수 정의 및 설정으로 오버라이드 가능하게 하기
- [ ] 시나리오 디렉토리 구조 스캔 로직 구현 (예: `01_simple_chat/scenario.yaml` 패턴 탐색)
- [ ] 단건 실행 플래그 `--scenario <dir_name>` 처리 (해당 디렉토리만 실행)
- [ ] 전체 실행 플래그 `--all` 처리 (모든 시나리오 디렉토리를 순차 실행)
- [ ] K8s CronJob용 `SCENARIO` 환경 변수(`"all"` 또는 특정 디렉토리명)와 CLI 플래그 간 우선순위/매핑 규칙 정의
- [ ] 잘못된 시나리오 이름/경로 입력 시 에러 메시지 및 exit code 처리 정의

### 2.3 CLI Interface Design

- [ ] `app_cli/main.py`에서 `argparse` 또는 동등한 라이브러리로 CLI 인자 파서 스켈레톤 구현
- [ ] 지원 플래그 정의: `--scenario`, `--all`, `--scenario-root`, `--dry-run`(필요 시) 등
- [ ] `-h` / `--help` 출력에 사용 예시 포함 (단건 실행/전체 실행, K8s/CI 예시)
- [ ] 인자와 환경 변수 간 우선순위 규칙 정의 (`--scenario` vs `SCENARIO` 등)

### 2.4 Scenario Pipeline Integration

- [ ] `core/models.py` 기반으로 시나리오 YAML 구조를 로드/검증하는 헬퍼 함수 구현 되어있는지 확인하기
- [ ] `core/engine.py`의 Scenario Pipeline을 단일 시나리오 단위로 호출하는 함수 정의되어있는지 확인하기
- [ ] Prompt → Graph → App → Cleanup 각 단계별 실행 결과/예외를 캡처하고 상태를 반환하는 인터페이스 설계
- [ ] `app_cli/main.py`에서 다수의 시나리오를 순차 실행하면서 개별/전체 결과를 집계하는 루프 구현
- [ ] 실행 중단/예외 발생 시 남은 시나리오 처리 정책 정의(즉시 중단 vs 나머지 계속 실행)

### 2.5 Logging, Reporting & Exit Code

- [ ] stdout에 출력할 기본 로그 포맷 설계 (시나리오명, 단계, 상태, 소요 시간 등)
- [ ] 각 시나리오에 대해 최종 PASS/FAIL 및 LLM 판정 사유를 한 줄 또는 블록 형태로 출력하는 포맷 정의
- [ ] 전체 실행 결과 요약 출력 (총 시나리오 수, 성공/실패 개수, 실패 목록)
- [ ] 하나 이상 실패 시 프로세스 exit code `1`, 전부 성공 시 exit code `0` 반환 구현
- [ ] 예외/예기치 못한 에러 발생 시 로그 및 exit code 정책 정의 (예: 포맷팅된 에러 메시지 후 `1` 반환)

### 2.6 K8s CronJob / CI Integration

- [ ] PRD에 제시된 CronJob 스펙을 기준으로 실제 필요한 `args`/`env` 목록을 정리하고 주석으로 문서화
- [ ] K8s 환경에서 `SCENARIO`, `LLM_API_KEY`, `BASE_URL` 등 환경 변수로 설정 주입하는 가이드 작성
- [ ] GitHub Actions 등 CI에서 `python app_cli/main.py --all` 형태로 호출하는 예시 워크플로 정의
- [ ] CronJob/CI 환경에서의 로그 수집/보관 전략(예: stdout 기반) 메모

## 3. Open Questions / Follow-ups

- [ ] LLM Judge 설정(모델명, temperature 등)을 CLI에서 어느 정도까지 오버라이드 가능하게 할지 범위 정의 필요
- [ ] Scenario 실패 시 재시도 전략을 CLI 레벨에서 지원할지 여부 (예: `--retry-failed` 옵션)
- [ ] Slack/Teams Webhook 알림과 같은 향후 확장 기능을 CLI에서도 직접 제공할지, 별도 컴포넌트로 둘지 결정 필요