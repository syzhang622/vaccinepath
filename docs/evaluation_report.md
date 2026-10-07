# VaccinePath Prototype Evaluation Report

## 1. Purpose and scope

This document evaluates the frozen VaccinePath Family SG prototype against the CA6117 expectations for a working agentic healthcare workflow. The evaluation focuses on:

- correctness of the deterministic vaccination rules;
- safe routing of uncertain or clinically significant cases;
- state and memory across scheduled runs;
- tool use, idempotency, reminder limits, and auditability;
- the observable end-to-end workflow through the DeerFlow agent and Streamlit interface.

This is a prototype evaluation, not a clinical validation. All profiles and events are synthetic. The prototype is not connected to the National Immunisation Registry, NEHR, a clinic, or a real notification service.

## 2. System under test

| Item | Evaluated configuration |
|---|---|
| Repository version | `project_fix` working tree based on `32dc039` (final commit pending) |
| Evaluation date | 28 September 2026 |
| Operating environment | macOS Darwin 24.6.0, arm64 |
| Python | 3.13.9 |
| Agent framework | DeerFlow with a reused persistent thread and scheduled wake-ups |
| Language model | DeepSeek Chat through an OpenAI-compatible API |
| Rule engine | Deterministic Python functions with Pydantic inputs and outputs |
| Interface | Six-page Streamlit application |
| Prototype storage | Local JSON store with file locking |
| Guidance retrieval | Deterministic keyword retrieval over curated KKH and HealthHub excerpts |
| Agent authority | Custom `vaccinepath` profile; only the VaccinePath tool group is enabled |

The rule engine, rather than the language model, determines schedule status, record conflicts, pre-vaccination screening outcomes, and post-vaccination escalation. The language model coordinates tool calls and produces parent- or clinician-facing text from tool outputs.

## 3. Evaluation methodology

The prototype was evaluated at four levels:

1. **Source-data tests** check that the structured NCIS data matches the source schedule and preserves combination-vaccine and catch-up information.
2. **Rule-unit tests** exercise schedule computation, conflict detection, pre-vaccination screening, and post-vaccination escalation with positive, negative, and boundary inputs.
3. **Tool and UI integration tests** check persistence, idempotency, reminder limits, retrieval logging, human-review routing, and headless rendering of all six Streamlit pages.
4. **Live end-to-end tests** use the configured DeerFlow gateway and DeepSeek API to verify persistent-thread execution and two consecutive VaccinePath wake-ups.

The main reproducibility commands were:

```bash
uv run pytest
scripts/phase0_smoke.sh
scripts/phase2_demo.sh
```

## 4. Automated test results

The complete automated suite passed without failures:

```text
........................................................................ [ 76%]
......................                                                   [100%]
94 passed
```

| Test suite | Collected tests | Result | Primary concern |
|---|---:|---|---|
| `test_agent_setup.py` | 2 | Pass | Custom-agent least privilege and explicit run binding |
| `test_compute_schedule.py` | 16 | Pass | NCIS schedule status, catch-up rules, age/sex boundaries |
| `test_detect_conflicts.py` | 12 | Pass | Invalid, duplicate, early, extra, and overseas records |
| `test_ncis_data.py` | 4 | Pass | Integrity of the structured NCIS source data |
| `test_post_vaccination_escalate.py` | 26 | Pass | CONTINUE, WARN, URGENT, temperature and symptom boundaries |
| `test_pre_vaccination_screen.py` | 7 | Pass | CLEAR versus mandatory professional review |
| `test_tools.py` | 14 | Pass | Tool output, blocking, input isolation, reminders, retrieval |
| `test_ui.py` | 13 | Pass | Six-page rendering and critical parent/clinician interactions |
| **Total** | **94** | **Pass** | — |

### 4.1 Representative rule and integration cases

