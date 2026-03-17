from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from core.engine import ScenarioEngine, discover_scenario_files, exit_code_for_results
from core.judge import LLMJudge
from core.models import JudgeResult, ScenarioResult, StepResult, StepStatus


def _default_scenario_root() -> Path:
    """Return the default scenarios directory."""
    here = Path(__file__).resolve()
    return here.parent.parent / "scenarios"


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the app_cli entrypoint.

    Note: 앱 설정(LLM, Base URL, Admin Token)은 환경 변수로 주입하는 것을 기본으로 한다.
    """
    parser = argparse.ArgumentParser(
        prog="agent-builder-qa-cli",
        description="Run Agent Builder QA E2E scenarios in CLI/CronJob mode.",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Run a single scenario directory (e.g., '01_simple_chat').",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios under the scenario root directory.",
    )
    parser.add_argument(
        "--scenario-root",
        type=str,
        default=None,
        help="Override scenario root directory (default: ./scenarios relative to project).",
    )
    return parser.parse_args(args=list(argv) if argv is not None else None)


def _resolve_scenario_selection(args: argparse.Namespace) -> tuple[Path, Optional[List[str]]]:
    """Resolve scenario root path and selection based on args and environment."""
    # Scenario root
    if args.scenario_root:
        root = Path(args.scenario_root).resolve()
    else:
        root = _default_scenario_root()

    # Selection precedence: CLI args > env(SCENARIO)
    scenario_names: Optional[List[str]] = None

    if args.all:
        scenario_names = None
    elif args.scenario:
        scenario_names = [args.scenario]
    else:
        env_scenario = os.getenv("SCENARIO")
        if env_scenario:
            if env_scenario == "all":
                scenario_names = None
            else:
                scenario_names = [env_scenario]

    if scenario_names is None and not args.all and not os.getenv("SCENARIO"):
        raise SystemExit(
            "No scenario specified. Use --scenario NAME, --all, or set SCENARIO env."
        )

    return root, scenario_names


def _load_config_from_env() -> dict:
    """Load required configuration from environment variables.

    Required:
      - LLM_PROVIDER (default: "adxp")
      - LLM_API_KEY
      - LLM_MODEL (default: "GIP/gpt-4.1")
      - BASE_URL
      - ADMIN_TOKEN
    """
    cfg = {
        "llm_provider": os.getenv("LLM_PROVIDER", "adxp"),
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_model": os.getenv("LLM_MODEL", "GIP/gpt-4.1"),
        "base_url": os.getenv("BASE_URL", ""),
        "admin_token": os.getenv("ADMIN_TOKEN", ""),
    }

    missing = []
    if not cfg["llm_api_key"]:
        missing.append("LLM_API_KEY")
    if not cfg["base_url"]:
        missing.append("BASE_URL")
    if not cfg["admin_token"]:
        missing.append("ADMIN_TOKEN")

    if missing:
        msg = "Missing required environment variables: " + ", ".join(missing)
        raise SystemExit(msg)

    return cfg


def _build_engine(cfg: dict) -> ScenarioEngine:
    """Construct a ScenarioEngine instance for CLI execution."""
    judge = LLMJudge(
        provider=cfg["llm_provider"],
        api_key=cfg["llm_api_key"],
        model=cfg["llm_model"],
    )

    def _on_step_update(message: str, level: str = "info") -> None:
        prefix = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERROR]"}.get(
            level, "[INFO]"
        )
        print(f"{prefix} {message}")

    return ScenarioEngine(
        base_url=cfg["base_url"],
        admin_token=cfg["admin_token"],
        judge=judge,
        on_step_update=_on_step_update,
    )


def _select_scenario_files(root: Path, scenario_names: Optional[List[str]]) -> List[Path]:
    """Discover scenario.yaml files and filter by scenario directory names if provided."""
    all_files = discover_scenario_files(root)
    if scenario_names is None:
        return all_files

    names = set(scenario_names)
    return [p for p in all_files if p.parent.name in names]


def _run_cli_scenarios(engine: ScenarioEngine, files: List[Path]) -> List[ScenarioResult]:
    """Run scenarios via ScenarioEngine and collect results."""
    results: List[ScenarioResult] = []

    for path in files:
        print(f"=== Running scenario: {path.parent.name} ===")
        try:
            result = engine.run_scenario(str(path))
        except Exception as e:  # noqa: BLE001
            sr = ScenarioResult(scenario_name=path.parent.name)
            sr.steps.append(
                StepResult(
                    step="EXECUTE_SCENARIO",
                    status=StepStatus.ERROR,
                    error=str(e),
                )
            )
            sr.final_status = StepStatus.ERROR
            print(f"[ERROR] Scenario failed with exception: {e}", file=sys.stderr)
            results.append(sr)
            continue

        results.append(result)
        status = result.final_status.value
        print(f"=== Scenario finished: {path.parent.name} -> {status} ===")

    return results


def _print_summary(results: List[ScenarioResult]) -> None:
    """Print per-scenario summary and overall stats to stdout."""
    print("\n=== Summary ===")

    total = len(results)
    passed = 0
    failed = 0
    errored = 0

    for r in results:
        status = r.final_status.value
        if r.final_status == StepStatus.PASS:
            passed += 1
        elif r.final_status == StepStatus.FAIL:
            failed += 1
        elif r.final_status == StepStatus.ERROR:
            errored += 1

        judge_reasons: list[str] = []
        for step in r.steps:
            jr: JudgeResult | None = step.judge_result
            if jr:
                judge_reasons.append(f"{jr.status.value}: {jr.reason}")

        if judge_reasons:
            reason_text = " | ".join(judge_reasons)
        else:
            reason_text = "-"

        print(f"- {r.scenario_name}: {status}  (judge={reason_text})")

    print(
        f"\nTotal: {total}, PASS: {passed}, FAIL: {failed}, ERROR: {errored}",
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI entrypoint for running QA scenarios."""
    args = _parse_args(argv)

    try:
        root, scenario_names = _resolve_scenario_selection(args)
    except SystemExit as e:
        # Propagate the same exit code/message.
        print(str(e), file=sys.stderr)
        return 1

    try:
        cfg = _load_config_from_env()
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1

    engine = _build_engine(cfg)

    files = _select_scenario_files(root, scenario_names)
    if not files:
        print(f"No scenarios found under: {root}", file=sys.stderr)
        return 1

    results = _run_cli_scenarios(engine, files)
    _print_summary(results)
    code = exit_code_for_results(results)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

