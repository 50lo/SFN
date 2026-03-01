# Step Flow Notation

A concise format for describing multi-step workflows with branching and convergence. Designed for mobile input and LLM interpretation.

## Step format

```text
N. type[:param] [args...] ["prompt"] ([after X[,Y...]][, if condition][, goto N][, => output_name])
```

- **N** — step number (1-based, execution order for linear flows)
- **type** — one of: `tool`, `llm`, `wait_human`
- **:param** — for `tool`: CLI tool name (e.g. `tool:curl`, `tool:jq`). For other types: omitted.
- **args...** — shell-style arguments: positional values, `--flag=value`, `-f value`, or boolean flags `-f` / `--flag`. Use `{name}` to interpolate a named output. See *Tool arguments*.
- **"prompt"** — optional, for `llm` nodes. Short inline instruction in quotes.
- **after X** — dependencies. References one or more step numbers. If omitted, step depends on N-1 (sequential).
- **if condition** — conditional edge. Condition is evaluated against the output of the parent step that caused this step to run (see *Conditions*).
- **goto N** — after this step completes, jump to step N. Enables loops. Can be combined with `if` for conditional looping.
- **=> output_name** — optional output binding. Names this step's output so it can be referenced later (see *Outputs*).

## Implied steps

Every flow has two implied steps:

- **Step 0 (start)** — the entry point. Step 1 implicitly depends on it. Use `after 0` to run a step in parallel from the start.
- **Step 9999 (end)** — the terminal step. Any step with no outgoing dependents and no `goto` implicitly falls through to step 9999, ending the flow.

These steps are never written explicitly; they exist to anchor the flow graph.

## Tool arguments

Tool args after `tool:name` follow shell conventions and are passed verbatim as a shell command:

| Form | Meaning | Example |
|------|---------|---------|
| `bareword` | Positional argument | `tool:curl https://example.com` |
| `{var}` | Interpolated named output (positional or as value) | `tool:curl {page_url}` |
| `-f` | Boolean flag (no value) | `tool:curl -s` |
| `-f value` | Flag with a value | `tool:jq -r '.name'` |
| `--flag=value` | Flag with a value, long form | `tool:curl --output=file.html` |

Multiple args are space-separated as in a shell. Quote values that contain spaces: `tool:echo "hello world"`.

## Defaults and shortcuts

- Steps without `after` are sequential: step N implicitly depends on step N-1.
- Step 1 is always the first runnable step (it implicitly depends on step 0).
- Steps with no outgoing dependents and no `goto` implicitly fall through to step 9999 (end).
- `wait_human` pauses execution until the user responds. The response becomes the step's output.

## Outputs

A step may name its output using `=> name`. Later steps may reference named outputs inside prompts and tool arguments using `{name}` interpolation.

Example:

```text
1. tool:curl -s https://example.com => page
2. llm "summarize {page}" => summary
3. tool:save_note --text={summary}
```

Notes:

- If multiple parents exist, prefer naming the specific parent output you want to reference.
- If a step has no `=> name`, its output is still available to the executor/LLM, but it cannot be referenced by name.

## Conditions

Conditions gate whether a step runs when its dependency completes.

### Condition subject

A condition is evaluated against the output of the dependency that triggered the step.

- If the step has a single dependency, the condition is evaluated against that dependency's output.
- If the step has multiple dependencies, the condition is evaluated against the dependency whose completion makes the step eligible to run (i.e., "the triggering parent"). If you need unambiguous gating, use `=>` to name outputs and refer to them explicitly in the condition via `has(...)`, `eq(...)`, etc.
- To test a specific named output rather than the triggering parent, prefix the predicate with the output name: `output_name contains("text")`, `output_name has(key)`, etc.

### Condition language

To keep conditions short and phone-friendly, use a small set of functions and operators. The LLM may still interpret the semantics, but these forms are preferred:

- **status tokens**: `succeeded`, `failed`
- **text predicates**: `contains("text")`, `match(/regex/)`
- **qualified text predicates**: `output_name contains("text")`, `output_name match(/regex/)` — test a specific named output
- **field predicates** (for structured outputs): `has(key)`, `eq(key,"value")`
- **boolean ops**: `and`, `or`, `not` (parentheses optional)

Examples:

```text
4. llm "fix failing tests" (after 3, if failed, goto 3)
5. tool:save_db (after 2, if contains("approved"))
6. llm "ask for missing info" (after 2, if not has("email"))
7. tool:flag_external (after 1, if page_url contains("abcd.com"))
```

### Failure detection

`failed` and `succeeded` work uniformly across all step types. `failed` means the step did not accomplish its goal; `succeeded` means it did. The executor handles detecting and routing failures appropriately for each step type.

**Failure routing pattern:** when a step produces a named output consumed by downstream steps, add an `if failed` sibling branch to route to an alternative action (retry, fallback source, error report) when the step cannot produce the expected result. See *Extractive LLM with failure handling* in Examples.

## Branching

Multiple steps can reference the same parent with different conditions:

```text
3. tool:save_db (after 2, if contains("approved"))
4. llm "explain rejection" (after 2, if contains("rejected"))
```

## Convergence

A step that depends on multiple parents waits for **all** of them to complete before running (AND-join):

```text
5. llm "summarize both results" (after 3, 4)
```

Step 5 runs only after both step 3 and step 4 have completed.

## Loops

Use `goto N` to create cycles. Combine with `if` for conditional looping:

```text
3. tool:run_tests => tests
4. llm "fix failing tests" (after 3, if failed, goto 3)
```

Step 4 runs only if tests fail, then jumps back to step 3. When tests pass, step 3 falls through to the next step instead.

## Edge cases

- **Parallel execution**: two steps with the same `after` and no `if` run in parallel.
- **Condition matching**: conditions are interpreted against the triggering parent's output; prefer the *Condition language* forms for consistency.
- **Missing conditions**: if a step has conditional siblings but no condition itself, it acts as the default/else branch.
- **Loop exit**: a `goto` with an `if` condition only loops when the condition is met. Otherwise, execution continues forward normally.

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

Note: step 2 uses `after 0` to indicate no dependency on step 1 (both run in parallel from the start). Step 3 waits for both to complete (AND-join).

### Extractive LLM with failure handling

```text
1. tool:curl -s https://example.com => page
2. llm "extract the pricing table from {page}" => pricing
3. tool:save_note --text={pricing}
4. llm "pricing not found, describe what the page contains instead" (after 2, if failed)
```

Step 3 (default branch) saves the extracted pricing on success. Step 4 runs if step 2 failed — whether due to an API error or because the content wasn't found — and produces a useful fallback description.

### Loop: iterative dev cycle

```text
1. llm "Read PRD.md, split to tasks, save to TASKS.md" => tasks
2. llm "Implement next task from TASKS.md, mark done" => impl
3. tool:run_tests => tests
4. llm "Fix failing tests" (after 3, if failed, goto 3)
5. llm "Prepare implementation summary" (after 3, if succeeded and contains("tasks remain"), goto 2)
```

Inner loop: steps 3-4 repeat until tests pass. Outer loop: steps 2-5 repeat until all tasks are done. When no tasks remain, step 5 falls through to step 9999 (end).
