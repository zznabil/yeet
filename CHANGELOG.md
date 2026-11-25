# Changes

## 1.2.1 — 2026-11-25

- Live trials run again: default model `anthropic/claude-sonnet-5-5` (retired `openai-codex/gpt-6.1-sol` removed); override with `YEET_TRIAL_MODEL`.
- `trial_check` shows the agent an explicit PASS/FAIL line, not only an opaque completion marker.
- Early OMP exits report OMP's stderr; temp-directory cleanup locks no longer mask the real trial result.

## 1.2.0 — 2026-11-25

- Completion gates: inventory every skippable outcome; reread the request before claiming complete; calibrated checks (a known-broken state must fail); stale-evidence rule; no "should work", deferred or partial coverage as done; disclose caps and unprocessed remainder; worker returns are claims; no blocked/infeasible verdict while a safe distinguishing probe remains.
- Considerate finish: ACT / ASK / DO NOT ACT initiative; safe preparation, then one bundled question; ready-to-use handoff (where, how to run, user action left); clean-start check when others run it; cut avoidable human effort; one bounded care pass.
- Proportional security: supply-chain, crypto or adversarial checks only when work ships, signs, handles secrets, keys, payments or personal data, or crosses a trust boundary.
- Skill context budget raised from 1,300 to 1,600 words.

## 1.1.0 — 2026-11-24

- Records: yeet specs, state, handoffs, archives and docs are Python literal code records in `.yeet/`, max 200 non-blank lines or 500 words; overflow continues in linked files. Typed `Record` schema and checker ship in `skills/yeet/scripts/`; basedpyright is the record LSP.
- vähän governs yeet: built-in STE/ISO 704/Diataxis, answer-first and visuals rules; precedence user/project > vähän > yeet; shapes reports, handoffs, docs.

## 1.0.0 — 2026-11-22

- Replace the CLI, generated workflows, website and skill catalogue with one standalone `yeet` skill.
- Keep lightweight specs, agent-owned execution, bounded repair and real-result verification.
- Support manual selection and host-controlled implicit invocation.
- Remove required proposal, archive, approval-round and task-file ceremonies. Keep safety/consent gates.
- Add package validation and isolated execution trials. The local predecessor checkout retains its Git history.
