---
name: sfn-to-acp
description: >
  Convert Step Flow Notation (SFN) workflows into executable Python scripts
  that call coding agents through the Agent Client Protocol (ACP). Use this skill
  whenever a user provides a multi-step workflow in SFN format and wants a Python
  script, or when the user describes a workflow and asks for a runnable ACP-based
  pipeline. Also trigger when the user mentions "SFN to ACP", "sfn-to-acp",
  "ACP pipeline", "Agent Client Protocol", or asks to generate a Python workflow
  that talks to coding agents over ACP.
---

# SFN to ACP

Convert Step Flow Notation into standalone executable Python scripts. The generated
scripts keep the same user-facing workflow as `sfn-to-python`: same SFN syntax,
same branching/loop behavior, same `--agent` / `--model` interface, same
step-by-step logging. The only runtime difference is that `llm` steps talk to
coding agents through ACP instead of spawning CLI prompt commands directly.

Before generating, read the script template at [assets/template.py](assets/template.py)
and the worked example at [references/example_output.py](references/example_output.py).

## Step Flow Notation (input format)

SFN is a concise text format for multi-step workflows.

### Step syntax

```text
N. type[:param[:subparam]] [args...] ["prompt"] ([after X[,Y...]][, if cond][, goto N][, => name])
```

| Part | Meaning |
|------|---------|
| `N` | Step number (1-based) |
| `type` | `tool`, `llm`, or `wait_human` |
| `:param` | Tool name for `tool`, or coding agent for `llm` |
| `:subparam` | Model for `llm`; requires `:param` |
| `args` | Shell-style arguments (see below) |
| `"prompt"` | Inline instruction for `llm` steps |
| `after X,Y` | Dependencies. Omitted = depends on N-1. `after 0` = depends on flow start |
| `if cond` | Conditional gate on parent output |
| `goto N` | Loop back to step N after completion |
| `=> name` | Name this step's output for `{name}` interpolation in later steps |

### LLM selectors

`llm` steps may pin a coding agent and model:

```text
llm[:agent[:model]] "prompt"
```

- `llm "..."` -> use script defaults
- `llm:codex "..."` -> use `codex` and its ACP agent default model
- `llm:codex:gpt-5.4 "..."` -> use `codex` and request that model through ACP session config
- `llm::gpt-5.4 "..."` -> invalid

### Tool argument syntax

Tool args use shell-passthrough style — the args after `tool:name` are passed verbatim
as a shell command, so write them exactly as you would at a terminal:

| Form | Meaning | Example |
|------|---------|---------|
| `-f` | Boolean flag (no value) | `tool:curl -s` |
| `--flag` | Boolean flag, long form | `tool:curl --silent` |
| `-f value` | Flag with value | `tool:jq -r '.name'` |
| `--flag=value` | Flag with value, long form | `tool:curl --output=file.html` |
| `bareword` | Positional argument | `tool:echo hello` |
| `{var}` | Interpolated variable (positional or as a value) | `tool:curl -s {page_url}` |

Multiple args are space-separated as in a shell. Quote values that contain spaces:
`tool:echo "hello world"`.

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

The generated script is a single self-contained `.py` file. It uses the Python
standard library plus the `agent-client-protocol` package for `llm` steps.
`tool:` and `wait_human` behavior is otherwise the same as `sfn-to-python`.

Every generated script follows the template in [assets/template.py](assets/template.py).
Read it before generating.

### Runtime requirements

- Python 3.10+
- `pip install agent-client-protocol`
- At least one ACP-compatible coding agent available on PATH

The ACP SDK is imported lazily inside `run_llm()`, so scripts with no `llm` steps
still run without the package installed.

ACP agent subprocesses should inherit the full current environment so existing
auth tokens and agent-specific env vars keep working.

### Supported coding agents

Generated scripts should support these ACP-backed agents:

