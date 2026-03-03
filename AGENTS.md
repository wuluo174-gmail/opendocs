# AGENTS.md

## OpenDocs repository rules

### 1. Source of truth
Always follow these files in this exact order:
1. `docs/specs/OpenDocs_工程实施主规范_v1.0.md`
2. `docs/acceptance/tasks.yaml`
3. `docs/acceptance/acceptance_cases.md`
4. `docs/prompts/codex_operator_prompt.md`

### 2. Stage discipline
- Work strictly in stage order: `S0 -> S11`.
- Only do one stage at a time.
- Before making changes, restate the current stage goal and exit criteria.
- List the files you plan to create or modify before implementation.
- Do not start the next stage until the current stage exit criteria are all met.

### 3. Test discipline
- No stage is complete without tests.
- You must run the stage test commands, not merely describe them.
- If tests fail, fix the smallest cause first and rerun the relevant tests.
- Do not widen scope when debugging.

### 4. Architecture discipline
- Do not replace the locked tech stack unless an ADR is created first.
- Keep changes minimal, clear, typed, and testable.
- Do not introduce large frameworks early "for future use".
- Update docs whenever behavior changes.

### 5. Safety red lines
- No default delete behavior.
- No write operations without preview and confirmation.
- No UI direct DB/file/provider access.
- No memory overriding document evidence.
- No factual answer without citations.
- Refuse when evidence is insufficient.
- No plaintext secrets in logs or committed files.
- In local-only work, do not request network unless the human explicitly allows it.

### 6. Reporting style
The human supervisor is not a developer.
After each stage, explain in plain Chinese:
1. what you changed
2. why you changed it
3. what commands you ran
4. what passed / failed
5. whether the stage gate is satisfied

### 7. If blocked
When blocked, do not stop at vague discussion.
Output:
1. smallest blocker
2. root cause
3. smallest safe fix
4. commands to rerun
5. whether an ADR is required