| ID | Component and input | Expected outcome | Observed outcome | Result | Evidence |
|---|---|---|---|---|---|
| SCH-01 | Newborn with no records | BCG and HepB due; later doses upcoming | Expected statuses and dates returned | Pass | `test_newborn_all_upcoming_except_birth_doses` |
| SCH-02 | Child with records through six months | Recorded doses completed; later doses upcoming | Records matched to the correct dose sequence | Pass | `test_on_schedule_child_at_7_months_has_completed_and_upcoming` |
| SCH-03 | Dose passes the configured 30-day grace period | Status becomes overdue and requires clinician confirmation | Boundary changes from due to overdue on the next day | Pass | `test_overdue_uses_30_day_grace_and_requires_clinician_confirmation` |
| SCH-04 | Late DTaP/IPV/Hib dose with no NCIS catch-up interval | Do not invent a date; return `needs_clinician` | No due date generated; clinician review required | Pass | `test_no_catch_up_rule_in_pdf_means_needs_clinician` |
| SCH-05 | Late MMR dose 1 | Apply the documented minimum four-week interval | Dose 2 moved to dose 1 plus four weeks | Pass | `test_mmr_catch_up_interval_4_weeks_after_late_dose1` |
| REC-01 | Vaccination dates before birth and after the evaluation date | Blocking validation errors | `before_birth` and `future_date` returned | Pass | `test_before_birth_and_future_are_blocking_errors` |
| REC-02 | Same antigens recorded twice on the same day | Duplicate errors and scheduling blocked | Four antigen-level duplicate errors returned | Pass | `test_same_day_duplicate` |
| REC-03 | Unverified overseas combination-vaccine record | Preserve the record but require professional review | `overseas_unverified` review issue returned | Pass | `test_unverified_overseas_record_needs_review` |
| REC-04 | An impossible record is present when the agent requests a schedule | Return no schedule items and route the data error for review | `blocked=true`, empty items, and a blocking audit entry returned | Pass | `test_check_schedule_is_blocked_by_impossible_record` |
| SCR-01 | All six screening answers are “no” | `CLEAR`, while retaining the disclaimer | CLEAR with no flags | Pass | `test_all_no_is_clear` |
| SCR-02 | A previous serious reaction is reported | Mandatory professional review | Flag retained and review required | Pass | `test_previous_serious_reaction_requires_review` |
| SCR-03 | An answer is uncertain | Never clear automatically; mark incomplete | Review required and `incomplete=true` | Pass | `test_unsure_is_never_clear` |
| MON-01 | Mild expected reaction with short-duration fever | Continue monitoring and check again in 24 hours | `CONTINUE`, no escalation trigger | Pass | `test_expected_mild_reaction_continues` |
| MON-02 | Fever continues for 49 hours | Recommend medical review | `WARN` with the duration trigger | Pass | `test_fever_more_than_2_days_warns` |
| MON-03 | Seizure and temperature of 41.5°C | Urgent assessment takes priority while retaining other triggers | `URGENT`; urgent and warning triggers listed | Pass | `test_urgent_also_lists_warn_triggers` |
| MON-04 | Infant under three months with temperature of 38.0°C | Urgent assessment | `URGENT` with infant-fever trigger | Pass | `test_infant_under_3_months_38_is_urgent` |
| TOL-01 | Create the same vaccination task twice | Create once and return the existing task thereafter | No duplicate task created | Pass | `test_create_tasks_idempotent` |
| TOL-02 | Send more than three reminders | Stop at the configured maximum and return the task as exhausted | Fourth reminder blocked | Pass | `test_send_reminder_appends_disclaimer_and_respects_max` |
| TOL-03 | Attempt to remind the same task twice during one wake-up | Only the first notification is sent | Second call rejected as `already_reminded_this_run`; count remains one | Pass | `test_send_reminder_enforces_one_per_child_task_per_wake` |
| SEC-01 | Caregiver free text contains instructions to ignore rules and read secrets | Do not expose the string to the model; structured safety fields still drive evaluation | Free text withheld and the structured seizure still produced `URGENT` | Pass | `test_get_child_withholds_caregiver_free_text_from_agent` |
| SEC-02 | Create a thread and scheduled task | Both must use the least-privilege custom agent | Both request bodies carry `assistant_id=vaccinepath` | Pass | `test_setup_binds_thread_and_schedule_to_custom_agent` |
| RAG-01 | Retrieve guidance for seizure and emergency | Return a verbatim HealthHub excerpt and log the source | Correct excerpt and `retrieved:` audit entry returned | Pass | `test_get_guidance_returns_verbatim_quotes_and_logs_retrieved` |
| RAG-02 | Ask retrieval for an uncovered catch-up topic | Return no excerpt rather than a misleading quotation | Empty result with a “do not quote” instruction | Pass | `test_get_guidance_returns_nothing_for_topics_the_corpus_does_not_cover` |
| UI-01 | Render every Streamlit page headlessly | No page raises an exception | Profiles, timeline, tasks, check-in, review, and logs all render | Pass | `test_every_page_renders_without_exception` |
| UI-02 | Submit 41.5°C and seizure through the check-in page | Show immediate emergency guidance and create a review task | Urgent UI response and persisted review task | Pass | `test_checkin_urgent_routes_to_review` |
| UI-03 | Clinician approves an overseas-record review | Verify selected record and persist the human decision | Record verified; `approved` written to audit log | Pass | `test_review_queue_approve_marks_done_and_verifies_record` |
| UI-04 | Timeline contains an impossible future record | Stop before rendering a schedule and explain the block | Blocking error shown and schedule metrics withheld | Pass | `test_timeline_blocks_impossible_records` |

