import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import build_application_components


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one MiniHarness coding task synchronously"
    )
    parser.add_argument("prompt", help="Coding task for the agent")
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Workspace root; defaults to MINIHARNESS_WORKSPACE_ROOT",
    )
    parser.add_argument("--task-id")
    args = parser.parse_args()

    components = build_application_components(workspace_root=args.workspace)
    try:
        result = components.task_service.run(
            args.prompt,
            task_id=args.task_id,
        )
        task = components.repository.get_task(result.task_id or "")
        events = components.repository.list_events(task.id)
        tool_calls = components.repository.list_tool_calls(task.id)
    finally:
        components.close()

    print(f"task_id: {task.id}")
    print(f"status: {task.status}")
    print(f"agent_status: {result.status}")
    print(f"stop_reason: {result.stop_reason}")
    print(f"iterations: {result.iterations}")
    print(f"tool_calls: {result.tool_call_count}")
    print(f"events_persisted: {len(events)}")
    print(f"tool_records_persisted: {len(tool_calls)}")
    if result.answer:
        print(f"answer: {result.answer}")
    if result.error:
        print(f"error: {result.error}")


if __name__ == "__main__":
    main()
