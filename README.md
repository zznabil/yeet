# yeet

One skill. Prompt to verified result. Humans steer; agents own execution.

Spec-driven, without proposal rounds, phase commands or task-file rituals.
Works for one-shot tasks and iterative work. No CLI, runtime, hooks or dependencies.

## Install

Copy [`skills/yeet`](skills/yeet/SKILL.md), including `agents/`, into a skill directory your agent supports:

- Codex or OMP: `~/.agents/skills/yeet/`
- Claude Code: `~/.claude/skills/yeet/`
- Other agents: their documented skill directory.

Restart or reload skills if your host requires it. Confirm `yeet` appears in its skill list.
Installation does not change your project's rules or grant permissions.

## Use

- Manual: `$yeet fix this bug and verify the result` in Codex; `/skill:yeet …` in OMP; `/yeet …` in hosts with slash skills.
- Automatic: ask for an outcome normally. The description supports agent selection; the Codex adapter permits implicit invocation. Actual selection depends on the host and model—not guaranteed by a Markdown file.

Give the outcome and hard constraints. Add checks, budget or approval limits when needed.
The agent inspects context, forms a compact spec, executes, checks and repairs.
Routine choices stay with the agent. Only blocking intent, unavailable facts and required approvals return to you.

For short work, the spec stays in context. Longer work may write records in `.yeet/`.
Records are Python literal files (AST-parseable, LSP-checkable), each at most 200 non-blank lines or 500 words. Overflow continues in a linked file; done records go to `.yeet/archive/`.
No required new documents. Question-only, plan-only and read-only requests retain those limits.

## Limits

A skill guides behaviour; it cannot enforce obedience, supply tools or survive a stopped host.
Autonomy does not permit unauthorised deletion, publication, spending or production changes.
The agent must report missing evidence, failed checks and blockers—not claim completion.

## Maintain

Python 3.10+; standard library only:

```text
python tools/validate_skill.py
python tools/test_checks.py
python tools/evaluate_skill.py
python tools/check_record.py .yeet   # optional: check a project's records
```

The validator checks package shape, metadata, local links and required rule coverage.
It does not prove agent behaviour. Optional live trials require Windows, authenticated OMP,
`openai-codex/gpt-6.1-sol` and Codex native MXC. Guarded tools and confined checks fail closed.
See [`tools/TRIALS.md`](tools/TRIALS.md) for fixed pass conditions and evidence limits.

Update: inspect the new skill, then replace the installed `yeet` folder. No automatic updates.
Uninstall: remove that installed folder; leave project work untouched.

[Design sources](CREDITS.md) · [Changes](CHANGELOG.md) · [MIT licence](LICENSE)