## 5. Live agent evaluation

### 5.1 Phase 0: gateway, scheduler, and persistent state

The Phase 0 smoke test completed with `PHASE 0 PASS`. A first message instructed the model to answer `PONG`. A scheduled wake-up was then triggered in the same thread and asked the model to return `WAKE` plus its previous answer. The response was `WAKE PONG`, and the thread message count increased from two to four. This demonstrates that the scheduled task reused the same thread and retained its earlier state across the wait.

### 5.2 Phase 2: two-wake-up VaccinePath workflow

The full demo completed with `PHASE 2 PASS`.

| Observation | Wake-up 1 | Wake-up 2 |
|---|---:|---:|
| Run status | Success | Success |
| Approximate runtime | 18 seconds | 26 seconds |
| Tool calls | 17 | 20 |
| Children checked | Mei, Kai, Priya | Mei, Kai, Priya |

During the first wake-up, the agent:

- ran record and schedule checks for all three children;
- created four vaccination tasks for Mei and four for Priya;
- sent one bundled reminder to each affected child;
- left Kai undisturbed because no action was required;
- bundled Priya’s early MMR and unverified overseas records into one professional-review request;
- completed the run with a logged wake-up summary.

Between wake-ups, the simulation marked Mei’s influenza task complete and submitted a post-vaccination check-in containing a seizure, a temperature of 41.3°C, fever despite medication, and parental concern.

During the second wake-up, the agent:

- recognised that Mei’s influenza vaccination had been completed;
- evaluated the new check-in as `URGENT` without changing the rule-engine decision;
- retrieved the HealthHub quotation “Has a fit (seizure or convulsion)”;
- sent a parent message instructing immediate attendance at the Children’s Emergency and routed the case for review;
- retained Mei’s overdue booster items without creating duplicate tasks;
- sent Priya a repeat reminder rather than creating a new set of tasks;
- completed a second state-aware summary.

The resulting prototype state contained:

| Evidence | Observed value |
|---|---:|
| Completed wake-ups | 2 |
| Notifications | 4 |
| Professional-review tasks | 2 |
| Audit entries | 29 |
| Audit actors | 13 rule-engine, 14 agent, 2 parent |
| Mei check-in result | `URGENT` |
| Mei review reasons | 5 |
| Priya review reasons | 11, bundled into one review task |

The live notification for Mei included the retrieved HealthHub quotation and the fixed disclaimer. Priya’s second notification was explicitly labelled as a repeat reminder. The corresponding visual evidence is available in `docs/screenshots/02_第一次唤醒摘要.jpg`, `docs/screenshots/04_打卡URGENT_引用HealthHub原句.jpg`, `docs/screenshots/07_第二次唤醒摘要_已唤醒2次.jpg`, and `docs/screenshots/09_agent唤醒记录_工具调用.jpg`.

