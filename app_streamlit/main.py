"""[Mode 1] Streamlit UI 앱 — Agent Builder QA Test Runner"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

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
    "llm_provider": "openai",
    "llm_api_key": "",
    "llm_model": "gpt-4o-mini",
    "base_url": "",
    "admin_token": "",
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
# Sidebar — 환경 설정
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ 환경 설정")

    st.subheader("LLM Judge")
    provider_idx = 0 if st.session_state.llm_provider == "openai" else 1
    st.session_state.llm_provider = st.selectbox(
        "Provider",
        options=["openai", "anthropic"],
        index=provider_idx,
    )

    default_model = (
        "gpt-4o-mini" if st.session_state.llm_provider == "openai"
        else "claude-haiku-4-5-20251001"
    )
    st.session_state.llm_model = st.text_input(
        "Model",
        value=st.session_state.llm_model or default_model,
        placeholder=default_model,
    )
    st.session_state.llm_api_key = st.text_input(
        "API Key",
        value=st.session_state.llm_api_key,
        type="password",
        placeholder="sk-...",
    )

    st.divider()

    st.subheader("Agent Builder")
    st.session_state.base_url = st.text_input(
        "Base URL",
        value=st.session_state.base_url,
        placeholder="http://localhost:8000",
    )
    st.session_state.admin_token = st.text_input(
        "Admin Token",
        value=st.session_state.admin_token,
        type="password",
    )

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
    if not st.session_state.llm_api_key:
        errors.append("LLM API Key를 입력해주세요.")
    if not st.session_state.base_url:
        errors.append("Agent Builder Base URL을 입력해주세요.")
    if not st.session_state.admin_token:
        errors.append("Admin Token을 입력해주세요.")
    return errors


def build_engine(on_step_update) -> ScenarioEngine:
    judge = LLMJudge(
        provider=st.session_state.llm_provider,
        api_key=st.session_state.llm_api_key,
        model=st.session_state.llm_model,
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
                    st.text_area(
                        "Response",
                        value=step.response,
                        height=80,
                        disabled=True,
                        key=f"resp_{r.scenario_name}_{step.step}",
                    )

                if step.judge_result:
                    badge = (
                        "🟢 PASS" if step.judge_result.status.value == "PASS"
                        else "🔴 FAIL"
                    )
                    st.markdown(f"**Judge:** {badge} — {step.judge_result.reason}")

                if step.error:
                    st.error(f"오류: {step.error}")

                st.divider()
