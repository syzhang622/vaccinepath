# VaccinePath Family SG — Proposal (v2)

## Question 1 — Project title

**VaccinePath Family SG: An Agentic Childhood Vaccination Planning and Post-Vaccination Monitoring Assistant**

## Question 2 — Healthcare-related problem

Singapore's childhood immunisation programme achieves high overall coverage, so the problem we address is not awareness but **coordination and continuity**. Managing a child's vaccinations means tracking multiple vaccines, doses, boosters and appointments across several years, and the burden falls on parents — especially where records are fragmented.

The intended users are parents and caregivers of children aged 0–17 in Singapore, in particular three groups for whom coordination breaks down most often:

1. **Multi-child families** managing several overlapping schedules at once;
2. **Families whose doses are split across providers** — polyclinics, private paediatric clinics and school health programmes — producing incomplete or duplicated records;
3. **Families relocating to Singapore with overseas vaccination records**, which must be reconciled against the National Childhood Immunisation Schedule (NCIS) to determine which doses are still due.

For these users, fragmented or unclear information contributes to delayed or missed doses, unnecessary repeat doses, parental anxiety and additional administrative work for healthcare staff. After vaccination, parents may also be uncertain which reactions are expected, how symptoms are changing over time, and when professional attention should be sought.

Singapore already provides the official NCIS, and HealthHub offers immunisation records, upcoming-vaccination notifications and selected appointment functions. However, these services assume a single clean record and send generic reminders: they do not reconcile fragmented or overseas records against the schedule, do not follow through when an appointment is missed, and do not provide structured post-vaccination follow-up. VaccinePath Family SG aims to complement — not replace — these services by converting vaccination information into a personalised, continuously tracked workflow with human oversight. It does not determine a child's clinical suitability for vaccination, diagnose vaccine reactions or provide medical treatment.

## Question 3 — Agentic AI approach

What makes the system agentic rather than a traditional chatbot is that it is **long-running, stateful and self-triggering**. A chatbot answers questions when asked; VaccinePath holds a persistent goal ("keep this child's vaccination plan on track") and continues working toward it across weeks, without waiting to be prompted.

Concretely, the agent **wakes up on its own schedule**. At each scheduled run it checks the family's state: which doses are due or overdue, which reminders are unanswered, which monitoring tasks are open. It then decides what to do — send a reminder, ask whether a vaccination was completed, reorganise administrative tasks after a missed appointment, or escalate a case — and records the outcome before sleeping until the next trigger.

Each run follows a **Perceive–Reason–Act** cycle:

- **Perceive:** it reads vaccination records, appointment updates, task-completion signals and parent-reported observations;
- **Reason:** it compares structured records with official guidance, checks the current workflow state, identifies missing, duplicate or conflicting information, and applies predefined scheduling and escalation rules;
- **Act:** it asks targeted follow-up questions, updates tasks, schedules reminders, prepares summaries, or escalates for human review.

At intake, the agent converts manually entered records into a machine-checkable structure, detects gaps, duplicates and conflicts (including overseas records mapped against the NCIS), asks clarifying questions, and generates a personalised vaccination task plan. Before any scheduling, it runs a structured pre-vaccination safety screening (previous serious reactions, known allergies, current illness, immune-related conditions). The agent records and flags this information but never decides suitability itself: flagged or uncertain cases enter a **mandatory healthcare-professional review state** before the workflow can proceed.

After vaccination, the agent runs a monitoring workflow based on **structured parent check-ins**. Decisions to continue monitoring, warn, or escalate are made by a **deterministic rule engine against predefined criteria** — the LLM is confined to explaining information (with source-linked guidance retrieved from a knowledge base of official MOH/HealthHub material) and asking follow-up questions; it does not make escalation decisions and does not diagnose.

The agent may autonomously organise records, request missing administrative information, update routine tasks, send reminders and generate summaries. Human confirmation is required for vaccination suitability, complex catch-up schedules, previous serious reactions, potential contraindications and all clinical decisions. Tools and data sources include a RAG knowledge base of official guidance, the deterministic rule engine, a family/workflow-state database, simulated clinic, calendar and notification services, and structured JSON outputs with audit logging. The workflow stops when its goal is completed, required information remains unavailable, or a case exceeds the agent's authorised scope.

## Question 4 — Proposed prototype

The prototype will be a web application for parents managing the vaccination journeys of one or more children, built around one **core closed loop** that will be fully implemented and demonstrated, plus clearly separated stretch goals.

**Core scope:**

1. Family and child profiles with manual entry of vaccination records;
2. Validation against the official NCIS: detection of missing, duplicate or conflicting entries (including overseas records), with clarifying questions;
3. A personalised vaccination plan and timeline;
4. A structured pre-vaccination safety questionnaire, with flagged or uncertain cases routed to a mandatory professional-review state (a simulated clinician console with approve/reject/edit);
5. Simulated appointment booking, plus reminders driven by the agent's scheduled runs;
6. Administrative replanning after missed appointments (clinical catch-up schedules are flagged for professional confirmation);
7. Structured post-vaccination parent check-ins with rule-based continue/warn/escalate outcomes;
8. Clear workflow statuses (e.g. **Information Complete**, **Professional Review Required**, **Urgent Assessment Required**), source-linked explanations, and a complete audit log (input, action, source, timestamp, output, human decision).

