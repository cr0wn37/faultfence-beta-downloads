"""FaultFence model-backed all-applicable-attacks coordinator (macOS/Linux terminal).

ADD-ONLY companion for the verified FaultFence v0.8.0 public Testing Kit.
Runs each eligible attack through the *existing* single-attack CLI/Docker gateway;
validates reports and exports a consolidated .assessment.json for the web dashboard.
Never imports a customer's adapter on the host. Never uploads a report automatically.
No production financial/payment credentials or non-synthetic records permitted.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Only installed, previously validated FaultFence modules are imported. There is
# no direct provider API call and no customer adapter import in this coordinator.
from faultfence.batch import _attack_for_applicability, _collect, _new_reports
from faultfence.batch_export import export_assessment_bundle
from faultfence.capabilities import AgentCapabilityProfile, FEATURE_FINANCIAL_SANDBOX_ENFORCED
from faultfence.cli import load_config, validate_project
from faultfence.tool_mapping import load_tool_mapping
from faultfence.validation import OUTCOMES
from run_local_assessment import BUILTIN_ATTACKS

MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,99}\Z")
AUTH_FIELDS = ("authorized_resource", "authorized_max_amount", "authorized_currency",
               "authorized_amount", "authorized_quantity", "authorized_units", "units_per_pack")


def parser_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run each applicable FaultFence catalog attack against your synthetic, local model-backed agent."
    )
    parser.add_argument("--project", required=True, type=Path, help="Local agent integration directory")
    parser.add_argument("--attack", choices=["all"], default="all", help="All statically applicable attacks")
    parser.add_argument("--runs", type=int, choices=[1, 2, 3], default=1,
                        help="Runs per applicable attack (model beta safety cap: 1-3)")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--request", default=None,
                        help="Synthetic user instruction; applied to every applicable attack unless overridden")
    parser.add_argument("--requests-file", type=Path, default=None,
                        help="Optional JSON mapping attack IDs to attack-specific legitimate synthetic requests")
    parser.add_argument("--max-agent-runs", type=int, default=None,
                        help="Optional ceiling on total agent runs; NOT a currency/API spend cap")
    parser.add_argument("--allow-provider-data-egress", action="store_true",
                        help="Acknowledge synthetic prompts leave local Docker for OpenAI")
    parser.add_argument("--plan", action="store_true", help="List eligible attacks without any API call or key prompt")
    for field in AUTH_FIELDS:
        parser.add_argument("--" + field.replace("_", "-"), default=None)
    args = parser.parse_args(argv)
    if args.max_agent_runs is not None and args.max_agent_runs < 1:
        parser.error("--max-agent-runs must be a positive integer")
    if args.request is not None and (not args.request.strip() or len(args.request) > 4000):
        parser.error("--request must contain 1-4000 characters of synthetic text")
    if not MODEL_RE.fullmatch(args.model):
        parser.error("Invalid OpenAI model identifier")
    if not args.plan and not args.allow_provider_data_egress:
        parser.error("Real model testing requires explicit --allow-provider-data-egress")
    return args




def read_request_overrides(path: Path | None, catalog: set[str]) -> dict[str, str]:
    """Optional per-attack *legitimate* tasks; JSON is data, not executable code."""
    if path is None:
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("--requests-file must be a regular JSON file, not a symlink")
    if path.stat().st_size > 64 * 1024:
        raise ValueError("--requests-file is too large (64 KB maximum)")
    mapping = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(mapping, dict):
        raise ValueError("--requests-file must be a JSON object mapping attack IDs to requests")
    bad = set(mapping) - catalog
    if bad:
        raise ValueError("Unknown attack ID(s) in --requests-file: " + ", ".join(sorted(bad)))
    for key, val in mapping.items():
        if not isinstance(val, str) or not val.strip() or len(val) > 4000:
            raise ValueError(f"Request for {key} must be 1-4000 characters of synthetic text")
    return mapping

def prepare(args: argparse.Namespace) -> tuple[Any, list[tuple[str, bool, list[str]]], str, str]:
    config = load_config(args.project.expanduser())
    validate_project(config, verbose=True)  # static only; no import of customer's code
    request = args.request if args.request is not None else config.request
    if not isinstance(request, str) or not request.strip() or len(request) > 4000:
        raise ValueError("Supply a synthetic request (1-4000 chars) or set a valid project request")
    reg = load_tool_mapping(config.mappings)
    capabilities = AgentCapabilityProfile.from_mapping_registry(
        reg, features=[FEATURE_FINANCIAL_SANDBOX_ENFORCED]
    )
    # The same applicability precheck used by the built-in offline batch.
    eligibility: list[tuple[str, bool, list[str]]] = []
    for attack_id, factory in sorted(BUILTIN_ATTACKS.items()):
        result = _attack_for_applicability(factory, args).check_applicability(capabilities)
        eligibility.append((attack_id, result.applicable, list(result.reasons)))
    return config, eligibility, request, args.model


def ensure_paths(output: Path) -> Path:
    if output.is_symlink():
        raise ValueError("Report output cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    batches = output / "batches"
    if batches.is_symlink():
        raise ValueError("Batch output cannot be a symlink")
    batches.mkdir(parents=True, exist_ok=True)
    return batches


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError("Refusing a symlink batch summary path")
    with path.open("x", encoding="utf-8") as out:
        json.dump(summary, out, ensure_ascii=False, indent=2)
        out.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = parser_args(argv)
    root = Path(__file__).resolve().parent
    cli = root / ".venv" / "bin" / "faultfence"
    config, eligibility, request, model = prepare(args)
    request_overrides = read_request_overrides(args.requests_file, set(BUILTIN_ATTACKS))
    available = [a for a, eligible, _ in eligibility if eligible]
    print("\nMODEL-BACKED BATCH PLAN |", len(eligibility), "catalog attacks")
    print("  Agent:", config.root)
    print("  Model:", model)
    for attack_id, eligible, reasons in eligibility:
        if eligible:
            print(f"  RUN  {attack_id} x {args.runs}")
        else:
            print(f"  SKIP {attack_id}: {'; '.join(reasons) or 'not applicable to mapped capabilities'}")
    total_runs = len(available) * args.runs
    print(f"  Total applicable: {len(available)}; total agent runs: {total_runs}")
    if request_overrides:
        print("  Per-attack legitimate request overrides:", ", ".join(sorted(request_overrides)))
    if args.max_agent_runs is not None:
        print("  Maximum permitted agent runs:", args.max_agent_runs)
        if total_runs > args.max_agent_runs:
            print(f"  REFUSED: {total_runs} planned runs exceed --max-agent-runs={args.max_agent_runs}", file=sys.stderr)
            return 2
    print("  Actual provider calls and charges may exceed run count; no automatic spend cap.")
    if args.plan:
        print("  PLAN ONLY — no Docker or model request made.")
        return 0
    if not available:
        print("No applicable attacks. Review your actual tool mappings/policy.", file=sys.stderr)
        return 2
    if not cli.is_file():
        print("Missing installed CLI; run bash setup.sh in this kit first.", file=sys.stderr)
        return 2
    print("\nSynthetic/nonproduction testing ONLY. Prompts leave local environment via the OpenAI gateway.")
    print("No live payment APIs, banking credentials, customer data or unrestricted financial tools.")
    print("Each attack runs separately with its own restricted Docker gateway; there is no parallel execution.")
    answer = input(f"Type RUN to authorize up to {len(available) * args.runs} agent runs (API charges may apply): ")
    if answer.strip() != "RUN":
        print("Cancelled; no API request sent.")
        return 2
    key = getpass.getpass("OpenAI API key (hidden; not saved by this launcher): ").strip()
    if not key:
        print("No key supplied; cancelled.", file=sys.stderr)
        return 2
    # The original FaultFence CLI reads OPENAI_API_KEY only from its host process,
    # and its controlled sidecar mounts the secret into the gateway only.
    environment = dict(os.environ)
    environment["OPENAI_API_KEY"] = key
    del key
    batch_id = "batch-" + uuid.uuid4().hex[:16]
    summary: dict[str, Any] = {
        "schema_version": "1.0", "kind": "faultfence_attack_batch_summary",
        "batch_id": batch_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_id": load_tool_mapping(config.mappings).agent_id,
        "mode": "model", "model": model, "runs_per_attack": args.runs,
        "note": "Real model reasoning, synthetic financial tools only. Each attack uses a separate restricted Docker OpenAI gateway. Provider prompts leave the device; API charges may apply. No production exploit established.",
        "attacks": {},
    }
    try:
        out_dir = config.output_dir
        batches_dir = ensure_paths(out_dir)
        failed = False
        abort_id: str | None = None
        for attack_id, applicable, reasons in eligibility:
            if not applicable:
                summary["attacks"][attack_id] = {
                    "status": "SKIPPED_NOT_APPLICABLE", "reason": reasons,
                    "counts": {k: 0 for k in sorted(OUTCOMES)}, "reports": [],
                }
                continue
            if abort_id:
                summary["attacks"][attack_id] = {
                    "status": "NOT_RUN_BATCH_STOPPED", "reason": [f"Stopped after {abort_id} failed"],
                    "counts": {k: 0 for k in sorted(OUTCOMES)}, "reports": [],
                }
                continue
            before = {p.name for p in out_dir.glob("*.json") if p.is_file()}
            command = [
                str(cli), "test", "--project", str(config.root),
                "--mode", "model", "--attack", attack_id,
                "--model", model, "--runs", str(args.runs),
                "--request", request_overrides.get(attack_id, request), "--allow-provider-data-egress",
            ]
            for attr in AUTH_FIELDS:
                value = getattr(args, attr)
                if value is not None:
                    command += ["--" + attr.replace("_", "-"), str(value)]
            print(f"\n=== MODEL ATTACK {attack_id} | {args.runs} run(s) ===", flush=True)
            try:
                code = subprocess.run(command, cwd=str(root), env=environment, check=False).returncode
                result = _collect(_new_reports(out_dir, before), attack_id, args.runs, out_dir)
                if code != 0:
                    result["status"] = "INCOMPLETE"
                    result["classification"] = "INCOMPLETE"
                    result["errors"].append(f"isolated model launcher exited {code}")
            except (OSError, subprocess.SubprocessError) as exc:
                result = {
                    "status": "INCOMPLETE", "classification": "INCOMPLETE",
                    "counts": {k: 0 for k in sorted(OUTCOMES)}, "reports": [],
                    "errors": [f"model launcher error ({type(exc).__name__})"],
                }
            summary["attacks"][attack_id] = result
            print("  Result:", result["classification"], flush=True)
            if result["status"] != "COMPLETE":
                failed = True
                abort_id = attack_id
                print("  STOPPED on execution/report failure to avoid repeated unexpected API charges.", flush=True)
        entries = summary["attacks"]
        summary["selected_attacks"] = sum(x for _, x, _ in eligibility)
        summary["skipped_attacks"] = sum(not x for _, x, _ in eligibility)
        summary["completed_attacks"] = sum(e.get("status") == "COMPLETE" for e in entries.values())
        summary["outcomes"] = {
            k: sum(e.get("counts", {}).get(k, 0) for e in entries.values())
            for k in sorted(OUTCOMES)
        }
        summary["status"] = "INCOMPLETE" if failed else "COMPLETE"
        summary_path = batches_dir / f"{batch_id}.json"
        write_summary(summary_path, summary)
        print("\nALL MODEL ATTACKS SUMMARY:")
        print("  Result:", summary["status"])
        print("  Completed:", summary["completed_attacks"], "/", summary["selected_attacks"])
        print("  Skipped not applicable:", summary["skipped_attacks"])
        print("  Attack run outcomes:", summary["outcomes"])
        print("  Local summary:", summary_path)
        if failed:
            print("  No consolidated assessment exported: model execution incomplete.")
            return 2
        dest = batches_dir / f"{batch_id}.assessment.json"
        export_assessment_bundle(summary, out_dir, dest)
        print("  IMPORT THIS FILE INTO /dashboard/assessments:", dest)
        print("  No automatic cloud upload; inspect for sensitive data before optional save.")
        return 0
    finally:
        environment.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled: a report may exist for the interrupted attack. No consolidated bundle.", file=sys.stderr)
        raise SystemExit(130)
    except (ValueError, OSError, KeyError, ImportError, json.JSONDecodeError) as exc:
        print(f"Model-batch preflight/export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
