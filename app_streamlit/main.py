"""[Mode 1] Streamlit UI 앱 — Agent Builder QA Test Runner"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st
import queue
import threading

import streamlit.components.v1 as st_components

SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() != "false"


def _render_copy_table(rows: list[dict], copy_cols: list[str]) -> None:
    """테이블 렌더링. copy_cols에 해당하는 컬럼은 hover 시 copy 아이콘 표시."""
    if not rows:
        st.info("결과 없음")
        return
    headers = list(rows[0].keys())
    height = 37 * (len(rows) + 1) + 16

    ths = "".join(f"<th>{h}</th>" for h in headers)
    trs = ""
    for row in rows:
        tds = ""
        for h in headers:
            val = str(row.get(h, "")).replace('"', "&quot;").replace("<", "&lt;")
            if h in copy_cols:
                tds += (
                    f'<td class="cp" data-v="{val}">'
                    f'<span>{val}</span>'
                    f'<button class="ci" onclick="doCopy(this)" title="복사">⎘</button>'
                    f"</td>"
                )
            else:
                tds += f"<td>{val}</td>"
        trs += f"<tr>{tds}</tr>"

    html = f"""
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:sans-serif;font-size:13px}}
table{{width:100%;border-collapse:collapse}}
th{{background:#f0f2f6;padding:7px 10px;text-align:left;border-bottom:2px solid #ddd;white-space:nowrap}}
td{{padding:6px 10px;border-bottom:1px solid #eee;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
tr:hover td{{background:#f5f7fa}}
.cp{{position:relative}}
.ci{{display:none;position:absolute;right:4px;top:50%;transform:translateY(-50%);
     background:#fff;border:1px solid #ccc;border-radius:3px;cursor:pointer;
     padding:1px 6px;font-size:12px;color:#555;line-height:1.4}}
.cp:hover .ci{{display:block}}
.ci:hover{{background:#e8e8e8}}
</style>
<table>
<thead><tr>{ths}</tr></thead>
<tbody>{trs}</tbody>
</table>
<script>
function doCopy(btn){{
  var v = btn.parentElement.getAttribute('data-v');
  navigator.clipboard.writeText(v).then(function(){{
    btn.textContent = '✓';
    btn.style.color = 'green';
    setTimeout(function(){{ btn.textContent = '⎘'; btn.style.color = '#555'; }}, 1200);
  }});
}}
</script>"""
    st_components.html(html, height=height, scrolling=False)


_DEFAULT_ADXP_ENDPOINT = "https://aip.sktai.io/api/v1/gateway/chat/completions"
_DEFAULT_BASE_URL = "https://aip.sktai.io"

from core.engine import ScenarioEngine, discover_scenario_files
from core.judge import LLMJudge
from core.models import ScenarioResult, StepStatus


def _run_scenarios_thread(
    targets: list[str],
    scenario_labels: dict[str, str],
    base_url: str,
    admin_token: str,
    judge_provider: str,
    judge_api_key: str,
    judge_model: str,
    judge_temperature: float,
    judge_endpoint: str,
    stop_event: threading.Event,
    result_queue: queue.Queue,
) -> None:
    """백그라운드에서 시나리오를 순차 실행하고 결과를 큐로 전달합니다."""
    judge = LLMJudge(
        provider=judge_provider,
        api_key=judge_api_key,
        model=judge_model,
        temperature=judge_temperature,
        endpoint=judge_endpoint,
    )
    results: list[ScenarioResult] = []

    for yaml_path in targets:
        if stop_event.is_set():
            result_queue.put({"type": "all_done", "results": results, "stopped": True})
            return

        scenario_name = scenario_labels.get(yaml_path, yaml_path)
        result_queue.put({"type": "scenario_start", "name": scenario_name})

        def on_update(msg: str, level: str = "info", _n=scenario_name, _rq=result_queue, _se=stop_event):
            _rq.put({"type": "log", "scenario": _n, "msg": msg, "level": level})
            if _se.is_set():
                raise InterruptedError("사용자가 실행을 중단했습니다.")

        engine = ScenarioEngine(
            base_url=base_url,
            admin_token=admin_token,
            judge=judge,
            on_step_update=on_update,
        )

        try:
            result = engine.run_scenario(yaml_path)
            results.append(result)
            result_queue.put({
                "type": "scenario_done",
                "name": scenario_name,
                "result": result,
                "status": result.final_status.value,
            })
        except InterruptedError:
            result_queue.put({"type": "scenario_stopped", "name": scenario_name})
            result_queue.put({"type": "all_done", "results": results, "stopped": True})
            return
        except Exception as exc:
            result_queue.put({
                "type": "scenario_error",
                "name": scenario_name,
                "error": str(exc),
                "tb": traceback.format_exc(),
            })

    result_queue.put({"type": "all_done", "results": results, "stopped": False})


# ──────────────────────────────────────────────────────────────────────────────
# Page Config
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Agent Builder QA",
    page_icon="🧪",
    layout="wide",
)

# ──────────────────────────────────────────────────────────────────────────────
# Session State Init
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "llm_provider": os.getenv("LLM_PROVIDER", "adxp"),
    "llm_api_key": os.getenv("LLM_API_KEY", ""),
    "llm_model": os.getenv("LLM_MODEL", "GIP/gpt-4.1"),
    "llm_temperature": 0.0,
    "llm_endpoint": os.getenv("ADXP_JUDGE_ENDPOINT", _DEFAULT_ADXP_ENDPOINT),
    "base_url": os.getenv("BASE_URL", _DEFAULT_BASE_URL),
    "auth_url": os.getenv("AUTH_URL", "https://aip.sktai.io"),
    "auth_username": os.getenv("AUTH_USERNAME", ""),
    "auth_password": os.getenv("AUTH_PASSWORD", ""),
    "auth_client_id": os.getenv("AUTH_CLIENT_ID", "default"),
    "admin_token": "",
    "refresh_token": "",
    "token_expires_at": 0.0,
    "token_expires_in": 3600,
    "scenarios_dir": "./scenarios",
    "scenario_files": [],
    "running": False,
    "stop_requested": False,
    "results": [],
    "_stop_event": None,
    "_result_queue": None,
    "_thread": None,
    "_scenario_progress": {},
}

for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ──────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_token() -> tuple[bool, str]:
    """Keycloak 로그인 → access_token 획득."""
    url = f"{st.session_state.auth_url.rstrip('/')}/api/v1/auth/login"
    try:
        resp = httpx.post(
            url,
            data={
                "username": st.session_state.auth_username,
                "password": st.session_state.auth_password,
                "client_id": st.session_state.auth_client_id,
            },
            timeout=30.0,
            verify=SSL_VERIFY,
        )
        resp.raise_for_status()
        body = resp.json()
        expires_in = body.get("expires_in", 3600)
        st.session_state.admin_token = body["access_token"]
        st.session_state.refresh_token = body.get("refresh_token", "")
        st.session_state.token_expires_in = expires_in
        st.session_state.token_expires_at = time.time() + expires_in
        return True, ""
    except Exception as e:
        traceback.print_exc()
        return False, str(e)


def _do_refresh_token() -> tuple[bool, str]:
    """refresh_token으로 새 access_token 획득."""
    url = f"{st.session_state.auth_url.rstrip('/')}/api/v1/auth/token/refresh"
    try:
        resp = httpx.post(
            url,
            params={"refresh_token": st.session_state.refresh_token},
            timeout=30.0,
            verify=SSL_VERIFY,
        )
        resp.raise_for_status()
        body = resp.json()
        expires_in = body.get("expires_in", st.session_state.token_expires_in)
        st.session_state.admin_token = body["access_token"]
        st.session_state.token_expires_at = time.time() + expires_in
        return True, ""
    except Exception as e:
        traceback.print_exc()
        return False, str(e)


def _ensure_valid_token() -> tuple[bool, str]:
    """토큰 유효성 확인 및 필요 시 자동 갱신."""
    if not st.session_state.admin_token or st.session_state.token_expires_at == 0.0:
        return False, "로그인이 필요합니다."
    if time.time() >= st.session_state.token_expires_at - 60:
        if st.session_state.refresh_token:
            ok, err = _do_refresh_token()
            if not ok:
                return False, f"토큰 갱신 실패: {err}"
        else:
            return False, "토큰이 만료되었습니다. 다시 로그인해주세요."
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — 환경 설정
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ 환경 설정")

    st.subheader("LLM Judge")
    _providers = ["adxp","openai", "anthropic"]
    _provider_idx = _providers.index(st.session_state.llm_provider) if st.session_state.llm_provider in _providers else 0
    st.session_state.llm_provider = st.selectbox(
        "Provider",
        options=_providers,
        index=_provider_idx,
    )

    _is_adxp = st.session_state.llm_provider == "adxp"

    if _is_adxp:
        st.session_state.llm_endpoint = st.text_input(
            "Judge Endpoint",
            value=st.session_state.llm_endpoint,
            placeholder=_DEFAULT_ADXP_ENDPOINT,
        )
        st.session_state.llm_model = st.text_input(
            "Serving Name",
            value=st.session_state.llm_model,
            placeholder="serving-name",
        )
        st.session_state.llm_api_key = st.text_input(
            "Model Gateway API Key",
            value=st.session_state.llm_api_key,
            type="password",
            placeholder="Model Gateway에서 발급받은 API Key",
        )
    else:
        _default_model = (
            "GIP/gpt-4.1" if st.session_state.llm_provider == "openai"
            else "claude-haiku-4-5-20251001"
        )
        st.session_state.llm_model = st.text_input(
            "Model",
            value=st.session_state.llm_model or _default_model,
            placeholder=_default_model,
        )
        st.session_state.llm_api_key = st.text_input(
            "API Key",
            value=st.session_state.llm_api_key,
            type="password",
            placeholder="sk-...",
        )

    st.session_state.llm_temperature = st.number_input(
        "Temperature",
        value=float(st.session_state.llm_temperature),
        min_value=0.0,
        max_value=2.0,
        step=0.1,
        format="%.1f",
    )

    st.divider()

    st.subheader("Agent Builder")
    st.session_state.base_url = st.text_input(
        "Base URL",
        value=st.session_state.base_url,
        placeholder=_DEFAULT_BASE_URL,
    )
    st.session_state.auth_url = st.text_input(
        "Auth Server URL",
        value=st.session_state.auth_url,
        placeholder="http://keycloak-auth.aiplatform.svc.cluster.local:8000",
    )
    st.session_state.auth_client_id = st.text_input(
        "Project Name",
        value=st.session_state.auth_client_id,
    )
    st.session_state.auth_username = st.text_input(
        "Username",
        value=st.session_state.auth_username,
    )
    st.session_state.auth_password = st.text_input(
        "Password",
        value=st.session_state.auth_password,
        type="password",
    )
    if st.button("🔑 Login", use_container_width=True):
        ok, err = _fetch_token()
        if ok:
            st.success("로그인 성공")
        else:
            st.error(f"로그인 실패: {err}")

    # Token status
    if st.session_state.admin_token:
        _remaining = st.session_state.token_expires_at - time.time()
        if _remaining > 60:
            st.caption(f"✅ Token valid ({int(_remaining / 60)}m {int(_remaining % 60)}s)")
        elif _remaining > 0:
            st.caption(f"⚠️ Token expiring soon ({int(_remaining)}s)")
        else:
            st.caption("❌ Token expired")
    else:
        st.caption("⚪ 로그인 필요")

    st.divider()

    st.subheader("시나리오")
    st.session_state.scenarios_dir = st.text_input(
        "Scenarios 디렉토리",
        value=st.session_state.scenarios_dir,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_scenario_list() -> int:
    root = Path(st.session_state.scenarios_dir)
    files = discover_scenario_files(root)
    st.session_state.scenario_files = [str(f) for f in files]
    return len(files)


def get_scenario_label(yaml_path: str) -> str:
    return Path(yaml_path).parent.name


def validate_config() -> list[str]:
    errors = []
    if st.session_state.llm_provider != "adxp" and not st.session_state.llm_api_key:
        errors.append("LLM API Key를 입력해주세요.")
    if not st.session_state.base_url:
        errors.append("Agent Builder Base URL을 입력해주세요.")
    if not st.session_state.admin_token:
        errors.append("로그인이 필요합니다.")
    return errors


def build_engine(on_step_update) -> ScenarioEngine:
    judge = LLMJudge(
        provider=st.session_state.llm_provider,
        api_key=st.session_state.llm_api_key,
        model=st.session_state.llm_model,
        temperature=float(st.session_state.llm_temperature),
        endpoint=st.session_state.llm_endpoint,
    )
    return ScenarioEngine(
        base_url=st.session_state.base_url,
        admin_token=st.session_state.admin_token,
        judge=judge,
        on_step_update=on_step_update,
    )


# 최초 로드 시 시나리오 목록 채우기
if not st.session_state.scenario_files:
    load_scenario_list()

# ──────────────────────────────────────────────────────────────────────────────
# Main — Title
# ──────────────────────────────────────────────────────────────────────────────

st.title("🧪 Agent Builder QA")
st.caption("YAML 시나리오 기반 E2E 테스트 자동화 도구")

tab_runner, tab_editor = st.tabs(["▶ Test Runner", "📝 Scenario Editor"])

# ──────────────────────────────────────────────────────────────────────────────
# Tab 1: Test Runner
# ──────────────────────────────────────────────────────────────────────────────

with tab_runner:

    st.subheader("Scenario Control")

    btn_col1, btn_col2 = st.columns([1, 5])
    with btn_col1:
        if st.button("🔄 Reload", use_container_width=True):
            count = load_scenario_list()
            st.toast(f"{count}개 시나리오 로드됨")

    scenario_labels = {
        f: get_scenario_label(f)
        for f in st.session_state.scenario_files
    }

    selected_paths: list[str] = st.multiselect(
        "실행할 시나리오",
        options=list(scenario_labels.keys()),
        format_func=lambda x: scenario_labels.get(x, x),
        default=list(scenario_labels.keys()),
        disabled=st.session_state.running,
    )

    run_col1, run_col2, run_col3 = st.columns([2, 2, 1])
    with run_col1:
        run_selected_btn = st.button(
            "▶ Run Selected",
            disabled=st.session_state.running or not selected_paths,
            use_container_width=True,
            type="primary",
        )
    with run_col2:
        run_all_btn = st.button(
            "⏩ Run All",
            disabled=st.session_state.running or not st.session_state.scenario_files,
            use_container_width=True,
        )
    with run_col3:
        stop_btn = st.button(
            "⏹ Stop",
            disabled=not st.session_state.running,
            use_container_width=True,
        )

    if stop_btn:
        st.session_state.stop_requested = True
        if st.session_state._stop_event:
            st.session_state._stop_event.set()

    # ── Execution: 백그라운드 스레드 시작 ────────────

    targets: list[str] = []
    if run_selected_btn:
        targets = selected_paths
    elif run_all_btn:
        targets = list(scenario_labels.keys())

    if targets:
        errors = validate_config()
        if errors:
            for e in errors:
                st.error(e)
        else:
            _token_ok, _token_err = _ensure_valid_token()
            if not _token_ok:
                st.error(_token_err)
            else:
                _stop_event = threading.Event()
                _result_queue: queue.Queue = queue.Queue()
                st.session_state._stop_event = _stop_event
                st.session_state._result_queue = _result_queue
                st.session_state._scenario_progress = {}
                st.session_state.running = True
                st.session_state.stop_requested = False
                st.session_state.results = []

                _thread = threading.Thread(
                    target=_run_scenarios_thread,
                    args=(
                        targets,
                        scenario_labels,
                        st.session_state.base_url,
                        st.session_state.admin_token,
                        st.session_state.llm_provider,
                        st.session_state.llm_api_key,
                        st.session_state.llm_model,
                        float(st.session_state.llm_temperature),
                        st.session_state.llm_endpoint,
                        _stop_event,
                        _result_queue,
                    ),
                    daemon=True,
                )
                st.session_state._thread = _thread
                _thread.start()
                st.rerun()

    # ── 실행 중: 큐 polling ─────────────────────────────

    _just_finished = False
    if st.session_state.running:
        _rq = st.session_state._result_queue
        if _rq:
            try:
                while True:
                    _upd = _rq.get_nowait()
                    _t = _upd["type"]
                    if _t == "scenario_start":
                        st.session_state._scenario_progress[_upd["name"]] = {
                            "status": "running", "logs": []
                        }
                    elif _t == "log":
                        _prog = st.session_state._scenario_progress.setdefault(
                            _upd["scenario"], {"status": "running", "logs": []}
                        )
                        _prog["logs"].append((_upd["msg"], _upd["level"]))
                    elif _t == "scenario_done":
                        _prog = st.session_state._scenario_progress.setdefault(
                            _upd["name"], {"logs": []}
                        )
                        _prog["status"] = "done"
                        _prog["result"] = _upd["result"]
                    elif _t == "scenario_stopped":
                        _prog = st.session_state._scenario_progress.setdefault(
                            _upd.get("name", ""), {"logs": []}
                        )
                        _prog["status"] = "stopped"
                    elif _t == "scenario_error":
                        _prog = st.session_state._scenario_progress.setdefault(
                            _upd.get("name", ""), {"logs": []}
                        )
                        _prog["status"] = "error"
                        _prog["error"] = _upd.get("error", "")
                    elif _t == "all_done":
                        st.session_state.results = _upd.get("results", [])
                        st.session_state.running = False
                        _just_finished = True
            except queue.Empty:
                pass

    # ── 진행 상황 렌더링 (실행 중 / 완료 모두 표시) ──

    if st.session_state._scenario_progress:
        st.subheader("진행 상황")
        for _name, _prog in st.session_state._scenario_progress.items():
            _status = _prog.get("status", "running")
            _logs = _prog.get("logs", [])
            _parts = []
            for _msg, _lvl in _logs[-15:]:
                if _lvl == "error":
                    _parts.append(f":red[❌ {_msg}]")
                elif _lvl == "warning":
                    _parts.append(f":orange[⚠️ {_msg}]")
                else:
                    _parts.append(f"`{_msg}`")

            if _status == "running":
                with st.status(f"🔄 {_name} 실행 중...", expanded=True):
                    if _parts:
                        st.markdown("\n\n".join(_parts))
            elif _status == "done":
                _result = _prog.get("result")
                _is_pass = _result and _result.final_status == StepStatus.PASS
                with st.status(
                    f"{'✅' if _is_pass else '❌'} {_name}",
                    state="complete" if _is_pass else "error",
                    expanded=not _is_pass,
                ):
                    if _parts:
                        st.markdown("\n\n".join(_parts))
            elif _status == "stopped":
                st.warning(f"⏹ {_name} — 중단됨")
            elif _status == "error":
                with st.status(f"❌ {_name}", state="error", expanded=True):
                    if _parts:
                        st.markdown("\n\n".join(_parts))
                    st.error(_prog.get("error", "알 수 없는 오류"))

    # ── Polling 루프 제어 ────────────────────────────

    if st.session_state.running:
        time.sleep(0.5)
        st.rerun()
    elif _just_finished:
        st.rerun()

    # ── Result Report ──────────────────────────────

    if st.session_state.results:
        st.divider()
        st.subheader("결과 리포트")

        rows = []
        for r in st.session_state.results:
            judge_reasons = []
            total_elapsed = 0.0
            for step in r.steps:
                if step.judge_result:
                    judge_reasons.append(step.judge_result.reason)
                if step.elapsed_time:
                    total_elapsed += step.elapsed_time

            rows.append({
                "시나리오": r.scenario_name,
                "결과": r.final_status.value,
                "총 소요(s)": round(total_elapsed, 2),
                "LLM 판정 요약": " / ".join(judge_reasons) if judge_reasons else "-",
            })

        df = pd.DataFrame(rows)

        def _highlight(val: str) -> str:
            if val == "PASS":
                return "background-color:#d4edda; color:#155724"
            if val in ("FAIL", "ERROR"):
                return "background-color:#f8d7da; color:#721c24"
            return ""

        st.dataframe(
            df.style.map(_highlight, subset=["결과"]),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("상세 로그")

        for r in st.session_state.results:
            icon = "✅" if r.final_status == StepStatus.PASS else "❌"
            with st.expander(f"{icon} {r.scenario_name}", expanded=(r.final_status != StepStatus.PASS)):
                for step in r.steps:
                    status_icon = {
                        StepStatus.PASS: "🟢",
                        StepStatus.FAIL: "🔴",
                        StepStatus.ERROR: "🔴",
                        StepStatus.SKIP: "⚪",
                    }.get(step.status, "⚪")

                    col_a, col_b = st.columns([5, 1])
                    with col_a:
                        st.markdown(f"**{status_icon} {step.step}**")
                    with col_b:
                        if step.elapsed_time is not None:
                            st.caption(f"{step.elapsed_time:.2f}s")

                    if step.response:
                        with st.expander("Response", expanded=False):
                            st.markdown(step.response)

                    if step.raw_response:
                        with st.expander("Raw SSE Events", expanded=False):
                            st.code(step.raw_response, language="text")

                    if step.judge_result:
                        badge = (
                            "🟢 PASS" if step.judge_result.status.value == "PASS"
                            else "🔴 FAIL"
                        )
                        st.markdown(f"**Judge:** {badge} — {step.judge_result.reason}")

                    if step.error:
                        st.error(f"오류: {step.error}")

                    st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Tab 2: Scenario Editor
# ──────────────────────────────────────────────────────────────────────────────

with tab_editor:
    import json as _json
    import yaml as _yaml

    st.subheader("Scenario 파일 편집기")

    scenarios_root = Path(st.session_state.scenarios_dir)
    scenario_dirs = sorted([d for d in scenarios_root.iterdir() if d.is_dir()])

    if not scenario_dirs:
        st.info(f"`{st.session_state.scenarios_dir}` 경로에 시나리오 폴더가 없습니다.")
    else:
        # ── 1단계: 시나리오 폴더 선택 ──────────────────────
        folder_options = {str(d): d.name for d in scenario_dirs}
        selected_folder = st.selectbox(
            "시나리오 폴더",
            options=list(folder_options.keys()),
            format_func=lambda x: folder_options.get(x, x),
        )

        if selected_folder:
            folder_path = Path(selected_folder)
            editable_files = sorted(
                f for f in folder_path.iterdir()
                if f.is_file() and f.suffix in (".yaml", ".yml", ".json")
            )

            if not editable_files:
                st.info("편집 가능한 파일(.yaml/.json)이 없습니다.")
            else:
                # ── 2단계: 파일 선택 ───────────────────────────
                file_label_map = {str(f): f.name for f in editable_files}
                selected_file = st.selectbox(
                    "편집할 파일",
                    options=list(file_label_map.keys()),
                    format_func=lambda x: file_label_map.get(x, x),
                )

                if selected_file:
                    edit_path = Path(selected_file)
                    is_json = edit_path.suffix == ".json"
                    editor_key = f"file_editor__{selected_file}"

                    if editor_key not in st.session_state:
                        st.session_state[editor_key] = edit_path.read_text(encoding="utf-8")

                    ec1, ec2 = st.columns([1, 5])
                    with ec1:
                        if st.button("🔄 파일 다시 읽기", use_container_width=True):
                            st.session_state[editor_key] = edit_path.read_text(encoding="utf-8")
                            st.toast("파일을 다시 읽었습니다.")


                    edited = st.text_area(
                        f"`{edit_path}`",
                        height=480,
                        key=editor_key,
                    )

                    save_col, preview_col = st.columns([1, 4])
                    with save_col:
                        if st.button("💾 저장", type="primary", use_container_width=True):
                            try:
                                if is_json:
                                    _json.loads(edited)  # JSON 유효성 검사
                                else:
                                    _yaml.safe_load(edited)  # YAML 유효성 검사
                                edit_path.write_text(edited, encoding="utf-8")
                                st.success(f"저장 완료: `{edit_path}`")
                                if edit_path.suffix in (".yaml", ".yml"):
                                    load_scenario_list()
                            except (_json.JSONDecodeError, _yaml.YAMLError) as exc:
                                st.error(f"파싱 오류: {exc}")
                            except Exception as exc:
                                st.error(f"저장 실패: {exc}")

                    with preview_col:
                        with st.expander("파싱 미리보기", expanded=False):
                            try:
                                if is_json:
                                    st.json(_json.loads(edited))
                                else:
                                    st.json(_yaml.safe_load(edited))
                            except Exception as exc:
                                st.error(f"파싱 오류: {exc}")

                    # scenario.yaml에 knowledges 섹션이 있을 때 Knowledge 조회 UI
                    is_yaml = edit_path.suffix in (".yaml", ".yml")
                    if is_yaml and edit_path.name == "scenario.yaml" and "knowledges:" in edited:
                        with st.container(border=True):
                            st.markdown("**Knowledge 조회**")
                            kb_url_key = f"kb_url_scenario__{selected_file}"
                            know_page_key = f"know_browser_page__{selected_file}"
                            know_data_key = f"know_browser_data__{selected_file}"

                            if know_page_key not in st.session_state:
                                st.session_state[know_page_key] = 1

                            kv_col1, kv_col2 = st.columns([4, 1])
                            with kv_col1:
                                kb_url_val = st.text_input(
                                    "Knowledge Base URL",
                                    value=st.session_state.get(kb_url_key, st.session_state.get("base_url", "")),
                                    key=kb_url_key,
                                    placeholder="https://...",
                                    label_visibility="collapsed",
                                )
                            with kv_col2:
                                fetch_clicked = st.button("🔍 조회", use_container_width=True, key=f"know_fetch__{selected_file}")

                            if fetch_clicked:
                                if not st.session_state.get("admin_token"):
                                    st.warning("로그인이 필요합니다. 사이드바에서 로그인 후 다시 시도하세요.")
                                else:
                                    st.session_state[know_page_key] = 1
                                    try:
                                        page = 1
                                        resp = httpx.get(
                                            f"{kb_url_val.rstrip('/')}/api/v1/knowledge/repos/unified",
                                            params={"page": page, "size": 5, "filter": "is_deleted:false,is_active:true"},
                                            headers={"Authorization": f"Bearer {st.session_state.get('admin_token')}"},
                                            verify=SSL_VERIFY,
                                            timeout=30.0,
                                        )
                                        resp.raise_for_status()
                                        st.session_state[know_data_key] = resp.json()
                                    except Exception as exc:
                                        st.error(f"조회 실패: {exc}")
                                        st.session_state[know_data_key] = None

                            know_data = st.session_state.get(know_data_key)
                            if know_data is not None:
                                # items 추출
                                raw = know_data.get("data", []) if isinstance(know_data, dict) else []
                                if isinstance(raw, list):
                                    items = raw
                                elif isinstance(raw, dict):
                                    items = raw.get("data", [])
                                else:
                                    items = []

                                # pagination: payload.pagination.links 기반
                                links = (know_data.get("payload", {}).get("pagination", {}).get("links", [])
                                         if isinstance(know_data, dict) else [])
                                has_prev = len(links) > 0 and links[0].get("url") is not None
                                has_next = len(links) > 1 and links[1].get("url") is not None
                                prev_page = links[0].get("page") if has_prev else None
                                next_page = links[1].get("page") if has_next else None
                                page_size = 5
                                current_page = st.session_state[know_page_key]
                                last_page = (know_data.get("payload", {}).get("pagination", {}).get("last_page", -1)
                                             if isinstance(know_data, dict) else -1)
                                page_label = f"{current_page} / {last_page}" if last_page and last_page > 0 else str(current_page)

                                rows = [{
                                    "id": row.get("id", ""),
                                    "name": row.get("name", ""),
                                    "vector_db_type": row.get("vector_db_type", ""),
                                    "kind": row.get("kind", ""),
                                } for row in items]
                                _render_copy_table(rows, copy_cols=["id", "name"])

                                _, pg_col1, pg_col2, pg_col3, _ = st.columns([3, 1, 2, 1, 3])
                                with pg_col1:
                                    if st.button("<", key=f"know_prev__{selected_file}", disabled=not has_prev, use_container_width=True):
                                        if not st.session_state.get("admin_token"):
                                            st.warning("로그인이 필요합니다. 사이드바에서 로그인 후 다시 시도하세요.")
                                        else:
                                            new_page = max(1, prev_page if prev_page else current_page - 1)
                                            st.session_state[know_page_key] = new_page
                                            try:
                                                resp = httpx.get(
                                                    f"{kb_url_val.rstrip('/')}/api/v1/knowledge/repos/unified",
                                                    params={"page": new_page, "size": page_size, "filter": "is_deleted:false,is_active:true"},
                                                    headers={"Authorization": f"Bearer {st.session_state.get('admin_token')}"},
                                                    verify=SSL_VERIFY,
                                                    timeout=30.0,
                                                )
                                                resp.raise_for_status()
                                                st.session_state[know_data_key] = resp.json()
                                            except Exception as exc:
                                                st.error(f"조회 실패: {exc}")
                                            st.rerun()
                                with pg_col2:
                                    st.markdown(f"<div style='text-align:center; padding-top:8px'>{page_label}</div>", unsafe_allow_html=True)
                                with pg_col3:
                                    if st.button(">", key=f"know_next__{selected_file}", disabled=not has_next, use_container_width=True):
                                        if not st.session_state.get("admin_token"):
                                            st.warning("로그인이 필요합니다. 사이드바에서 로그인 후 다시 시도하세요.")
                                        else:
                                            new_page = next_page if next_page else current_page + 1
                                            st.session_state[know_page_key] = new_page
                                            try:
                                                resp = httpx.get(
                                                    f"{kb_url_val.rstrip('/')}/api/v1/knowledge/repos/unified",
                                                    params={"page": new_page, "size": page_size, "filter": "is_deleted:false,is_active:true"},
                                                    headers={"Authorization": f"Bearer {st.session_state.get('admin_token')}"},
                                                    verify=SSL_VERIFY,
                                                    timeout=30.0,
                                                )
                                                resp.raise_for_status()
                                                st.session_state[know_data_key] = resp.json()
                                            except Exception as exc:
                                                st.error(f"조회 실패: {exc}")
                                            st.rerun()

                    # scenario.yaml에 llms 섹션이 있을 때 LLM 조회 UI
                    if is_yaml and edit_path.name == "scenario.yaml" and "llms:" in edited:
                        with st.container(border=True):
                            st.markdown("**LLM 조회**")
                            llm_url_key = f"serving_url_scenario__{selected_file}"
                            llm_page_key = f"llm_browser_page__{selected_file}"
                            llm_data_key = f"llm_browser_data__{selected_file}"

                            if llm_page_key not in st.session_state:
                                st.session_state[llm_page_key] = 1

                            lv_col1, lv_col2 = st.columns([4, 1])
                            with lv_col1:
                                llm_url_val = st.text_input(
                                    "Serving URL",
                                    value=st.session_state.get(llm_url_key, st.session_state.get("base_url", "")),
                                    key=llm_url_key,
                                    placeholder="https://...",
                                    label_visibility="collapsed",
                                )
                            with lv_col2:
                                llm_fetch_clicked = st.button("🔍 조회", use_container_width=True, key=f"llm_fetch__{selected_file}")

                            if llm_fetch_clicked:
                                if not st.session_state.get("admin_token"):
                                    st.warning("로그인이 필요합니다. 사이드바에서 로그인 후 다시 시도하세요.")
                                else:
                                    st.session_state[llm_page_key] = 1
                                    try:
                                        resp = httpx.get(
                                            f"{llm_url_val.rstrip('/')}/api/v1/servings",
                                            params={"page": 1, "size": 5, "filter": "type:language,status:Available"},
                                            headers={"Authorization": f"Bearer {st.session_state.get('admin_token')}"},
                                            verify=SSL_VERIFY,
                                            timeout=30.0,
                                        )
                                        resp.raise_for_status()
                                        st.session_state[llm_data_key] = resp.json()
                                    except Exception as exc:
                                        st.error(f"조회 실패: {exc}")
                                        st.session_state[llm_data_key] = None

                            llm_data = st.session_state.get(llm_data_key)
                            if llm_data is not None:
                                # items 추출
                                llm_raw = llm_data.get("data", []) if isinstance(llm_data, dict) else []
                                if isinstance(llm_raw, list):
                                    llm_items = llm_raw
                                elif isinstance(llm_raw, dict):
                                    llm_items = llm_raw.get("data", [])
                                else:
                                    llm_items = []

                                # pagination: payload.pagination.links 기반
                                llm_links = (llm_data.get("payload", {}).get("pagination", {}).get("links", [])
                                             if isinstance(llm_data, dict) else [])
                                llm_has_prev = len(llm_links) > 0 and llm_links[0].get("url") is not None
                                llm_has_next = len(llm_links) > 1 and llm_links[1].get("url") is not None
                                llm_prev_page = llm_links[0].get("page") if llm_has_prev else None
                                llm_next_page = llm_links[1].get("page") if llm_has_next else None
                                llm_page_size = 5
                                llm_current_page = st.session_state[llm_page_key]
                                llm_last_page = (llm_data.get("payload", {}).get("pagination", {}).get("last_page", -1)
                                                 if isinstance(llm_data, dict) else -1)
                                llm_page_label = (f"{llm_current_page} / {llm_last_page}"
                                                  if llm_last_page and llm_last_page > 0 else str(llm_current_page))

                                llm_rows = [{
                                    "serving_name": row.get("name", ""),
                                    "model_name": row.get("model_name", ""),
                                    "provider_name": row.get("provider_name", ""),
                                    "serving_type": row.get("serving_type", ""),
                                } for row in llm_items]
                                _render_copy_table(llm_rows, copy_cols=["serving_name"])

                                _, lp_col1, lp_col2, lp_col3, _ = st.columns([3, 1, 2, 1, 3])
                                with lp_col1:
                                    if st.button("<", key=f"llm_prev__{selected_file}", disabled=not llm_has_prev, use_container_width=True):
                                        if not st.session_state.get("admin_token"):
                                            st.warning("로그인이 필요합니다. 사이드바에서 로그인 후 다시 시도하세요.")
                                        else:
                                            new_page = max(1, llm_prev_page if llm_prev_page else llm_current_page - 1)
                                            st.session_state[llm_page_key] = new_page
                                            try:
                                                resp = httpx.get(
                                                    f"{llm_url_val.rstrip('/')}/api/v1/servings",
                                                    params={"page": new_page, "size": llm_page_size, "filter": "type:language,status:Available"},
                                                    headers={"Authorization": f"Bearer {st.session_state.get('admin_token')}"},
                                                    verify=SSL_VERIFY,
                                                    timeout=30.0,
                                                )
                                                resp.raise_for_status()
                                                st.session_state[llm_data_key] = resp.json()
                                            except Exception as exc:
                                                st.error(f"조회 실패: {exc}")
                                            st.rerun()
                                with lp_col2:
                                    st.markdown(f"<div style='text-align:center; padding-top:8px'>{llm_page_label}</div>", unsafe_allow_html=True)
                                with lp_col3:
                                    if st.button(">", key=f"llm_next__{selected_file}", disabled=not llm_has_next, use_container_width=True):
                                        if not st.session_state.get("admin_token"):
                                            st.warning("로그인이 필요합니다. 사이드바에서 로그인 후 다시 시도하세요.")
                                        else:
                                            new_page = llm_next_page if llm_next_page else llm_current_page + 1
                                            st.session_state[llm_page_key] = new_page
                                            try:
                                                resp = httpx.get(
                                                    f"{llm_url_val.rstrip('/')}/api/v1/servings",
                                                    params={"page": new_page, "size": llm_page_size, "filter": "type:language,status:Available"},
                                                    headers={"Authorization": f"Bearer {st.session_state.get('admin_token')}"},
                                                    verify=SSL_VERIFY,
                                                    timeout=30.0,
                                                )
                                                resp.raise_for_status()
                                                st.session_state[llm_data_key] = resp.json()
                                            except Exception as exc:
                                                st.error(f"조회 실패: {exc}")
                                            st.rerun()
