# Step Flow Notation

A short text format for writing multi-step workflows. Easy to type on a phone, easy for LLMs to read and convert.

## Step format

```text
N. type[:param] [args...] ["prompt"] ([after X[,Y...]][, if condition][, goto N][, => output_name])
```

- **N** — step number (starts at 1; steps run in this order unless changed with `after`)
- **type** — one of: `tool`, `llm`, `wait_human`
- **:param** — for `tool`: the command name (e.g. `tool:curl`, `tool:jq`). Not used for other types.
- **args...** — arguments passed to the tool, like a shell command. Use `{name}` to insert a named output from an earlier step. See *Tool arguments*.
- **"prompt"** — for `llm` steps only. A short instruction in quotes.
- **after X** — which steps must finish before this one runs. Can list multiple: `after 1, 2`. If missing, the step waits for the previous one (N-1).
- **if condition** — only run this step when the condition is true. Checked against the parent step's output (see *Conditions*).
- **goto N** — jump to step N after this step finishes. Use with `if` to create loops.
- **=> output_name** — give this step's output a name so later steps can use it with `{name}`.

## Implied steps

Every flow has two automatic steps:

- **Step 0 (start)** — the starting point. Step 1 depends on it. Use `after 0` to run a step in parallel from the start.
- **Step 9999 (end)** — the end point. Any step with no next step and no `goto` goes to step 9999 automatically.

You never write these steps. They are always there.

## Tool arguments

Arguments after `tool:name` work like shell commands:

| Form | Meaning | Example |
|------|---------|---------|
| `bareword` | Positional argument | `tool:curl https://example.com` |
| `{var}` | Insert a named output from an earlier step | `tool:curl {page_url}` |
| `-f` | Flag (no value) | `tool:curl -s` |
| `-f value` | Flag with a value | `tool:jq -r '.name'` |
| `--flag=value` | Long flag with a value | `tool:curl --output=file.html` |

Separate arguments with spaces. Use quotes around values with spaces: `tool:echo "hello world"`.

## Defaults

- Steps without `after` run in order: step N waits for step N-1.
- Step 1 always runs first (it depends on step 0).
- Steps with no next step and no `goto` go to step 9999 (end).
- `wait_human` pauses the flow until the user responds. Their response becomes the step's output.

## Outputs

Use `=> name` to name a step's output. Later steps can use that output by writing `{name}` in prompts or arguments.

Example:

```text
1. tool:curl -s https://example.com => page
2. llm "summarize {page}" => summary
3. tool:save_note --text={summary}
```

Notes:

- When a step has multiple parents, name the specific output you want to use.
- A step without `=> name` still produces output, but other steps cannot refer to it by name.

## Conditions

Conditions control whether a step runs after its parent finishes.

### What does the condition check?

A condition checks the parent step's output.

- **One parent:** the condition checks that parent's output.
- **Multiple parents:** the condition checks the last parent to finish. For more control, name outputs with `=>` and test them directly: `output_name contains("text")`.

### Condition language

Use these short forms for conditions:

- **status**: `succeeded`, `failed`
- **text checks**: `contains("text")`, `match(/regex/)`
- **text checks on a named output**: `output_name contains("text")`, `output_name match(/regex/)`
- **field checks** (for structured data): `has(key)`, `eq(key, "value")`
- **logic**: `and`, `or`, `not`

Examples:

```text
4. llm "fix failing tests" (after 3, if failed, goto 3)
5. tool:save_db (after 2, if contains("approved"))
6. llm "ask for missing info" (after 2, if not has("email"))
7. tool:flag_external (after 1, if page_url contains("abcd.com"))
```

### Failure handling

`failed` means the step did not accomplish its goal. `succeeded` means it did. These work the same way for all step types (`tool`, `llm`, `wait_human`).

**Tip:** if later steps depend on a named output, add an `if failed` branch to handle the case where that output can't be produced. See *LLM with failure handling* in Examples.

## Branching

Multiple steps can follow the same parent, each with a different condition:

```text
3. tool:save_db (after 2, if contains("approved"))
4. llm "explain rejection" (after 2, if contains("rejected"))
```

## Waiting for multiple steps

A step with multiple parents waits for **all** of them to finish before running:

```text
5. llm "summarize both results" (after 3, 4)
```

Step 5 runs only after both step 3 and step 4 finish.

## Loops

Use `goto N` to jump back to an earlier step. Add `if` to loop only when a condition is true:

```text
3. tool:run_tests => tests
4. llm "fix failing tests" (after 3, if failed, goto 3)
```

Step 4 runs only if tests fail, then jumps back to step 3. When tests pass, step 3 continues forward instead.

## Special cases

- **Parallel steps**: two steps with the same `after` and no `if` run at the same time.
- **Conditions**: always checked against the parent step's output. Use the forms from *Condition language* for consistency.
- **Default branch**: if some steps after a parent have conditions and one does not, the one without a condition is the default (like `else`).
- **Loop exit**: `goto` with `if` only loops when the condition is true. Otherwise, the flow continues forward.

## Examples

### Linear: fetch and summarize

```text
1. tool:curl -s https://example.com => page
2. llm "summarize {page}" => summary
3. wait_human
4. tool:save_note --text={summary}
```

### Branching: review gate

```text
1. tool:curl -s https://example.com => page
2. llm "analyze {page}, is it relevant?" => review
3. wait_human => decision
4. tool:save_db --payload={review} (after 3, if contains("approved"))
5. llm "draft rejection reason" (after 3, if contains("rejected"))
```

### Parallel with convergence

```text
1. tool:curl -s https://site-a.com => a
2. tool:curl -s https://site-b.com (after 0) => b
3. llm "compare both results: {a} vs {b}" (after 1, 2) => diff
4. wait_human
5. tool:send_report --text={diff}
```

Step 2 uses `after 0` so it starts at the same time as step 1 (both run in parallel). Step 3 waits for both to finish.

### LLM with failure handling

```text
1. tool:curl -s https://example.com => page
2. llm "extract the pricing table from {page}" => pricing
3. tool:save_note --text={pricing}
4. llm "pricing not found, describe what the page contains instead" (after 2, if failed)
```

Step 3 saves the pricing on success (it's the default branch — no condition). Step 4 runs if step 2 failed and produces a fallback description.

### Loop: iterative dev cycle

```text
1. llm "Read PRD.md, split to tasks, save to TASKS.md" => tasks
2. llm "Implement next task from TASKS.md, mark done" => impl
3. tool:run_tests => tests
4. llm "Fix failing tests" (after 3, if failed, goto 3)
5. llm "Prepare implementation summary" (after 3, if succeeded and contains("tasks remain"), goto 2)
```

Inner loop: steps 3–4 repeat until tests pass. Outer loop: steps 2–5 repeat until all tasks are done. When no tasks remain, step 5 goes to step 9999 (end).
