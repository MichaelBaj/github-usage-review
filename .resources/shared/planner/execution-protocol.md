# Planner Execution Protocol

Reference for agents executing planner-generated phase files. The planner embeds the reminder block in every phase file; this document is the canonical source.

## Per-Task Loop

```
for each task in the phase:
  1. Read the task line (confirm it is `- [ ]` — if `- [x]`, skip)
  2. Execute the task to completion
  3. Edit the phase file: change `- [ ]` → `- [x]`, save immediately
  4. Then and only then: read the next task
```

Never read ahead, batch checkbox updates, or continue past a checkpoint without the required commit.

## Checkpoint Halt Procedure

On `🔖 CHECKPOINT`:
1. Verify the gate.
2. Audit checkboxes.
3. Commit with exact checkpoint message.
4. Continue only after commit succeeds.

## Protocol Violations

| Violation | Consequence |
|-----------|-------------|
| Marking multiple tasks complete at once | Reset to `- [ ]`, redo with immediate updates |
| Proceeding past checkpoint without commit | Stop and run checkpoint procedure |
| Committing without gate verification | Revert, fix, verify, re-commit |
| Skipping checkpoint because progress is obvious | Not allowed |

## Self-Correction During Execution

If protocol is violated:
1. Stop immediately.
2. Audit phase file and checkbox state.
3. Find last clean checkpoint.
4. Re-execute tasks after that checkpoint as needed.
