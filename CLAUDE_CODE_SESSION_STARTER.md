# Claude Code — Session Starter

Paste this prompt at the start of every Claude Code session working on the ASTRA intent feature.

---

## Prompt to paste into Claude Code

```
Read the following files before doing anything else:
- ASTRA_INTENT_FEATURE.md  (full feature design — source of truth)
- DECISIONS.md             (architectural decisions and rationale)
- TASKS.md                 (ordered implementation backlog)

We are implementing the intent-driven planner feature for ASTRA.
The existing backend services (artifact-service, capability-service, conductor-service)
must not be modified except for TASK-001 (conductor-core extraction), which is additive only.

After reading the three files, tell me:
1. Which task you are picking up (I will tell you if different)
2. What files you plan to create or modify
3. Any questions about the design before you start

Current task: [FILL IN TASK NUMBER e.g. TASK-001]
```

---

## Tips for smooth sessions

- **One task per session** — Claude Code works best with a focused scope. Complete TASK-001 fully before starting TASK-002.
- **Run tests after TASK-001** — before touching anything else, verify the existing conductor tests still pass after conductor-core extraction.
- **Reference the design doc for schemas** — if Claude Code asks about a data model field, point it to Section 3 of ASTRA_INTENT_FEATURE.md.
- **DECISIONS.md prevents drift** — if Claude Code suggests an approach that contradicts a decision (e.g. modifying the existing conductor), point it to the relevant ADR.
- **Frontend tasks reference the mockups** — the mockups live in the design chat. For TASK-009 onwards, describe the visual you want by referencing the mockup state names in ASTRA_INTENT_FEATURE.md Section 4.2.
