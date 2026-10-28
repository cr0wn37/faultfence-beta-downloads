"""Optional FaultFence model test launcher for macOS/Linux terminal.

Prompts for an OpenAI API key on the host without echoing or storing it.
Passes it only to the existing FaultFence CLI process via an environment variable.
This does not change Docker isolation or the provider gateway. Synthetic data only.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FaultFence opt-in OpenAI assessment (synthetic data only)")
    parser.add_argument("--project", type=Path, required=True, help="Directory containing your authorized agent's faultfence.json")
    parser.add_argument("--attack", default="AI-008", help="Attack ID, such as AI-008")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model ID supported by your provider account")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--allow-provider-data-egress", action="store_true", help="Acknowledge synthetic prompts leave your device for OpenAI")
    args = parser.parse_args(argv)

    if not args.allow_provider_data_egress:
        parser.error("Remote testing requires explicit --allow-provider-data-egress")
    if not (1 <= args.runs <= 20):
        parser.error("--runs must be between 1 and 20")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", args.model):
        parser.error("Invalid model ID")
    if not re.fullmatch(r"[A-Z0-9-]{2,40}", args.attack):
        parser.error("Invalid attack ID")
    project = args.project.expanduser().resolve()
    if not project.is_dir() or not (project / "faultfence.json").is_file():
        parser.error("--project must be a directory containing faultfence.json")

    kit_root = Path(__file__).resolve().parent
    cli = kit_root / ".venv" / "bin" / "faultfence"
    if not cli.is_file():
        parser.error("FaultFence is not installed in this kit; run bash setup.sh first")

    print("Synthetic/nonproduction data only. Your prompts will go to api.openai.com; API charges may apply.")
    print("Never use production banking credentials or confidential customer information.")
    key = getpass.getpass("OpenAI API key (hidden, not saved): ").strip()
    if not key:
        print("ERROR: OpenAI API key is required", file=sys.stderr)
        return 2
    env = dict(os.environ)
    env["OPENAI_API_KEY"] = key
    command = [
        str(cli), "test", "--project", str(project), "--mode", "model",
        "--attack", args.attack, "--model", args.model,
        "--runs", str(args.runs), "--allow-provider-data-egress",
    ]
    # No key in command arguments, console history, or any file written by this wrapper.
    # FaultFence itself handles provider gateway orchestration and its temp secrets.
    try:
        return subprocess.run(command, env=env, cwd=str(kit_root), check=False).returncode
    except OSError as exc:
        print(f"Cannot start FaultFence CLI: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        env.pop("OPENAI_API_KEY", None)
        del key


if __name__ == "__main__":
    raise SystemExit(main())