| Agent | Default ACP launch command | Model behavior |
|------|-----------------------------|----------------|
| `claude` | `npx -y @agentclientprotocol/claude-agent-acp` | Agent default unless model requested |
| `gemini` | `npx -y @google/gemini-cli --acp` | Agent default unless model requested |
| `codex` | `npx -y @zed-industries/codex-acp` | Agent default unless model requested |
| `opencode` | `opencode acp` | Agent default unless model requested |

Rules:

- Default to `claude` unless the user explicitly asks for another agent.
- Always generate `--agent` and `--model` as defaults for plain `llm` steps.
- Also honor `SFN_AGENT` and `SFN_MODEL` environment variables.
- Plain `llm` uses the selected agent's ACP default model unless `--model` or `SFN_MODEL` is set.
- `llm:agent` overrides the default agent for that step and uses that agent's ACP default model.
- `llm:agent:model` overrides both for that step and requests the model through ACP session config.
- Allow advanced users to override the launch command with `SFN_CLAUDE_COMMAND`,
  `SFN_GEMINI_COMMAND`, `SFN_CODEX_COMMAND`, or `SFN_OPENCODE_COMMAND`.

### Permission handling

All ACP permission requests must be auto-approved. Generated scripts are intended
to run inside a sandboxed environment where that is safe, so the client callback
should deterministically accept every request without prompting the human.

### Runner functions

| Function | SFN type | Returns | Failure detection |
|----------|----------|---------|-------------------|
| `run_tool(command, label)` | `tool:name` | `(stdout, error)` | Non-zero exit code |
| `run_llm(prompt, agent, model, extract)` | `llm` | `(text, error)` | ACP/session error + semantic failure (`ERROR:` prefix when `extract=True`) |
| `wait_human(prompt)` | `wait_human` | `(response, error)` | Empty input |

Every runner returns a `(result, error)` tuple. `error` is `None` on success,
a descriptive string on failure. `result` is `None` on failure.

### ACP session model selection

When a model is requested, configure it through ACP session model/config APIs
instead of process flags. The generated script should:

1. Open a fresh ACP session for the `llm` step.
2. Inspect the session's config options.
3. Prefer the agent's explicit session model state when available.
4. Fall back to config options when model state is not exposed.
5. Set the requested model before calling `session/prompt`.

If the ACP agent does not expose a model selector, or the requested model is not
offered, return a clear error instead of silently ignoring the request.

### Fresh session per LLM step

Create a fresh ACP session for every `run_llm()` call. This keeps behavior close
to `sfn-to-python`, where each `llm` step is isolated unless the SFN explicitly
passes prior outputs via `{var}` or sliding-window context.

## The `extract` parameter

`extract=True` is set on `run_llm` when the LLM step has `=> name` and any downstream
step references that name. It does two things:

1. **Appends a prompt suffix** asking the LLM to output only the raw result, or
   `ERROR: <reason>` if it cannot complete the task.
2. **Checks the response** for an `ERROR:` prefix and converts it into a
   `(None, error)` return — making semantic failures behave identically to ACP
   transport failures for downstream branching.

When `extract=False` (generative LLM steps with no critical named output), the
LLM responds freely and only ACP/session errors are detected.

## Passing data between steps

Data flows through **Python variables**. No temp files needed.

### Named outputs (`=> name`)

The SFN output name becomes a Python variable name:

```python
# SFN: tool:curl -s https://example.com => page
page, err = run_tool('curl -s https://example.com', label="curl")
```

### `{var}` in LLM prompts

Replace `{var}` with the Python variable via f-string:

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

When an LLM prompt does **not** reference any `{var}` that corresponds to its
parent step's output, include the parent's result as context:

```python
result, err = run_llm(
    "Extract the title"
    f"\n\nContent from previous step:\n\n{page2_html}",
    extract=True
)
```

If the prompt already references the parent output via `{var}`, do **not**
duplicate it as context.

### When to set `extract=True`

