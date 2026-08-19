# Autonomous execution template

Hand a bounded autonomous task to the agent , with guardrails . Relies on the approval system and checkpoints .

```markdown
EXECUTE: <task>
AUTONOMY LEVEL: <full | ask before destructive | ask before external actions>
APPROVAL RULES:
- Never run <specific dangerous commands> without asking.
- Never modify <protected files/folders>.
REPORT BACK: <what the final message must include>
ROLLBACK: <checkpoints on? what's the undo path?>
```