### 5.3 Post-review live verification

After the safety fixes, the complete two-wake demo was rerun against the DeepSeek API and ended with `PHASE 2 PASS`. Wake-up 1 (`9425e7da-a517-48b1-9911-83fe2cde6a83`) completed in approximately 18 seconds with 18 application-tool calls. After the synthetic parent event, wake-up 2 (`0b4f56a6-59b6-42a5-9448-69c0dac72d26`) completed in approximately 22 seconds with 17 calls. The final state contained two completed wake-ups, four notifications, two professional-review tasks, 27 audit entries, and an `URGENT` check-in with the four expected triggers.

Every observed application call in both runs was a `vp_*` call. Gateway assembly logged `Create Agent(vaccinepath)`, `subagent_enabled: False`, `has_memory=False`, 14 configured VaccinePath tools, zero MCP tools, and zero ACP tools. No web, shell, browser, general file-read/write, skill, plugin, or subagent call occurred.

The six English Streamlit routes (`/`, `/timeline`, `/tasks`, `/checkin`, `/review`, `/logs`) were then rendered in a real browser. All six loaded successfully and a visible-text scan found no Chinese characters. The current local browser has been left on the English **Audit & Agent Runs** page for manual inspection.

## 6. Safety and governance evaluation

| Risk or requirement | Control evaluated | Evidence and result |
|---|---|---|
| Hallucinated vaccination intervals | The engine must not infer an interval absent from the NCIS source | SCH-04 passed: no date was generated and the case was routed to a clinician |
| Unsupported retrieval | Retrieval must not attach an unrelated quotation | RAG-02 passed: uncovered schedule/catch-up queries returned no excerpt |
| Model overriding clinical rules | Escalation and screening decisions are returned by deterministic tools | MON-03, SCR-02, and the Phase 2 urgent check-in produced the required escalation |
| Over-permissioning | The LLM must not inherit general web, shell, browser, file-read/write, skill, plugin, or subagent capabilities | The custom profile allowlists only `vaccinepath`; SEC-02 and `test_profile_is_a_deny_by_default_allowlist` passed |
| Alert fatigue | Tasks and review reasons are deduplicated; reminders are bundled and capped | TOL-01, TOL-02, and TOL-03 passed; post-review Phase 2 used one reminder per affected child per run |
| Auditability | Inputs, actions, outputs, sources, timestamps, and human decisions must be recordable | Tool/UI tests passed; post-review Phase 2 produced 27 audit entries across three actor types |
| Human checkpoint | A clinician can approve, edit, reject, and verify records | UI-03 passed and the review-page demo provides visual evidence |
| Prompt injection | User-provided text must not become agent instructions or alter deterministic outcomes | SEC-01 passed: caregiver free text is retained in storage for clinicians but withheld from the LLM; only structured fields are evaluated. The agent also has no general-purpose tools |

This control reduces the reachable impact of prompt injection; it does not constitute a production security assessment. Additional adversarial strings and all future free-text fields should be included in deployment-level testing.

### 6.1 Model choice and limitations

DeepSeek Chat was selected for the classroom prototype because its OpenAI-compatible API integrates directly with DeerFlow, it provides adequate tool calling for the narrow administrative orchestration task, and its usage cost supports repeated demo and evaluation runs. The model is replaceable: no clinical rule is encoded in the prompt or model. Schedule, conflict, screening, and escalation decisions remain deterministic Python outputs.

The trade-off is that model behaviour can still vary in tool ordering, wording, and adherence to multi-step prompts. This is why the implementation enforces blocking, authority, idempotency, reminder limits, and clinical escalation below the prompt layer, and retains human review for uncertain or safety-relevant cases.

## 7. Defects found during development and regression controls

