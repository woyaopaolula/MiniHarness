import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OLLAMA_EXE = Path(sys.prefix) / "Library" / "bin" / "ollama.exe"
DATA_DIR = PROJECT_ROOT / "data" / "ollama"
MODEL_DIR = DATA_DIR / "models"
LOG_DIR = PROJECT_ROOT / "logs"
PID_FILE = DATA_DIR / "ollama.pid"
HOST = "127.0.0.1:11434"
DEFAULT_MODEL = os.getenv("MINIHARNESS_OLLAMA_MODEL", "qwen2.5-coder:3b")


def api_ready() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{HOST}/api/tags",
            timeout=2,
        ) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def wait_until_ready(seconds: int = 30) -> None:
    for _ in range(seconds * 2):
        if api_ready():
            return
        time.sleep(0.5)
    raise RuntimeError("Ollama did not become ready")


def start() -> None:
    if api_ready():
        print(f"Ollama is already running on {HOST}")
        return
    if not OLLAMA_EXE.exists():
        raise RuntimeError(f"Ollama executable not found: {OLLAMA_EXE}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["OLLAMA_HOST"] = HOST
    environment["OLLAMA_MODELS"] = str(MODEL_DIR)
    environment["OLLAMA_LLM_LIBRARY"] = "cuda_v12"
    stdout_path = LOG_DIR / "ollama-stdout.log"
    stderr_path = LOG_DIR / "ollama-stderr.log"
    with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open(
        "a",
        encoding="utf-8",
    ) as stderr:
        process = subprocess.Popen(
            [str(OLLAMA_EXE), "serve"],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=environment,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            ),
        )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    wait_until_ready()
    print(f"Ollama started on {HOST}")


def status() -> None:
    if not api_ready():
        print(f"Ollama is not running on {HOST}")
        return
    with urllib.request.urlopen(f"http://{HOST}/api/tags", timeout=5) as response:
        payload = json.load(response)
    models = [model["name"] for model in payload.get("models", [])]
    print(f"Ollama is running on {HOST}")
    print("Models: " + (", ".join(models) if models else "(none)"))


def pull(model: str) -> None:
    environment = os.environ.copy()
    environment["OLLAMA_HOST"] = HOST
    environment["OLLAMA_MODELS"] = str(MODEL_DIR)
    subprocess.run(
        [str(OLLAMA_EXE), "pull", model],
        env=environment,
        check=True,
    )


def stop() -> None:
    if not PID_FILE.exists() and not api_ready():
        print("Ollama is not running")
        return

    if PID_FILE.exists():
        process_id = int(PID_FILE.read_text(encoding="utf-8").strip())
        subprocess.run(
            ["taskkill", "/PID", str(process_id), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    # Ollama may detach its model runner outside the server's process tree.
    # Filter by this Conda environment's executable path to avoid touching an
    # unrelated user-installed Ollama process.
    stop_script = (
        f"$target = [System.IO.Path]::GetFullPath('{OLLAMA_EXE}'); "
        "Get-Process ollama -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -eq $target } | "
        "Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", stop_script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    PID_FILE.unlink(missing_ok=True)
    for _ in range(20):
        if not api_ready():
            print("Ollama stopped")
            return
        time.sleep(0.25)
    raise RuntimeError("Ollama did not stop")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage local Ollama for Qwen")
    parser.add_argument("command", choices=["start", "stop", "status", "pull"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    if args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    elif args.command == "pull":
        pull(args.model)
    else:
        status()


if __name__ == "__main__":
    main()