**Stretch goals (only if time permits; not required for the core demonstration):** OCR upload of paper records; clinic search; symptom-trend visualisation; exportable parent/clinician summaries.

**Expected workflow:**

```text
Onboard child → validate records against NCIS → clarify gaps → generate plan
        ↓
  [recurring agent cycle]
  wake on schedule → check due doses and open tasks
  → run pre-vaccination screening (flags → professional review)
  → book simulated appointment + send reminders
  → confirm completion, or replan if missed
  → post-vaccination structured check-ins → continue or escalate
  → update state + audit log → sleep until next trigger
        ↓
  stop when the plan is complete, information is unavailable,
  or the case exceeds the agent's authorised scope
```

**Technology:** Streamlit for the interface; LangGraph for stateful workflow orchestration; an LLM API (e.g. Claude or GPT) accessed behind a mockable interface, so models can be swapped and tests can run without live calls; a deterministic Python rule engine for scheduling and escalation logic; a vector database for RAG over official MOH/HealthHub guidance; SQLite for profiles, task states and audit records. Clinic booking, calendar notifications and healthcare-provider escalation will be simulated.

**Demonstration scenarios:** (1) a complete routine record; (2) an incomplete or duplicate record requiring clarification; (3) a pre-vaccination case involving an allergy or previous reaction that requires professional review; (4) a missed appointment requiring replanning; (5) a mild post-vaccination report that continues monitoring; (6) a concerning report that triggers human escalation.

**Evaluation** will measure record-validation accuracy, correct workflow-state transitions, successful execution of scheduled tasks, and escalation of all predefined safety cases. Negative testing will include ambiguous records, out-of-scope medical questions, prompt injection and attempts to bypass human review.

## Question 5 — Safety, ethical, privacy, security and implementation concerns

The primary safety risks are that incomplete records, extraction errors, outdated guidance or AI hallucinations could produce an incorrect plan, an inappropriate response to a parent's report, or an incorrect assessment of vaccination suitability. Vaccination scheduling, safety-flagging and escalation logic therefore use **predefined, source-grounded deterministic rules rather than unrestricted language-model reasoning**: the LLM explains and asks questions, while the rule engine decides. These rules would require clinical validation before any real-world deployment.

A general allergy does not necessarily mean a child cannot be vaccinated, while a previous serious reaction or an allergy to a specific vaccine component may require professional assessment. The system therefore collects and flags relevant information without converting an allergy label into an automatic approval or refusal; the final suitability decision always rests with a healthcare professional.

The system will not: diagnose vaccine reactions; determine clinical suitability for vaccination; automatically approve or reject vaccination based on an allergy record; recommend or modify medication; independently create complex catch-up schedules; or replace professional medical assessment. Previous serious reactions, potential component allergies, immunocompromised status, significant current illness, unclear vaccination history and other uncertain findings require human review before the workflow proceeds. Persistent or concerning post-vaccination reports also trigger human review. When predefined urgent conditions are reported, the prototype stops the normal workflow, displays appropriate escalation information and records the event; it does not claim to have contacted a real healthcare provider.

Vaccination and monitoring records are sensitive information concerning minors. The prototype uses synthetic data only and collects only what the workflow requires. A real implementation would require explicit parental consent, strong authentication, encryption, role-based access, secure retention and deletion policies, and compliance with applicable privacy regulations.

Ethical concerns include parental over-reliance on automated advice, unequal digital access, language barriers and notification fatigue. Mitigations include clearly stated limitations, configurable reminder frequency, plain-language and source-cited explanations, and human checkpoints throughout — the agent supports parental decision-making without replacing parental autonomy or the clinician–patient relationship.

Security risks include unauthorised access, prompt injection through user-provided text, and misuse of connected tools. Mitigations include input validation, restricted tool permissions, structured output schemas, least-privilege access and comprehensive audit logs.

The prototype will not connect to the National Immunisation Registry, NEHR or real clinic systems. Its scope is limited to routine childhood vaccinations under the NCIS and short-term parent-assisted monitoring. Adult vaccination, travel vaccination, direct clinical triage and fully automated catch-up planning remain future work.

## Key official sources

- [National Childhood Immunisation Schedule (NCIS)](https://www.healthhub.sg/sites/assets/Assets/eServices/HPB-DB-Immunisation-Schedule.pdf)
- [HealthHub: Health records and immunisation records](https://support.healthhub.sg/hc/en-us/articles/15658192421785-What-types-of-health-records-are-available-on-HealthHub-and-where-are-these-health-records-retrieved-from)
- [HealthHub Parent Hub: Student immunisation and screening](https://www.healthhub.sg/programmes/parent-hub/student_immunisation_and_screening)
- [HealthHub: Immunisation for babies and children](https://www.healthhub.sg/well-being-and-lifestyle/pregnancy-and-infant-health/baby-immunisation-inject-to-protect)
- [HealthHub: Childhood immunisation suitability and possible reactions](https://www.healthhub.sg/well-being-and-lifestyle/personal-care/all-you-need-to-know-about-vaccinations)