| Defect observed | Potential impact | Resolution | Regression evidence |
|---|---|---|---|
| The model re-derived the reminder window and skipped a tool-directed repeat reminder | Required follow-up could be missed | Reminder and escalation decisions were moved into `vp_list_tasks` as ready-made outputs | `test_list_tasks_precomputes_repeat_and_escalation` |
| Cross-session framework memory caused a new agent to claim knowledge of an earlier run | Misleading summaries and poor auditability | Uncontrolled cross-session memory was disabled; scheduled runs reuse only the intended thread | Phase 0 persistent-thread test and setup configuration |
| One extreme overdue case produced 16 tasks, 15 review requests, and about 100 calls | Alert fatigue, excessive cost, and unusable review queues | Task creation, reminders, and review reasons were bundled and made idempotent | `test_create_tasks_idempotent`, `test_request_review_bundles_per_child`, Phase 2 |
| Retrieval quoted guidance for a topic not covered by the corpus | False grounding | Unsupported topics now return no excerpts and explicitly instruct the caller not to quote | `test_get_guidance_returns_nothing_for_topics_the_corpus_does_not_cover` |
| A UI refactor changed all screening radio-button defaults to “yes” | False safety flags and unnecessary reviews | Defaults were restored to “no” and locked by a UI test | `test_screening_defaults_are_all_no_and_clear` |
| UI and agent used different time zones | Incorrect due dates and reminder timing | Dates and scheduled tasks were standardised on Asia/Singapore | Store/scheduler configuration and live Phase 2 timestamps |
| Streamlit reruns could resubmit a form | Duplicate screening records or actions | Idempotency checks were added before persistence | `test_tasks_page_screening_with_flag_routes_to_review` |
| A blocking record error was reported but schedule computation still continued | Tasks could be generated from impossible data | `vp_check_schedule` and the timeline now stop before schedule generation and expose the blocking issues | `test_check_schedule_is_blocked_by_impossible_record`, `test_timeline_blocks_impossible_records` |
| “One reminder per child per wake-up” existed only in the prompt | Multiple calls could generate multiple notifications in one run | The tool now records the reminded child in run state and rejects subsequent calls, even for different tasks | `test_send_reminder_enforces_one_per_child_task_per_wake` |
| VaccinePath threads used the default lead agent | General configured tools could be inherited | Setup now installs and binds a deny-by-default custom agent profile | `test_profile_is_a_deny_by_default_allowlist`, `test_setup_binds_thread_and_schedule_to_custom_agent` |
| Caregiver free text was returned inside the model-visible child payload | A malicious string could be interpreted as an instruction | Raw free text remains stored for clinicians but is replaced with a boolean presence flag before model exposure | `test_get_child_withholds_caregiver_free_text_from_agent` |

## 8. Limitations

- The NCIS source does not specify catch-up intervals for every vaccine series. The prototype deliberately identifies missing doses but routes unsupported timing decisions to a clinician.
- The post-vaccination thresholds are derived from public KKH and HealthHub guidance and have not undergone independent clinical validation.
- Guidance retrieval is deterministic keyword matching over a small curated corpus, not semantic vector retrieval over a comprehensive clinical knowledge base.
- All data, clinic actions, notifications, and clinician decisions are simulated. There is no integration with real healthcare records or services.
- The prototype operates as a single-family, single-thread demonstration and has not been evaluated for multi-tenant privacy, authentication, encryption, accessibility, or production-scale concurrency.
- The prompt-injection regression covers the current caregiver check-in field, not every possible adversarial encoding or future input surface.
- DeerFlow still supplies a small set of framework-owned, non-clinical built-ins (for example presentation/upload-listing plumbing). The VaccinePath profile removes general configured tool groups and the live run used only `vp_*` tools, but a production deployment should also enforce an infrastructure-level tool authorization policy rather than relying on framework defaults.

## 9. Conclusion

The reviewed prototype passed all 94 automated tests and both live workflow checks. The evidence demonstrates deterministic schedule and escalation behaviour, persistent state across scheduled runs, least-privilege tool use, idempotent task handling, enforced reminder controls, input isolation, official-source retrieval, mandatory human review, and auditable state changes.

The evaluation supports the prototype’s intended claim: VaccinePath is a working agentic coordination workflow with explicit safety boundaries. It does not establish clinical effectiveness, production security, or readiness for use with real patient data.
