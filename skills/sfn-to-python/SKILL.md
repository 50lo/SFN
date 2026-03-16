---
name: sfn-to-python
description: >
  Convert Step Flow Notation (SFN) workflows into executable Python scripts.
  Use this skill whenever a user provides a multi-step workflow in SFN format and wants
  a Python script, or when the user describes a workflow and asks for a runnable Python
  pipeline. Also trigger when the user mentions "SFN to Python", "convert to Python",
  "generate Python script", "python pipeline", or "sfn-to-python".
---

# SFN to Python

Convert Step Flow Notation into standalone executable Python scripts. The generated scripts have zero dependencies beyond Python 3 and one supported coding-agent CLI on PATH. Designed for developers learning to write workflows — clear error reporting is the top priority.

Before generating, read the script template at [assets/template.py](assets/template.py) and the worked example at [references/example_output.py](references/example_output.py).

## Step Flow Notation (input format)

SFN is a concise text format for multi-step workflows.

### Step syntax

```
N. type[:param] [args...] ["prompt"] ([after X[,Y...]][, if cond][, goto N][, => name])
```

| Part | Meaning |
|------|---------|
| `N` | Step number (1-based) |
| `type` | `tool`, `llm`, or `wait_human` |
| `:param` | Tool name for `tool` type (e.g. `tool:fetch_url`) |
| `args` | Shell-style arguments (see below) |
| `"prompt"` | Inline instruction for `llm` steps |
| `after X,Y` | Dependencies. Omitted = depends on N-1. `after 0` = depends on flow start |
| `if cond` | Conditional gate on parent output |
| `goto N` | Loop back to step N after completion |
| `=> name` | Name this step's output for `{name}` interpolation in later steps |

### Tool argument syntax

Tool args use shell-passthrough style — the args after `tool:name` are passed verbatim as a shell command, so write them exactly as you would at a terminal:

| Form | Meaning | Example |
|------|---------|---------|
| `-f` | Boolean flag (no value) | `tool:curl -s` |
| `--flag` | Boolean flag, long form | `tool:curl --silent` |
| `-f value` | Flag with value | `tool:jq -r '.name'` |
| `--flag=value` | Flag with value, long form | `tool:curl --output=file.html` |
| `bareword` | Positional argument | `tool:echo hello` |
| `{var}` | Interpolated variable (positional or as a value) | `tool:curl -s {page_url}` |

Multiple args are space-separated as in a shell. Quote values that contain spaces: `tool:echo "hello world"`.

### Defaults

- Step N implicitly depends on step N-1 when `after` is omitted.
- Step 1 implicitly depends on step 0 (flow start).
- Steps with no dependents are end nodes.
- `wait_human` pauses until user responds; response becomes step output.

### Conditions

Evaluated against the triggering parent's output:

- Status: `succeeded`, `failed`
- Text: `contains("text")`, `match(/regex/)`
- Structured: `has(key)`, `eq(key,"value")`
- Boolean: `and`, `or`, `not`

### Patterns

- **Parallel**: two steps with same `after`, no `if` -> run concurrently.
- **Branch**: same `after`, different `if` conditions -> conditional routing.
- **Converge**: one step with `after X, Y` -> waits for multiple parents.
- **Loop**: `goto N` (with optional `if`) -> cycle back.
- **Default branch**: among conditional siblings, a step without `if` acts as else.

## Python script (output format)

The generated script is a single self-contained `.py` file. All imports are from the Python standard library. The only external dependency is one supported coding-agent CLI on PATH for `llm` steps.

Every generated script follows the template in [assets/template.py](assets/template.py). Read it before generating.

### Supported coding agents

Generated scripts should support the same agent set and invocation patterns as `/Users/a/code/ghost/lib/ghost-agents.sh`:

| Agent | Command pattern | Default model |
|------|------------------|---------------|
| `claude` | `claude [--model MODEL] -p PROMPT --dangerously-skip-permissions` | `claude-sonnet-4-6` |
| `gemini` | `gemini [--model MODEL] -y -p PROMPT` | `gemini-3-flash-preview` |
| `codex` | `codex exec [--model MODEL] PROMPT` | `gpt-5.2` |
| `opencode` | `opencode run [--model MODEL] -p PROMPT` | `gpt-5.2` |
| `rovodev` | `acli rovodev run PROMPT [--yolo]` | *(config-file)* |

Rules:

- Default to `claude` unless the user explicitly asks for another agent.
- Always generate runtime selection via `--agent` and `--model` so the script can switch CLIs without regeneration.
- Also honor `SFN_AGENT` and `SFN_MODEL` environment variables.
- Use an explicit default model for every supported agent in generated scripts.

### Runner functions

| Function | SFN type | Returns | Failure detection |
|----------|----------|---------|-------------------|
| `run_tool(command, label)` | `tool:name` | `(stdout, error)` | Non-zero exit code |
| `run_llm(prompt, agent, model, extract)` | `llm` | `(text, error)` | CLI error (non-zero exit) + semantic failure (`ERROR:` prefix when `extract=True`) |
| `wait_human(prompt)` | `wait_human` | `(response, error)` | Empty input |