| Scenario | `extract` |
|----------|-----------|
| LLM step has `=> name` **and** any downstream step references `{name}` | `True` |
| LLM step has `=> name` but no downstream reference | `False` |
| LLM step has no `=> name` | `False` |

## Conversion rules

Apply these rules to translate SFN steps into Python code:

### 1. Script boilerplate

Every script gets the full template from [assets/template.py](assets/template.py):
imports, agent resolution, ACP launch-command resolution, the three runner
functions, `main(args)`, and the `argparse` block.

### 2. Map steps to code blocks

For each SFN step N:

- **`tool:name`**: Generate `run_tool(command, label=tool_name)`. The command is
  the tool name + args as a shell string. If args contain `{var}`, use an f-string.
  If `=> name`, assign to a named variable.
- **`llm[:agent[:model]]`**: Generate `run_llm(prompt, agent, model, extract=...)`.
  The prompt comes from the quoted instruction. If it contains `{var}`, use an
  f-string and embed the variable. If the prompt has no `{var}` referencing the
  parent step's output, prepend context from the parent. Set `extract=True` when
  `=> name` and downstream steps reference it. Plain `llm` uses the script default
  agent/model. `llm:agent` uses `resolve_llm_config(..., step_agent="agent")`.
  `llm:agent:model` uses `resolve_llm_config(..., step_agent="agent", step_model="model")`.
- **`wait_human`**: Generate `wait_human(prompt)`. The prompt describes what input
  is expected.

### 3. Map dependencies to code ordering

- **Sequential** (no `after`): Steps appear in order in `main()`.
- **`after X`**: The step appears after step X's code block.
- **`after 0`**: The step runs at the start of `main()`, parallel with step 1.

### 4. Map conditions to if/elif/else

**`if failed`** -> `if err:` branch after the parent step's runner call.

**`if succeeded`** -> `if not err:` branch, or the else clause if there's a sibling
`if failed`.

**`if contains("text")`** -> `elif "text" in result:` after an `if err:` guard.

### 5. Map `goto N` to loops

Use the same `for _loop in range(args.max_loops)` structure as `sfn-to-python`.

### 6. Map parallel execution to ThreadPoolExecutor

Use the same `ThreadPoolExecutor` approach as `sfn-to-python` when two or more
steps share the same parent and have no conditions.

### 7. Map convergence to barrier

A step with `after X, Y` runs after both X and Y complete. Structure the code so
the convergence step appears after all parent branches complete.

### 8. Connect end steps

Steps with no dependents are endpoints. After their code executes, `main()`
returns naturally.

### 9. Handle `wait_human`

Use the same `wait_human()` pattern as `sfn-to-python`.

### 10. Named outputs and variable names

Use the SFN output name directly as the Python variable name. Convert hyphens to
underscores. If the name would shadow a Python builtin, append `_val`.

## Example conversion

For a complete worked example, see [references/example_output.py](references/example_output.py).
The example's docstring contains the input SFN and analysis; the code shows the
expected output.

## Output guidelines

- Generate a single `.py` file. All boilerplate is included — the script must be
  runnable with `python3 script.py`.
- Keep `--agent`, `--model`, `SFN_AGENT`, and `SFN_MODEL` support so existing
  `sfn-to-python` users do not need to learn a new interface.
- Keep `tool:` and `wait_human` behavior unchanged from `sfn-to-python`.
- Auto-approve every ACP permission request.
- Print `[Step N] Description` before each step so the user can follow execution.
- Every error path prints what failed and stops cleanly.
- Only import `concurrent.futures` when the SFN uses parallel branches.
- Only include `--max-loops` in argparse when the SFN uses `goto` loops.
- Add comments referencing the SFN step number and condition for each code block.
- Use single quotes for shell commands, f-strings when interpolating variables.
- If the user explicitly asks for one agent, set `DEFAULT_AGENT` to that agent in
  the generated script; otherwise leave it as `claude`.
- Keep the generated code simple and readable — this is a prototype tool, not an
  enterprise workflow runtime.
