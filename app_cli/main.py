from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from core.engine import (
    exit_code_for_results,
    print_results,
    run_scenarios_from_root,
)


def _default_scenario_root() -> Path:
    """Return the default scenarios directory."""
    here = Path(__file__).resolve()
    return here.parent.parent / "scenarios"


def _parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the app_cli entrypoint."""
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


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI entrypoint for running QA scenarios."""
    args = _parse_args(argv)

    try:
        root, scenario_names = _resolve_scenario_selection(args)
    except SystemExit as e:
        # Propagate the same exit code/message.
        print(str(e), file=sys.stderr)
        return 1

    results = run_scenarios_from_root(root=root, scenario_names=scenario_names)
    if not results:
        print(f"No scenarios found under: {root}", file=sys.stderr)
        return 1

    print_results(results)
    code = exit_code_for_results(results)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