Every runner returns a `(result, error)` tuple. `error` is `None` on success, a descriptive string on failure. `result` is `None` on failure.

### The `extract` parameter

`extract=True` is set on `run_llm` when the LLM step has `=> name` and any downstream step references that name. It does two things:

1. **Appends a prompt suffix** asking the LLM to output only the raw result, or `ERROR: <reason>` if it cannot complete the task.
2. **Checks the response** for an `ERROR:` prefix and converts it into a `(None, error)` return — making semantic failures (LLM can't find the content) behave identically to API failures for downstream branching.

When `extract=False` (generative LLM steps with no critical named output), the LLM responds freely and only CLI errors are detected.

## Passing data between steps

Data flows through **Python variables**. No temp files needed (unlike the DOT/Attractor approach where `tool_command` cannot access engine context).

### Named outputs (`=> name`)

The SFN output name becomes a Python variable name:

```python
# SFN: tool:curl -s https://example.com => page
page, err = run_tool('curl -s https://example.com', label="curl")
```

### `{var}` in LLM prompts

Replace `{var}` with the Python variable via f-string. When the prompt contains `{var}`, the referenced data is already embedded in the prompt — no additional context is needed.

```python
# SFN: llm "summarize {page}" => summary
summary, err = run_llm(f"summarize the following:\n\n{page}", extract=True)
```

### `{var}` in tool arguments

Replace `{var}` with the Python variable via f-string in the shell command:

```python
# SFN: tool:curl {page2_url}
page2_html, err = run_tool(f'curl {page2_url}', label="curl")
```

### Sliding window context for LLM steps

When an LLM prompt does **not** reference any `{var}` that corresponds to its parent step's output, include the parent's result as context. This ensures the LLM always has the data it needs:

```python
# SFN step 3 produced page2_html
# SFN step 4: llm "Extract the title" (implicit after 3, no {var} refs)
result, err = run_llm(
    "Extract the title"
    f"\n\nContent from previous step:\n\n{page2_html}",
    extract=True
)
```

If the prompt already references the parent output via `{var}`, do **not** duplicate it as context.

### When to set `extract=True`

| Scenario | `extract` |
|----------|-----------|
| LLM step has `=> name` **and** any downstream step references `{name}` | `True` |
| LLM step has `=> name` but no downstream reference | `False` |
| LLM step has no `=> name` | `False` |

## LLM failure handling

### Two failure modes

**Mode A — CLI error**: the selected agent CLI exits with non-zero code (network failure, auth error, quota exceeded). Detected by checking `result.returncode != 0`.

**Mode B — Semantic failure**: The CLI succeeds but the LLM says "I couldn't find it." Detected by checking the response for an `ERROR:` prefix when `extract=True`.

Both modes return `(None, error_string)` from `run_llm`, so downstream `if err:` / `if not err:` branching handles them uniformly. The user's `if failed` and `if succeeded` branches just work — no special handling needed in the SFN.

### Error message format

Every failure prints a clear message before returning:

```
[Step 4] Extract misconception section
  > llm: Find Common misconception section and extract section co...
  x LLM could not complete task: The page does not contain a "Common misconception" section
```

The step label, the truncated prompt, and the specific error are always visible.

## Conversion rules

Apply these rules to translate SFN steps into Python code:

### 1. Script boilerplate

Every script gets the full template from [assets/template.py](assets/template.py): imports, `resolve_agent()`, `check_agent()`, `build_agent_command()`, the three runner functions, `main(args)`, and the `argparse` block.

### 2. Map steps to code blocks

For each SFN step N:

- **`tool:name`**: Generate `run_tool(command, label=tool_name)`. The command is the tool name + args as a shell string. If args contain `{var}`, use an f-string. If `=> name`, assign to a named variable.
- **`llm`**: Generate `run_llm(prompt, agent, model, extract=...)`. The prompt comes from the quoted instruction. If it contains `{var}`, use an f-string and embed the variable. If the prompt has no `{var}` referencing the parent step's output, prepend context from the parent. Set `extract=True` when `=> name` and downstream steps reference it.
- **`wait_human`**: Generate `wait_human(prompt)`. The prompt describes what input is expected.

### 3. Map dependencies to code ordering

- **Sequential** (no `after`): Steps appear in order in `main()`. Each step follows the previous one linearly.
- **`after X`**: The step appears after step X's code block (and any of X's conditional branches).
- **`after 0`**: The step runs at the start of `main()`, parallel with step 1 (see rule 9).

### 4. Map conditions to if/elif/else

**`if failed`** -> `if err:` branch after the parent step's runner call.

**`if succeeded`** -> `if not err:` branch, or the else clause if there's a sibling `if failed`.

**`if contains("text")`** -> `elif "text" in result:` after an `if err:` guard. Always check `err` first to avoid checking `contains` on a `None` result.

