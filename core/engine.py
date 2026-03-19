from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import httpx
import yaml

from core.judge import LLMJudge
from core.models import (
    AnswerJudge,
    AppConfig,
    GraphConfig,
    JudgeStatus,
    PromptConfig,
    Scenario,
    ScenarioResult,
    StepResult,
    StepStatus,
)


class StreamError(Exception):
    """SSE 스트림 내 에러 이벤트 감지 시 발생."""
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


def load_scenario_from_file(path: Path) -> Scenario:
    """Load a Scenario model from a YAML file."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario.model_validate(data)


def discover_scenario_files(root: Path) -> List[Path]:
    """Discover scenario.yaml files under the given root directory."""
    if not root.exists():
        return []
    candidates: List[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            scenario_file = child / "scenario.yaml"
            if scenario_file.exists():
                candidates.append(scenario_file)
    return candidates


def run_scenario(scenario: Scenario) -> ScenarioResult:
    """Execute a single scenario and return a ScenarioResult.

    This is a minimal placeholder implementation for the CLI MVP:
    it does not yet call real APIs, but wires the result structure.
    """
    result = ScenarioResult(scenario_name=scenario.scenario_name)
    # Placeholder single step; real implementation will expand this.
    result.steps.append(
        StepResult(
            step="SCENARIO_LOADED",
            status=StepStatus.PASS,
            request=None,
            response=None,
            elapsed_time=None,
            judge_result=None,
            error=None,
        )
    )
    result.compute_final_status()
    return result


def run_scenarios_from_root(
    root: Path,
    scenario_names: Iterable[str] | None = None,
) -> List[ScenarioResult]:
    """Load and run scenarios under the given root.

    - root: directory containing per-scenario subdirectories.
    - scenario_names: if provided, only scenarios whose directory name is in this list are run.
    """
    scenario_files = discover_scenario_files(root)
    if scenario_names is not None:
        names = set(scenario_names)
        scenario_files = [
            p for p in scenario_files if p.parent.name in names  # type: ignore[union-attr]
        ]

    results: List[ScenarioResult] = []
    for path in scenario_files:
        try:
            scenario = load_scenario_from_file(path)
        except Exception as e:
            traceback.print_exc()
            # If loading fails, surface as an ERROR result.
            sr = ScenarioResult(scenario_name=path.parent.name)
            sr.steps.append(
                StepResult(
                    step="LOAD_SCENARIO",
                    status=StepStatus.ERROR,
                    error=f"Failed to load scenario: {e}",
                )
            )
            sr.compute_final_status()
            results.append(sr)
            continue

        sr = run_scenario(scenario)
        results.append(sr)

    return results


def exit_code_for_results(results: Iterable[ScenarioResult]) -> int:
    """Compute process exit code from scenario results."""
    has_failure = False
    for r in results:
        status = r.compute_final_status()
        if status in (StepStatus.FAIL, StepStatus.ERROR):
            has_failure = True
    return 1 if has_failure else 0


def print_results(results: Iterable[ScenarioResult], stream=None) -> None:
    """Print a human-readable summary of scenario results to the given stream."""
    if stream is None:
        stream = sys.stdout

    stream.write("=== Scenario Results ===\n")
    for r in results:
        status = r.compute_final_status().value
        stream.write(f"- {r.scenario_name}: {status}\n")
        for step in r.steps:
            stream.write(f"  * [{step.status.value}] {step.step}\n")
            if step.error:
                stream.write(f"    - error: {step.error}\n")
    stream.flush()


# ──────────────────────────────────────────────────────────────────────────────
# ScenarioEngine: Streamlit/CLI 공용 실제 API 호출 엔진
#
# API 엔드포인트 (adxp-endpoint 기준)
#   Prompt : POST   /api/v1/agent/inference-prompts
#            POST   /api/v1/agent/inference-prompts/import?prompt_uuid={id}
#            PUT    /api/v1/agent/inference-prompts/{id}
#            DELETE /api/v1/agent/inference-prompts/{id}
#   Graph  : POST   /api/v1/agent/agents/graphs
#            POST   /api/v1/agent/agents/graphs/import?agent_id={id}
#            PUT    /api/v1/agent/agents/graphs/{id}
#            POST   /api/v1/agent/agents/graphs/hard-delete?agent_id={id}
#            POST   /api/v1/agent/agents/graphs/stream
#   App    : POST   /api/v1/agent/agents/apps
#            POST   /api/v1/agent/agents/apps/hard-delete?app_id={id}
#            POST   /api/v1/agent_gateway/{app_id}/stream
# ──────────────────────────────────────────────────────────────────────────────

class ScenarioEngine:
    def __init__(
        self,
        base_url: str,
        admin_token: str,
        judge: LLMJudge,
        on_step_update: Optional[Callable[[str, str], None]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.judge = judge
        self.on_step_update = on_step_update or (lambda msg, level: None)
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=120.0,
        )

    def _notify(self, message: str, level: str = "info"):
        self.on_step_update(message, level)

    # ── 공통 유틸 ──────────────────────────────────

    @staticmethod
    def _resolve_path(path_str: str, scenario_dir: str) -> str:
        """상대 경로를 실제 파일 경로로 변환합니다. CWD → 시나리오 디렉토리 순으로 탐색."""
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return str(p)
        cwd_path = Path.cwd() / p
        if cwd_path.exists():
            return str(cwd_path)
        scenario_path = Path(scenario_dir) / p
        if scenario_path.exists():
            return str(scenario_path)
        return str(cwd_path)

    @staticmethod
    def _substitute_variables(content: str, variables: dict[str, str]) -> str:
        """{variable_name} 플레이스홀더를 실제 값으로 치환합니다."""
        for key, value in variables.items():
            content = content.replace(f"{{{key}}}", value)
        return content

    @staticmethod
    def _parse_stream_line(line: str) -> str:
        """SSE 스트림 한 줄에서 텍스트를 추출합니다."""
        raw = line.removeprefix("data:").strip()
        if not raw or raw == "[DONE]":
            return ""
        try:
            data = json.loads(raw)
            for key_path in [
                ["final_result"],
                ["content"],
                ["text"],
                ["delta", "content"],
                ["choices", 0, "delta", "content"],
                ["message", "content"],
            ]:
                try:
                    val = data
                    for k in key_path:
                        val = val[k]
                    if isinstance(val, str):
                        return val
                except (KeyError, IndexError, TypeError):
                    continue
        except json.JSONDecodeError:
            return raw
        return ""

    def _call_stream(self, url: str, payload: dict, headers: dict = None) -> tuple[str, int, str]:
        """스트림 API 호출 → (전체 응답 텍스트, HTTP 상태 코드, 원본 SSE 텍스트) 반환.

        SSE 스트림에서 `event: error` 또는 data에 "error" 키가 포함된 경우
        StreamError를 발생시킵니다.
        """
        full_response = ""
        raw_lines: list[str] = []
        status_code = 0
        current_event = "data"
        stream_error: str | None = None

        with self.client.stream("POST", url, json=payload, headers=headers or {}) as resp:
            status_code = resp.status_code
            resp.raise_for_status()
            for line in resp.iter_lines():
                raw_lines.append(line)
                if line.startswith("event:"):
                    current_event = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    raw = line.removeprefix("data:").strip()
                    if current_event == "error":
                        try:
                            data = json.loads(raw)
                            stream_error = data.get("message", raw)
                        except json.JSONDecodeError:
                            stream_error = raw
                    else:
                        try:
                            data = json.loads(raw)
                            if isinstance(data, dict) and "error" in data and not stream_error:
                                stream_error = data["error"]
                        except (json.JSONDecodeError, TypeError):
                            pass
                        full_response += self._parse_stream_line(line)
                    current_event = "data"

        raw_text = "\n".join(raw_lines)
        if stream_error:
            raise StreamError(stream_error, raw_response=raw_text)
        return full_response, status_code, raw_text

    def _get_app_apikey(self, app_id: str) -> str:
        """GET /api/v1/agent/agents/apps/{app_id}/apikeys 로 API key 조회."""
        resp = self.client.get(
            f"{self.base_url}/api/v1/agent/agents/apps/{app_id}/apikeys"
        )
        resp.raise_for_status()
        data = resp.json()
        items = (
            data.get("items")
            or data.get("data")
            or data.get("results")
            or (data if isinstance(data, list) else [])
        )
        if not items:
            raise ValueError(f"No API keys found for app {app_id}")
        item = items[0]
        if isinstance(item, str):
            return item
        key = item.get("key") or item.get("api_key") or item.get("apikey")
        if not key:
            raise ValueError(f"API key field not found in response: {item}")
        return key

    def _find_app_by_name(self, name: str) -> Optional[dict]:
        """GET /api/v1/agent/agents/apps?name={name} 으로 App을 검색합니다."""
        resp = self.client.get(
            f"{self.base_url}/api/v1/agent/agents/apps", params={"name": name}
        )
        resp.raise_for_status()
        data = resp.json()
        items = (
            data.get("items")
            or data.get("data")
            or data.get("results")
            or (data if isinstance(data, list) else [])
        )
        for item in items:
            if item.get("name") == name:
                return item
        return None

    def _import_resource(
        self,
        import_url: str,
        id_param: str,
        resource_id: str,
        payload: dict,
        update_if_exists: bool,
        put_url: str,
    ) -> str:
        """Import API 공통 로직.
        - Created / Validated → resource_id 반환
        - 충돌(HTTP 에러): update_if_exists=True → PUT 업데이트, False → skip
        """
        def _extract_response_message(response: httpx.Response) -> str:
            # Try to extract a friendly message from common JSON shapes.
            try:
                data = response.json()
                if isinstance(data, dict):
                    return (
                        data.get("detail")
                        or data.get("message")
                        or data.get("error")
                        or str(data)
                    )
            except Exception:
                pass
            # Fallback to raw text (may be empty).
            text = (response.text or "").strip()
            return text if text else response.reason_phrase or ""

        try:
            resp = self.client.post(import_url, params={id_param: resource_id}, json=payload)
            resp.raise_for_status()
            detail = resp.json().get("detail", "")
            self._notify(f"  → Import {detail}: {resource_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 405 and update_if_exists:
                self._notify(f"  → 충돌, PUT 업데이트: {resource_id}", "warning")
                put_resp = self.client.put(put_url, json=payload)
                try:
                    put_resp.raise_for_status()
                except httpx.HTTPStatusError as put_e:
                    msg = _extract_response_message(put_e.response)
                    raise httpx.HTTPStatusError(
                        f"PUT failed ({put_e.response.status_code}): {msg}",
                        request=put_e.request,
                        response=put_e.response,
                    ) from put_e
            else:
                msg = _extract_response_message(e.response)
                raise httpx.HTTPStatusError(
                    f"Import failed ({e.response.status_code}): {msg}",
                    request=e.request,
                    response=e.response,
                ) from e
        return resource_id

    def _stream_graph(self, graph_id: str, query: str) -> tuple[str, str]:
        """Graph stream API 호출 → (파싱된 텍스트, 원본 SSE 텍스트) 반환."""
        payload = {
            "graph_id": graph_id,
            "input_data": {
                "messages": [{"content": query, "type": "human"}],
                "additional_kwargs": {},
            },
        }
        text, _, raw = self._call_stream(
            f"{self.base_url}/api/v1/agent/agents/graphs/stream", payload
        )
        return text, raw

    def _stream_app(self, app_id: str, query: str, api_key: str) -> tuple[str, str]:
        """App(agent_gateway) stream API 호출 → (파싱된 텍스트, 원본 SSE 텍스트) 반환."""
        payload = {
            "input": {
                "messages": [{"content": query, "type": "human"}],
                "additional_kwargs": {},
            },
            "config": {},
        }
        text, _, raw = self._call_stream(
            f"{self.base_url}/api/v1/agent_gateway/{app_id}/stream",
            payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        return text, raw

    # ── Prompt Stage ──────────────────────────────

    def run_prompt_stage(
        self, prompt_cfg: PromptConfig, scenario_dir: str
    ) -> tuple[str, StepResult]:
        step_name = f"Prompt: {prompt_cfg.name}"
        start = time.time()

        try:
            self._notify(f"[Prompt] '{prompt_cfg.name}' 처리 중...")

            file_path = self._resolve_path(prompt_cfg.json_path, scenario_dir)
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            payload["name"] = prompt_cfg.name

            if prompt_cfg.id:
                # Import API: id 지정 생성/검증
                prompt_id = self._import_resource(
                    import_url=f"{self.base_url}/api/v1/agent/inference-prompts/import",
                    id_param="prompt_uuid",
                    resource_id=prompt_cfg.id,
                    payload=payload,
                    update_if_exists=prompt_cfg.update_if_exists,
                    put_url=f"{self.base_url}/api/v1/agent/inference-prompts/{prompt_cfg.id}",
                )
            else:
                # Create API: id 없는 경우 신규 생성
                resp = self.client.post(
                    f"{self.base_url}/api/v1/agent/inference-prompts", json=payload
                )
                resp.raise_for_status()
                prompt_id = resp.json()["id"]
                self._notify(f"[Prompt] 생성 완료: {prompt_id}")

            return prompt_id, StepResult(
                step=step_name,
                status=StepStatus.PASS,
                request=payload,
                response=f"prompt_id={prompt_id}",
                elapsed_time=time.time() - start,
            )

        except Exception as e:
            traceback.print_exc()
            self._notify(f"[Prompt] 오류: {e}", "error")
            return "", StepResult(
                step=step_name,
                status=StepStatus.ERROR,
                error=str(e),
                elapsed_time=time.time() - start,
            )

    # ── Graph Stage ───────────────────────────────

    def run_graph_stage(
        self,
        graph_cfg: GraphConfig,
        scenario_dir: str,
        prompt_vars: dict[str, str],
        answer_judge: Optional[AnswerJudge],
    ) -> tuple[str, list[StepResult]]:
        results: list[StepResult] = []
        graph_id = ""
        start = time.time()
        step_name = f"Graph: {graph_cfg.name}"

        try:
            self._notify(f"[Graph] '{graph_cfg.name}' 처리 중...")

            file_path = self._resolve_path(graph_cfg.file_path, scenario_dir)
            with open(file_path, "r", encoding="utf-8") as f:
                graph_content = f.read()

            graph_content = self._substitute_variables(graph_content, prompt_vars)
            payload = json.loads(graph_content)

            # force-create: 항상 새 리소스 생성 (datetime 접미사)
            if graph_cfg.force_create:
                graph_name = f"{graph_cfg.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                payload["name"] = graph_name
                resp = self.client.post(
                    f"{self.base_url}/api/v1/agent/agents/graphs", json=payload
                )
                resp.raise_for_status()
                graph_id = resp.json()["id"]
                self._notify(f"[Graph] 생성 완료 (force-create): {graph_id}")
            elif graph_cfg.id:
                # Import API: id 지정 생성/검증
                payload["name"] = graph_cfg.name
                graph_id = self._import_resource(
                    import_url=f"{self.base_url}/api/v1/agent/agents/graphs/import",
                    id_param="agent_id",
                    resource_id=graph_cfg.id,
                    payload=payload,
                    update_if_exists=graph_cfg.update_if_exists,
                    put_url=f"{self.base_url}/api/v1/agent/agents/graphs/{graph_cfg.id}",
                )
            else:
                # Create API: id 없는 경우 신규 생성
                payload["name"] = graph_cfg.name
                resp = self.client.post(
                    f"{self.base_url}/api/v1/agent/agents/graphs", json=payload
                )
                resp.raise_for_status()
                graph_id = resp.json()["id"]
                self._notify(f"[Graph] 생성 완료: {graph_id}")

            results.append(StepResult(
                step=step_name,
                status=StepStatus.PASS,
                response=f"graph_id={graph_id}",
                elapsed_time=time.time() - start,
            ))

            if answer_judge and graph_id:
                for question in answer_judge.questions:
                    q_start = time.time()
                    self._notify(f"[Graph] 스트림 테스트: '{question}'")
                    try:
                        response_text, raw_response = self._stream_graph(graph_id, question)
                        judge_result = self.judge.judge(
                            question=question,
                            response=response_text,
                            criteria=answer_judge.criteria,
                        )
                        results.append(StepResult(
                            step=f"Graph Stream [{question}]",
                            status=StepStatus.PASS if judge_result.status == JudgeStatus.PASS else StepStatus.FAIL,
                            request={"query": question},
                            raw_response=raw_response,
                            elapsed_time=time.time() - q_start,
                            judge_result=judge_result,
                        ))
                    except StreamError as e:
                        results.append(StepResult(
                            step=f"Graph Stream [{question}]",
                            status=StepStatus.FAIL,
                            request={"query": question},
                            raw_response=e.raw_response,
                            error=str(e),
                            elapsed_time=time.time() - q_start,
                        ))
                    except Exception as e:
                        traceback.print_exc()
                        results.append(StepResult(
                            step=f"Graph Stream [{question}]",
                            status=StepStatus.ERROR,
                            error=str(e),
                            elapsed_time=time.time() - q_start,
                        ))

        except Exception as e:
            traceback.print_exc()
            self._notify(f"[Graph] 오류: {e}", "error")
            results.append(StepResult(
                step=step_name,
                status=StepStatus.ERROR,
                error=str(e),
                elapsed_time=time.time() - start,
            ))

        return graph_id, results

    # ── App Stage ─────────────────────────────────

    def run_app_stage(
        self,
        app_cfg: AppConfig,
        graph_id: str,
        answer_judge: Optional[AnswerJudge],
    ) -> tuple[str, list[StepResult]]:
        results: list[StepResult] = []
        app_id = ""
        start = time.time()
        step_name = f"App: {app_cfg.name}"

        try:
            self._notify(f"[App] '{app_cfg.name}' 배포 중...")
            existing = self._find_app_by_name(app_cfg.name)

            if existing:
                app_id = existing["id"]
                self._notify(f"[App] 기존 리소스 재사용: {app_id}")
            else:
                payload = {
                    "name": app_cfg.name,
                    "description": app_cfg.name,
                    "target_id": graph_id,
                    "target_type": "agent_graph",
                    "serving_type": "shared",
                    "cpu_limit": 2,
                    "cpu_request": 1,
                    "gpu_limit": 0,
                    "gpu_request": 0,
                    "max_replicas": 1,
                    "mem_limit": 2,
                    "mem_request": 2,
                    "min_replicas": 1,
                    "workers_per_core": 3,
                }
                resp = self.client.post(
                    f"{self.base_url}/api/v1/agent/agents/apps", json=payload
                )
                resp.raise_for_status()
                app_id = resp.json()["data"]["app_id"]
                self._notify(f"[App] 배포 완료: {app_id}")

            results.append(StepResult(
                step=step_name,
                status=StepStatus.PASS,
                response=f"app_id={app_id}",
                elapsed_time=time.time() - start,
            ))

            if answer_judge and app_id:
                api_key = self._get_app_apikey(app_id)
                for question in answer_judge.questions:
                    q_start = time.time()
                    self._notify(f"[App] 스트림 테스트: '{question}'")
                    try:
                        response_text, raw_response = self._stream_app(app_id, question, api_key)
                        judge_result = self.judge.judge(
                            question=question,
                            response=response_text,
                            criteria=answer_judge.criteria,
                        )
                        results.append(StepResult(
                            step=f"App Stream [{question}]",
                            status=StepStatus.PASS if judge_result.status == JudgeStatus.PASS else StepStatus.FAIL,
                            request={"query": question},
                            raw_response=raw_response,
                            elapsed_time=time.time() - q_start,
                            judge_result=judge_result,
                        ))
                    except StreamError as e:
                        results.append(StepResult(
                            step=f"App Stream [{question}]",
                            status=StepStatus.FAIL,
                            request={"query": question},
                            raw_response=e.raw_response,
                            error=str(e),
                            elapsed_time=time.time() - q_start,
                        ))
                    except Exception as e:
                        traceback.print_exc()
                        results.append(StepResult(
                            step=f"App Stream [{question}]",
                            status=StepStatus.ERROR,
                            error=str(e),
                            elapsed_time=time.time() - q_start,
                        ))

        except Exception as e:
            traceback.print_exc()
            if isinstance(e, httpx.HTTPStatusError):
                try:
                    body = e.response.json()
                except Exception:
                    body = e.response.text
                msg = f"{e} | response body: {body}"
            else:
                msg = str(e)
            self._notify(f"[App] 오류: {msg}", "error")
            results.append(StepResult(
                step=step_name,
                status=StepStatus.ERROR,
                error=msg,
                elapsed_time=time.time() - start,
            ))

        return app_id, results

    # ── Cleanup Stage ─────────────────────────────

    def run_cleanup(
        self,
        prompt_pairs: list[tuple[PromptConfig, str]],
        graph_cfg: Optional[GraphConfig],
        graph_id: str,
        app_cfg: Optional[AppConfig],
        app_id: str,
    ) -> list[StepResult]:
        results: list[StepResult] = []

        def _delete(label: str, url: str):
            # Normal delete (DELETE)
            try:
                self._notify(f"[Cleanup] {label} 삭제 중...")
                resp = self.client.delete(url)
                resp.raise_for_status()
                results.append(StepResult(step=f"Cleanup {label}", status=StepStatus.PASS))
            except Exception as e:
                traceback.print_exc()
                results.append(StepResult(
                    step=f"Cleanup {label}", status=StepStatus.ERROR, error=str(e)
                ))

        # App → Graph → Prompt 순으로 삭제
        if app_cfg and app_cfg.auto_delete and app_id:
            _delete(
                f"App ({app_id})",
                f"{self.base_url}/api/v1/agent/agents/apps/{app_id}",
            )
        if graph_cfg and graph_cfg.auto_delete and graph_id:
            _delete(
                f"Graph ({graph_id})",
                f"{self.base_url}/api/v1/agent/agents/graphs/{graph_id}",
            )
        for prompt_cfg, prompt_id in prompt_pairs:
            if prompt_cfg.auto_delete and prompt_id:
                _delete(
                    f"Prompt ({prompt_id})",
                    f"{self.base_url}/api/v1/agent/inference-prompts/{prompt_id}",
                )

        return results

    # ── 메인 오케스트레이션 ────────────────────────

    def run_scenario(self, yaml_path: str) -> ScenarioResult:
        """yaml_path 의 시나리오를 로드하고 전체 파이프라인을 실행합니다."""
        scenario = load_scenario_from_file(Path(yaml_path))
        scenario_dir = str(Path(yaml_path).parent)
        result = ScenarioResult(scenario_name=scenario.scenario_name)

        prompt_vars: dict[str, str] = {}
        prompt_pairs: list[tuple[PromptConfig, str]] = []

        # 1. Prompt Stage
        for prompt_cfg in scenario.prompts:
            prompt_id, step = self.run_prompt_stage(prompt_cfg, scenario_dir)
            result.steps.append(step)
            if step.status == StepStatus.ERROR:
                self._finalize(result, prompt_pairs, scenario, "", "")
                return result
            placeholder_key = prompt_cfg.placeholder_in_graph or prompt_cfg.name
            prompt_vars[placeholder_key] = prompt_id
            prompt_pairs.append((prompt_cfg, prompt_id))

        # 2. Graph Stage
        graph_id = ""
        if scenario.graph:
            graph_id, graph_steps = self.run_graph_stage(
                graph_cfg=scenario.graph,
                scenario_dir=scenario_dir,
                prompt_vars=prompt_vars,
                answer_judge=scenario.answer_judge,
            )
            result.steps.extend(graph_steps)
            if graph_steps and graph_steps[0].status == StepStatus.ERROR:
                self._finalize(result, prompt_pairs, scenario, graph_id, "")
                return result

        # 3. App Stage
        app_id = ""
        graph_stream_steps = [
            s for s in result.steps if s.step.startswith("Graph Stream [")
        ]
        graph_stream_all_pass = all(s.status == StepStatus.PASS for s in graph_stream_steps)
        can_deploy_app = bool(graph_id) and (not graph_stream_steps or graph_stream_all_pass)

        if scenario.app and graph_id and can_deploy_app:
            app_id, app_steps = self.run_app_stage(
                app_cfg=scenario.app,
                graph_id=graph_id,
                answer_judge=scenario.answer_judge,
            )
            result.steps.extend(app_steps)
        elif scenario.app and graph_id and not can_deploy_app:
            result.steps.append(StepResult(
                step=f"App: {scenario.app.name}",
                status=StepStatus.SKIP,
                error="Skipped because Graph Stream did not fully pass.",
            ))
            self._notify(
                "[App] Graph Stream 검증 실패로 App 배포를 건너뜁니다.",
                "warning",
            )

        # 4. Cleanup + finalize
        self._finalize(result, prompt_pairs, scenario, graph_id, app_id)
        return result

    def _finalize(
        self,
        result: ScenarioResult,
        prompt_pairs: list[tuple[PromptConfig, str]],
        scenario: Scenario,
        graph_id: str,
        app_id: str,
    ):
        cleanup_steps = self.run_cleanup(
            prompt_pairs=prompt_pairs,
            graph_cfg=scenario.graph,
            graph_id=graph_id,
            app_cfg=scenario.app,
            app_id=app_id,
        )
        result.steps.extend(cleanup_steps)
        result.compute_final_status()

