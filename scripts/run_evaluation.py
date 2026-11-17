import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.core.model import OllamaModelAdapter, OpenAICompatibleModelAdapter
from app.evaluation.runner import (
    EvaluationRunner,
    build_scripted_adapter,
    load_evaluation_tasks,
    summarize_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MiniHarness coding evaluations")
    parser.add_argument(
        "--mode",
        choices=["mock", "openai", "ollama"],
        default="mock",
    )
    parser.add_argument(
        "--suite",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "tasks",
    )
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--verification-rounds", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    if not 0 <= args.verification_rounds <= 3:
        raise SystemExit("--verification-rounds must be between 0 and 3")

    tasks = load_evaluation_tasks(args.suite)
    if args.task_id:
        selected = set(args.task_id)
        tasks = [task for task in tasks if task.spec.id in selected]
        if not tasks:
            raise SystemExit("No evaluation tasks matched --task-id")

    if args.mode == "openai":
        model_name = os.getenv("MINIHARNESS_LLM_MODEL", "").strip()
        if not model_name:
            raise SystemExit("MINIHARNESS_LLM_MODEL is required for openai mode")
        api_key = os.getenv("MINIHARNESS_LLM_API_KEY")
        base_url = os.getenv("MINIHARNESS_LLM_BASE_URL")

        def model_factory(workspace: Path):
            return OpenAICompatibleModelAdapter(
                model_name,
                api_key=api_key,
                base_url=base_url,
            )

        model_label = model_name
    elif args.mode == "ollama":
        ollama_model = os.getenv(
            "MINIHARNESS_OLLAMA_MODEL",
            "qwen2.5-coder:3b",
        )
        ollama_base_url = os.getenv(
            "MINIHARNESS_OLLAMA_BASE_URL",
            "http://127.0.0.1:11434/v1",
        )

        def model_factory(workspace: Path):
            return OllamaModelAdapter(
                ollama_model,
                base_url=ollama_base_url,
            )

        model_label = ollama_model
    else:
        model_label = "scripted-golden"

        def model_factory_for_task(task):
            return lambda workspace: build_scripted_adapter(task.load_plan())

    runner = EvaluationRunner()
    cases = []
    for trial in range(1, args.repetitions + 1):
        for task in tasks:
            if args.mode == "mock":
                factory = model_factory_for_task(task)
            else:
                factory = model_factory
            cases.append(
                runner.run_task(
                    task,
                    factory,
                    trial=trial,
                    verification_rounds=args.verification_rounds,
                )
            )

    report = summarize_report(
        cases,
        suite=args.suite.name,
        mode=args.mode,
        model=model_label,
    )
    output = args.output or (
        PROJECT_ROOT
        / "data"
        / "results"
        / f"evaluation_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "task_id",
                "trial",
                "task_success",
                "agent_completed",
                "agent_status",
                "failure_stage",
                "tool_call_count",
                "tool_names",
                "iterations",
                "elapsed_seconds",
                "total_tokens",
                "verification_rounds",
                "test_exit_code",
            ],
        )
        writer.writeheader()
        for case in cases:
            row = {
                field: getattr(case, field)
                for field in writer.fieldnames
            }
            row["tool_names"] = ";".join(case.tool_names)
            writer.writerow(row)

    print(
        f"{report.passed_count}/{report.task_count} tasks passed "
        f"({report.task_success_rate:.1%})"
    )
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")


if __name__ == "__main__":
    main()