```python
result, err = run_step(...)
if err:
    # if failed branch (if present)
    ...
elif "approved" in result:
    # if contains("approved") branch
    ...
elif "rejected" in result:
    # if contains("rejected") branch
    ...
else:
    # default branch (if present)
    ...
```

**Default branch** (sibling with no condition): becomes the `else` clause.

When the only siblings are `if succeeded` and `if failed`:
```python
result, err = run_step(...)
if err:
    # if failed branch
    ...
else:
    # if succeeded branch (or default)
    ...
```

### 5. Map `goto N` to loops

A step with `goto N` creates a `for` loop wrapping steps N through the current step:

```python
for _loop in range(args.max_loops):
    # Step N
    result, err = run_step(...)
    if err:
        # if failed, goto N -> continue the loop
        ...
        continue
    # succeeded -> break out
    break
else:
    print(f"ERROR: Loop (steps N-M) exceeded {{args.max_loops}} iterations")
    return
```

The `for/else` pattern ensures a clear error message when the loop exceeds the maximum iterations.

### 6. Map parallel execution to ThreadPoolExecutor

When two or more steps share the same parent (or both use `after 0`) and have no conditions, they run in parallel:

```python
from concurrent.futures import ThreadPoolExecutor

def _parallel_step_1():
    # Step 1 code
    return run_tool('curl -s https://site-a.com')

def _parallel_step_2():
    # Step 2 code
    return run_tool('curl -s https://site-b.com')

with ThreadPoolExecutor() as pool:
    future_1 = pool.submit(_parallel_step_1)
    future_2 = pool.submit(_parallel_step_2)

a, err_a = future_1.result()
b, err_b = future_2.result()
if err_a:
    print(f"Step 1 failed: {err_a}")
    return
if err_b:
    print(f"Step 2 failed: {err_b}")
    return
```

Only add `from concurrent.futures import ThreadPoolExecutor` when the SFN actually uses parallel branches.

### 7. Map convergence to barrier

A step with `after X, Y` runs after both X and Y complete. When X and Y are parallel branches, this is natural — the `.result()` calls block until both finish. When X and Y are sequential branches (e.g., different conditional paths that converge), structure the code so the convergence step appears after all branches complete.

### 8. Connect end steps

Steps with no dependents (no step depends on them, no `goto`) are endpoints. After their code executes, `main()` returns naturally. No explicit `return` needed unless it's inside a branch.

### 9. Handle `wait_human`

```python
print("[Step 3] Approve or reject?")
decision, err = wait_human("Type 'approved' or 'rejected'")
if err:
    print(f"Pipeline stopped: {err}")
    return
```

### 10. Named outputs and variable names

Use the SFN output name directly as the Python variable name. Convert hyphens to underscores. If the name would shadow a Python builtin, append `_val` (e.g., `type` -> `type_val`).

## Example conversion

For a complete worked example (input SFN, analysis, and full output script), see [references/example_output.py](references/example_output.py). The example's docstring contains the input SFN and analysis; the code shows the expected output.

### Input (SFN)

```
1. tool:curl -s https://example.com => page
2. llm "summarize {page}" => summary
3. wait_human => decision
4. tool:save_db --payload={summary} (after 3, if contains("approved"))
5. llm "draft rejection reason" (after 3, if contains("rejected"))
```

### Analysis

- Step 1 `=> page`: referenced by step 2 (`{page}`). Assign to variable `page`.
- Step 2 `=> summary`: referenced by step 4 (`{summary}`). `extract=True` because downstream tool step uses it. Prompt contains `{page}` -> f-string substitution.
- Step 3 `=> decision`: `wait_human`. Used by steps 4 and 5 via `contains()`.
- Step 4: `if contains("approved")` -> `"approved" in decision`. Tool command uses `{summary}` -> f-string.
- Step 5: `if contains("rejected")` -> `"rejected" in decision`. No `{var}` refs, generative LLM -> `extract=False`.

### Output

See [references/example_output.py](references/example_output.py) for the full generated script.

## Output guidelines

- Generate a single `.py` file. All boilerplate (runners, imports, argparse) is included — the script must be runnable with just `python3 script.py`.
- For workflows with `llm` steps, include `--agent`, `--model`, `SFN_AGENT`, and `SFN_MODEL` support for `claude`, `gemini`, `codex`, and `opencode`.
- Use descriptive variable names from SFN output names (e.g., `page_html`, not `step_1_result`).
- Print `[Step N] Description` before each step so the user can follow execution.
- Every error path prints what failed and stops cleanly (no tracebacks).
- Only import `concurrent.futures` when the SFN uses parallel branches.
- Only include `--max-loops` in argparse when the SFN uses `goto` loops.
- Add comments referencing the SFN step number and condition for each code block.
- Use single quotes for shell commands, f-strings when interpolating variables.
- If the user explicitly asks for one agent, set `DEFAULT_AGENT` to that agent in the generated script; otherwise leave it as `claude`.
- Keep the generated code simple and readable — this is a learning tool.
