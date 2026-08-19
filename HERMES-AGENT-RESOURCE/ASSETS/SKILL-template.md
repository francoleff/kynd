# SKILL.md : skill template

Save to `~/.hermes/skills/<category>/<skill-name>/SKILL.md` . The skill name becomes a slash command . You can also ask the agent to create skills for you after complex tasks .

```markdown
---
name: <skill-name>
description: Brief description of what this skill does
version: 1.0.0
metadata:
  hermes:
    tags: [<tag1>, <tag2>]
    category: <category>
---

# <Skill Title>

## When to Use
Use this skill when the user asks to <trigger condition>.

## Procedure
1. <step 1>
2. <step 2>
3. <step 3>

## Pitfalls
- Common failure: <description>. Fix: <solution>

## Verification
Run <check> to confirm the result is correct.
```

Optionally add `references/` , `templates/` , or `scripts/` subfolders for supporting files .
