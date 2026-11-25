# Changes

## 1.4.1 — 2026-11-25

- Hill-climb rule made concrete after a live trial caught 1.4.0 handing back after one failed route: one failed route is never a blocker; when a named file, path, command or service is missing, read README, AGENTS, NOTES, CHANGELOG and nearby docs, search and try likely new locations first.
- New live trial `hill-climb` (missing file, notes point to the new home; random token). 1.4.0 failed it; 1.4.1 passed 3 of 3, full suite 4 of 4.
- Trial runner: `YEET_TRIAL_ONLY` selects trials; the write tool now names the task's real writable file.

## 1.4.0 — 2026-11-25

- Hill-climb before handing back: check notes and tool help for existing setups, try every safe route (other tools, config/registration fixes, missing services, restarts); hand back only credentials, physical actions or decisions, listing routes tried.
- Before closing or restarting anything the user has open, capture what restores it and verify the restore.

## 1.3.0 — 2026-11-25

- From an OpenSpec re-review: check the case the user would most hate to see broken; prove removed behaviour is gone on every path and renamed behaviour is unchanged.

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
