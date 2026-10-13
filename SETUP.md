# VaccinePath Family SG — Build, Run and Evaluate

CA6117 Agentic AI in Healthcare — Group 16
Source repository: https://github.com/syzhang622/vaccinepath (this folder is a snapshot of `main` at submission).

VaccinePath is a long-running, stateful, self-triggering agent that keeps a child's vaccinations on Singapore's National Childhood Immunisation Schedule (NCIS) and monitors for warning signs after vaccination. All clinical judgements are made by a deterministic Python rule engine; the LLM only orchestrates tool calls and writes human-readable text. All data is synthetic.

## 1. What is in this folder

| Path | What it is |
|---|---|
| `vaccinepath/rules/` | Deterministic rule engine: `compute_schedule`, `detect_conflicts`, `pre_vaccination_screen`, `post_vaccination_escalate` |
| `vaccinepath/tools.py` | The 14 `vp_*` tools the agent can call (all limited to the local state file) |
| `vaccinepath/agent/` | Thread goal, wake-up prompt, and the deny-by-default agent profile |
| `vaccinepath/guidance.py` | Keyword retrieval over official KKH / HealthHub excerpts (grounding) |
| `vaccinepath/ui/` | Six-page Streamlit interface (parent + clinician console) |
| `vaccinepath/data/` | NCIS table transcribed from the MOH PDF; synthetic demo family |
| `tests/` | 94 automated tests (rules, tools, UI, agent setup) |
| `scripts/` | Setup, start/stop, smoke test, two-wake-up demo |
| `docs/` | Rule-engine spec, evaluation report, demo script, official sources, screenshots |

## 2. Requirements

| Dependency | Version used | Notes |
|---|---|---|
| Python | 3.12 (3.13 also tested) | installed automatically by uv |
| uv | 0.11 or newer | Python package manager: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | any recent | needed by `scripts/setup.sh` to fetch DeerFlow |
| DeerFlow | commit `1e3bfa09d4e31e02d109ef2f4b41895dc89a78fe` (2026-09-20) | agent runtime; fetched and pinned by `scripts/setup.sh`, not modified |
| pydantic | 2.13.5 | pinned in `uv.lock` |
| streamlit | 1.64.0 | pinned in `uv.lock` |
| langchain-core | 1.6.3 | pinned in `uv.lock` |
| requests | 2.34.2 | pinned in `uv.lock` |
| python-dateutil | 2.9.0 | pinned in `uv.lock` |
| pytest | 9.1.1 | dev dependency |
| DeepSeek API key | — | external service, see §4; the model is replaceable via `deer-flow/config.yaml` |

OS: macOS and Linux. On Windows use WSL (the scripts are bash).

## 3. Quick check without any API key (rule engine + UI tests)

```bash
cd vaccinepath            # this folder
uv sync
uv run pytest             # expected: 94 passed
```

This runs the full automated suite: NCIS data integrity, the four rule functions (positive, negative and boundary cases), tool idempotency and reminder limits, retrieval, and headless rendering of all six UI pages. No network, no key, no DeerFlow needed.

## 4. Full agent (needs a DeepSeek key)

```bash
# 1. fetch DeerFlow (pinned commit), install its dependencies, generate config
DEEPSEEK_API_KEY=sk-xxxx scripts/setup.sh

# 2. start the agent gateway on http://localhost:8001 (auth disabled for local evaluation)
scripts/gateway.sh start

# 3. smoke test: thread + scheduled task + manual trigger; prints "PHASE 0 PASS"
scripts/phase0_smoke.sh

# 4. scripted two-wake-up demo: reset data → wake-up 1 → simulated parent actions → wake-up 2
scripts/phase2_demo.sh    # prints "PHASE 2 PASS" and the resulting state

# 5. web interface on http://localhost:8501
scripts/ui.sh
```

Get a key at https://platform.deepseek.com (a few dollars covers many runs). To use another OpenAI-compatible or Anthropic model, edit the `models:` entry in `deer-flow/config.yaml`; no clinical rule depends on the model.

Stop: `scripts/gateway.sh stop`, `pkill -f "streamlit run"`. Reset demo data: `scripts/agent_setup.sh --reset`.

## 5. Walking through the demo in the UI

Follow `docs/demo_script.md` (eight steps, matches the submitted recording):
Profiles (Priya's overseas records flagged) → **Run next check now** (wake-up 1) → Tasks: pre-vaccination screening with one "yes" → mark influenza as vaccinated → Post-vaccination Check-in: 41.3 °C + seizure → URGENT → Clinical Review: approve Priya → **Run next check now** (wake-up 2, summary refers to what happened in between) → Audit & Runs.

Each wake-up takes 15–40 seconds depending on the model.

## 6. Where the evaluation evidence is

- `docs/evaluation_report.md` — full test tables, live-run evidence, defects found and their regression tests
- `docs/rule_engine.md` — rule-engine spec and the official sources behind every threshold
- `docs/sources/` — verbatim excerpts from the MOH NCIS, KKH and HealthHub pages used for grounding
- `docs/screenshots/` — the nine screenshots used in the report
- `recordings/` (repository) / `VaccinePath_Demo.mp4` (this submission) — two-minute demo recording

## 7. Known limitations

Synthetic data only; no connection to NIR, NEHR or clinics; reminders go to a mock inbox; single family, single thread; escalation thresholds follow public KKH/HealthHub guidance and are not clinically validated. See report §5.2.
