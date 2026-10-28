# FaultFence macOS / Linux add-on — experimental

These files are **additions** to the original `v0.8.0-beta.2` release.
No existing Windows scripts, Docker config, wheel, policies, 17 attacks or reports have changed.

## Requirements
- macOS or Linux with Bash, Python **3.11+**, and working `python3 -m venv`.
- Docker Desktop (macOS, including Apple Silicon) or Docker Engine/Desktop (Linux), started and accessible to your user.
- Internet connection to download Python dependencies and build the pinned Docker image.
- Authorized **synthetic/nonproduction** agent and tools only; never connect live financial systems.

## Install / run an offline sample
Open a terminal in the extracted `FaultFence-Testing-Kit` folder:

```bash
bash setup.sh
bash try_sample.sh
```

The scripts create a **local** `.venv` (not shipped), install the bundled wheel, build the **same** Docker image and run the existing sample via Docker with network disabled. Reports remain local in `sample-agent/faultfence_reports/batches/`.

## Integrate your own Python agent (requires an adapter)

```bash
.venv/bin/faultfence init --project "$HOME/my-agent"
.venv/bin/faultfence validate --project "$HOME/my-agent"
.venv/bin/faultfence attacks
.venv/bin/faultfence test --project "$HOME/my-agent" --mode offline --attack AI-008 --runs 1
```

Edit `faultfence_adapter.py`, `faultfence_tool_mappings.json`, `faultfence_policy.json` and `faultfence.json` for **actual** tools first. `init` scaffolds only. An attack can be skipped when the adapter lacks required capabilities.

## Free model-attack applicability preview (no OpenAI key or API calls)

```bash
.venv/bin/python RUN_MODEL_ALL_UNIX.py \
  --project multi-tool-faultfence-agent --attack all --runs 1 \
  --authorized-resource invoice_100 --authorized-quantity 2 \
  --authorized-max-amount 100 --authorized-amount 100 \
  --authorized-currency INR --authorized-units 4 --units-per-pack 2 \
  --requests-file MODEL_BATCH_REQUESTS.example.json \
  --max-agent-runs 11 --plan
```

With the provided seven-tool mapping, this should print **11 applicable / 6 skipped**. This previews mapping applicability only, not exploit success or runtime compatibility.

## Optional OpenAI-backed tests (charges may apply)

Only for a compatible model adapter with synthetic prompts, and with a working Docker setup. Run *without* `--plan` and add `--allow-provider-data-egress` after reviewing the attack plan. This prompts for an API key without echoing it. Run an individual attack with:

```bash
.venv/bin/python RUN_MODEL_UNIX.py --project multi-tool-faultfence-agent \
  --attack AI-008 --model gpt-4.1-mini --runs 1 --allow-provider-data-egress
```

For the batch, use `RUN_MODEL_ALL_UNIX.py` with the same preview parameters, drop `--plan`, and add `--allow-provider-data-egress`. It asks for confirmation before starting. `--max-agent-runs` is **not a spend cap**.

## Reports
Import `.assessment.json` at `https://faultfence.com/dashboard/assessments` (sign-in required). Preview is local; cloud save requires a separate explicit action. Review content for sensitive information first.

## Compatibility caveat

- Linux: CLI and plan can be checked without Docker; Docker-based offline execution needs Docker Engine and isolation testing.
- macOS: Hosted CI can verify installation, CLI and a plan **without a Mac or Docker**. This does **not** establish Docker/Apple Silicon execution. Label macOS Docker testing **experimental** until validated on a real Mac with Docker Desktop.
- The included `SHA256SUMS.txt` covers all **original** release files and is deliberately unchanged. Verify `SHA256SUMS_UNIX_ADDONS.txt` separately for the new files.
