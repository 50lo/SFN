---
title: SFN Specification
description: Syntax, semantics, and examples for Step Flow Notation.
---

# Step Flow Notation

A short format for multi-step workflows with branching and convergence. Built
for mobile typing and LLM conversion.

## Step format

```text
N. type[:param[:subparam]] [args...] ["prompt"] ([after X[,Y...]][, if condition][, goto N]) [=> output_name]
```

- **N**: step number, starting at 1
- **type**: one of `tool`, `llm`, or `wait_human`
- **:param**: for `tool`, the CLI tool name such as `curl` or `jq`; for `llm`, an optional coding agent
- **:subparam**: for `llm`, an optional model; valid only when an agent is present
- **args...**: shell-style arguments, including interpolated named outputs like `{page}`
- **"prompt"**: optional inline instruction for an `llm` step
- **after X**: dependencies for non-linear execution
- **if condition**: a condition evaluated against the triggering parent output
- **goto N**: jump target used to create loops
- **=> output_name**: binds the step output for reuse in later steps

## Implied steps

Every flow has two implied steps:

- **Step 0 (start)**: the entry point
- **Step 9999 (end)**: the terminal step

Do not write these steps. They anchor the workflow graph and make constructs
like `after 0` possible.

## Tool arguments

Arguments after `tool:name` follow shell conventions and pass through as a shell
command.

| Form | Meaning | Example |
| --- | --- | --- |
| `bareword` | Positional argument | `tool:curl https://example.com` |
| `{var}` | Interpolated named output | `tool:curl {page_url}` |
| `-f` | Boolean flag | `tool:curl -s` |
| `-f value` | Flag with a value | `tool:jq -r '.name'` |
| `--flag=value` | Long flag with a value | `tool:curl --output=file.html` |

Quote values that contain spaces, for example:

```text
tool:echo "hello world"
```

## LLM selectors

`llm` steps may pin a coding agent and model:

```text
llm[:agent[:model]] "prompt"
```

- `llm "..."`: use the executor default agent and model
- `llm:codex "..."`: use `codex` and its default model
- `llm:codex:gpt-5.4 "..."`: use `codex` with an explicit model
- `llm::gpt-5.4 "..."`: invalid

Selectors are step-local. They do not affect other `llm` steps.

## Defaults and shortcuts

- Steps without `after` run in sequence by default.
- Step 1 depends on step 0.
- Steps without dependents and without `goto` fall through to step 9999.
- `wait_human` pauses until the user replies; that reply becomes the step
  output.

## Outputs

Use `=> name` to bind a step output, then reference it later with `{name}`.

```text
1. tool:curl -s https://api.github.com/repos/50lo/SFN/releases/latest => release
2. llm "summarize {release} for a short changelog" => summary
3. tool:save_note --text={summary}
```

If a step has no `=> name`, the executor may still see the output, but later
steps cannot reference it by name.

## Conditions

Conditions decide whether a step runs when its dependency finishes.

### Condition subject

- With one dependency, evaluate against that dependency's output.
- With multiple dependencies, evaluate against the dependency whose completion
  made the step runnable.
- To target a specific named output, qualify the predicate:
  `review contains("approved")`.

### Condition language

Preferred short forms:

- Status tokens: `succeeded`, `failed`
- Text predicates: `contains("text")`, `match(/regex/)`
- Qualified predicates: `output_name contains("text")`
- Field predicates: `has(key)`, `eq(key,"value")`
- Boolean operators: `and`, `or`, `not`

Examples:

```text
4. llm "fix failing tests" (after 3, if failed, goto 3)
5. tool:save_db (after 2, if contains("approved"))
6. llm "ask for missing info" (after 2, if not has("email"))
```

### Failure detection

`failed` and `succeeded` apply across all step types. Use a sibling `if failed`
branch when a later step depends on a result that might not exist.

## Branching

Several steps can depend on the same parent with different conditions:

```text
3. tool:save_db (after 2, if contains("approved"))
4. llm "explain rejection" (after 2, if contains("rejected"))
```

## Convergence

Multiple dependencies create an AND-join:

```text
5. llm "summarize both results" (after 3, 4)
```

That step runs only after both parents finish.

## Loops

Use `goto N` to create cycles:

```text
3. tool:run_tests => tests
4. llm:codex "fix failing tests" (after 3, if failed, goto 3)
```

The loop continues only while the condition holds. Otherwise execution moves
forward.

## Edge cases

- Two steps with the same `after` and no conditions run in parallel.
- If conditional siblings exist and one step has no condition, it acts as the
  default branch.
- A conditional `goto` loops only when its condition matches.

## Examples

### Linear: fetch release notes and summarize

```text
1. tool:curl -s https://api.github.com/repos/50lo/SFN/releases/latest => release
2. llm:codex:gpt-5.4 "summarize {release} for a short changelog email" => summary
3. wait_human
4. tool:save_note --text={summary}
```

### Branching: review gate

```text
1. tool:curl -s https://api.github.com/repos/50lo/SFN/pulls/1 => pr
2. llm "review {pr}: is this ready to merge?" => review
3. wait_human => decision
4. tool:save_db --payload={review} (after 3, if contains("approved"))
5. llm:codex "draft a clear rejection note for the author" (after 3, if contains("rejected"))
```

### Parallel with convergence

```text
1. tool:curl -s https://docs.example.com/v1/auth => v1
2. tool:curl -s https://docs.example.com/v2/auth (after 0) => v2
3. llm:codex "compare auth docs {v1} vs {v2}; list breaking changes" (after 1, 2) => diff
4. wait_human
5. tool:send_report --text={diff}
```

### Extractive LLM with failure handling

```text
1. tool:curl -s https://docs.example.com/pricing => page
2. llm:codex:gpt-5.4 "extract the pricing table from {page}" => pricing
3. tool:save_note --text={pricing}
4. llm "pricing not found; describe what the page contains instead" (after 2, if failed)
```

### Loop: iterative build cycle

```text
1. llm "Read PRD.md, split into tasks, save to TASKS.md" => tasks
2. llm:codex:gpt-5.4 "Implement the next open task from TASKS.md, then mark it done" => impl
3. tool:run_tests => tests
4. llm:codex "Fix failing tests" (after 3, if failed, goto 3)
5. llm "Write a short implementation summary" (after 3, if succeeded and contains("tasks remain"), goto 2)
```

## Quick reference

| Concept | Syntax | Example |
| --- | --- | --- |
| Sequential step | `N. type ...` | `2. llm "summarize {page}"` |
| LLM selector | `llm[:agent[:model]]` | `2. llm:codex:gpt-5.4 "summarize {page}"` |
| Named output | `=> name` | `1. tool:curl url => page` |
| Dependency | `after X` | `(after 3)` |
| Parallel start | `after 0` | `(after 0)` |
| Convergence | `after X, Y` | `(after 1, 2)` |
| Condition | `if ...` | `(after 2, if contains("yes"))` |
| Loop | `goto N` | `(after 3, if failed, goto 2)` |
| Human gate | `wait_human` | `3. wait_human => decision` |
