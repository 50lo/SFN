# Step Flow Notation

A short format for multi-step workflows with branching and convergence. Built for mobile typing and LLM conversion.

## Step format

```text
N. type[:param[:subparam]] [args...] ["prompt"] ([after X[,Y...]][, if condition][, goto N]) [=> output_name]
```

- **N** — step number (1-based; default run order for linear flows)
- **type** — one of: `tool`, `llm`, `wait_human`
- **:param** — for `tool`: CLI tool name (e.g. `tool:curl`, `tool:jq`). For `llm`: optional coding agent (e.g. `llm:codex`).
- **:subparam** — for `llm`: optional model (e.g. `llm:codex:gpt-5.4`). Valid only when an agent is set.
- **args...** — shell-style arguments: positional values, `--flag=value`, `-f value`, or boolean flags `-f` / `--flag`. Use `{name}` to interpolate a named output. See *Tool arguments*.
- **"prompt"** — optional, for `llm` steps. Short instruction in quotes.
- **after X** — dependencies. One or more step numbers. If omitted, the step depends on N-1 (sequential).
- **if condition** — conditional edge. Evaluated against the parent output that triggered this step (see *Conditions*).
- **goto N** — after this step finishes, jump to step N. Use for loops. Combine with `if` for conditional loops.
- **=> output_name** — optional output binding. Names this step's output for later use (see *Outputs*).

## Implied steps

Every flow has two implied steps:

- **Step 0 (start)** — entry point. Step 1 depends on it by default. Use `after 0` to start a step in parallel from the beginning.
- **Step 9999 (end)** — terminal step. Any step with no dependents and no `goto` falls through here and ends the flow.

Do not write these steps. They only anchor the graph.

## Tool arguments

Arguments after `tool:name` follow shell conventions and pass through as a shell command:

| Form | Meaning | Example |
|------|---------|---------|
| `bareword` | Positional argument | `tool:curl https://example.com` |
| `{var}` | Interpolated named output (positional or as a value) | `tool:curl {page_url}` |
| `-f` | Boolean flag (no value) | `tool:curl -s` |
| `-f value` | Flag with a value | `tool:jq -r '.name'` |
| `--flag=value` | Long flag with a value | `tool:curl --output=file.html` |

Separate multiple args with spaces, as in a shell. Quote values that contain spaces: `tool:echo "hello world"`.

## LLM selectors

`llm` steps may pin a coding agent and model:

```text
llm[:agent[:model]] "prompt"
```

- `llm "..."` — executor default agent and model
- `llm:codex "..."` — `codex` with that agent's default model
- `llm:codex:gpt-5.4 "..."` — `codex` with an explicit model
- `llm::gpt-5.4 "..."` — invalid; a model requires an agent

Selectors apply only to that step. They do not change defaults for other `llm` steps.

## Defaults and shortcuts

- Steps without `after` run in sequence: step N depends on step N-1.
- Step 1 is the first runnable step (it depends on step 0).
- Steps with no dependents and no `goto` fall through to step 9999 (end).
- `wait_human` pauses until the user replies. That reply is the step's output.

## Outputs

Name a step's output with `=> name`. Later steps can use that name in prompts and tool arguments via `{name}`.

Example:

```text
1. tool:curl -s https://api.github.com/repos/50lo/SFN/releases/latest => release
2. llm "summarize {release} for a short changelog" => summary
3. tool:save_note --text={summary}
```

Notes:

- With multiple parents, name the specific parent output you need.
- Without `=> name`, the executor or LLM may still see the output, but later steps cannot reference it by name.

## Conditions

Conditions decide whether a step runs when a dependency finishes.

### Condition subject

Evaluate a condition against the output of the dependency that triggered the step.

- One dependency: use that dependency's output.
- Multiple dependencies: use the dependency whose completion made the step eligible (the triggering parent). For clearer gating, name outputs with `=>` and refer to them in the condition with `has(...)`, `eq(...)`, and similar forms.
- To test a specific named output instead of the triggering parent, qualify the predicate: `output_name contains("text")`, `output_name has(key)`, and so on.

### Condition language

Keep conditions short and phone-friendly. Prefer this small set of forms (an LLM may still interpret meaning):

- **status tokens**: `succeeded`, `failed`
- **text predicates**: `contains("text")`, `match(/regex/)`
- **qualified text predicates**: `output_name contains("text")`, `output_name match(/regex/)` — test a named output
- **field predicates** (structured outputs): `has(key)`, `eq(key,"value")`
- **boolean ops**: `and`, `or`, `not` (parentheses optional)

Examples:

```text
4. llm "fix failing tests" (after 3, if failed, goto 3)
5. tool:save_db (after 2, if contains("approved"))
6. llm "ask for missing info" (after 2, if not has("email"))
7. tool:flag_external (after 1, if page_url contains("abcd.com"))
```

### Failure detection

`failed` and `succeeded` work the same across step types. `failed` means the step did not meet its goal; `succeeded` means it did. The executor detects and routes failures for each type.

**Failure routing:** when a named output feeds later steps, add an `if failed` sibling branch for retry, fallback, or an error report. See *Extractive LLM with failure handling* in Examples.

## Branching

Several steps can share one parent and use different conditions:

```text
3. tool:save_db (after 2, if contains("approved"))
4. llm "explain rejection" (after 2, if contains("rejected"))
```

## Convergence

A step with multiple parents waits for **all** of them (AND-join):

```text
5. llm "summarize both results" (after 3, 4)
```

Step 5 runs only after steps 3 and 4 both finish.

## Loops

Use `goto N` for cycles. Add `if` for conditional loops:

```text
3. tool:run_tests => tests
4. llm:codex "fix failing tests" (after 3, if failed, goto 3)
```

Step 4 runs only when tests fail, then returns to step 3. When tests pass, step 3 continues forward instead.

## Edge cases

- **Parallel execution**: two steps with the same `after` and no `if` run in parallel.
- **Condition matching**: conditions apply to the triggering parent's output; prefer the *Condition language* forms.
- **Missing conditions**: if siblings have conditions and one step has none, that step is the default/else branch.
- **Loop exit**: a `goto` with `if` loops only when the condition holds. Otherwise execution continues forward.

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

Note: step 2 uses `after 0` so it does not wait on step 1; both start together. Step 3 waits for both (AND-join).

### Extractive LLM with failure handling

```text
1. tool:curl -s https://docs.example.com/pricing => page
2. llm:codex:gpt-5.4 "extract the pricing table from {page}" => pricing
3. tool:save_note --text={pricing}
4. llm "pricing not found; describe what the page contains instead" (after 2, if failed)
```

Step 3 is the default success path and saves the table. Step 4 runs if step 2 failed — API error or missing content — and returns a useful fallback.

### Loop: iterative build cycle

```text
1. llm "Read PRD.md, split into tasks, save to TASKS.md" => tasks
2. llm:codex:gpt-5.4 "Implement the next open task from TASKS.md, then mark it done" => impl
3. tool:run_tests => tests
4. llm:codex "Fix failing tests" (after 3, if failed, goto 3)
5. llm "Write a short implementation summary" (after 3, if succeeded and contains("tasks remain"), goto 2)
```

Inner loop: steps 3–4 repeat until tests pass. Outer loop: steps 2–5 repeat while tasks remain. When none remain, step 5 falls through to step 9999 (end).
