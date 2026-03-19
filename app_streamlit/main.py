"""[Mode 1] Streamlit UI 앱 — Agent Builder QA Test Runner"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

_DEFAULT_ADXP_ENDPOINT = (
    "http://agent-gateway.aiplatform.svc.cluster.local/api/v1/gateway/chat/completion"
)
_DEFAULT_BASE_URL = "http://agent-backend.aiplatform.svc.cluster.local"

from core.engine import ScenarioEngine, discover_scenario_files
from core.judge import LLMJudge
from core.models import ScenarioResult, StepStatus

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
    "auth_url": os.getenv("AUTH_URL", ""),
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

# ──────────────────────────────────────────────────────────────────────────────
# Scenario Control
# ──────────────────────────────────────────────────────────────────────────────

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

# ──────────────────────────────────────────────────────────────────────────────
# Execution
# ──────────────────────────────────────────────────────────────────────────────

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
            st.session_state.running = True
            st.session_state.stop_requested = False
            st.session_state.results = []

            st.subheader("진행 상황")

            results: list[ScenarioResult] = []

            for yaml_path in targets:
                if st.session_state.stop_requested:
                    st.warning("⏹ 실행이 중단되었습니다.")
                    break

                scenario_name = scenario_labels.get(yaml_path, yaml_path)
                log_lines: list[str] = []

                with st.status(f"🔄 {scenario_name} 실행 중...", expanded=True) as status_box:
                    log_area = st.empty()

                    def on_update(msg: str, level: str = "info", _log=log_lines, _area=log_area):
                        _log.append(msg)
                        _area.markdown(
                            "\n\n".join(f"`{line}`" for line in _log[-15:])
                        )
                        if st.session_state.stop_requested:
                            raise InterruptedError("사용자가 실행을 중단했습니다.")

                    try:
                        engine = build_engine(on_update)
                        result = engine.run_scenario(yaml_path)
                        results.append(result)

                        if result.final_status == StepStatus.PASS:
                            status_box.update(label=f"✅ {scenario_name}", state="complete", expanded=False)
                        else:
                            status_box.update(label=f"❌ {scenario_name}", state="error", expanded=True)

                    except InterruptedError:
                        status_box.update(label=f"⏹ {scenario_name} — 중단됨", state="error", expanded=False)
                        break
                    except Exception as e:
                        traceback.print_exc()
                        st.error(f"실행 오류: {e}")
                        status_box.update(label=f"❌ {scenario_name} — 오류", state="error", expanded=True)

            st.session_state.results = results
            st.session_state.running = False

# ──────────────────────────────────────────────────────────────────────────────
# Result Report
# ──────────────────────────────────────────────────────────────────────────────

if st.session_state.results:
    st.divider()
    st.subheader("결과 리포트")

    # ── Summary Table ─────────────────────────────
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

    # ── Detailed Expanders ────────────────────────
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
