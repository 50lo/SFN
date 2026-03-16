#!/usr/bin/env python3
"""Pipeline: Review Pipeline
Generated from SFN by sfn-to-python

Example input (SFN):

1. tool:curl -s https://example.com => page
2. llm "summarize {page}" => summary
3. wait_human => decision
4. tool:save_db --payload={summary} (after 3, if contains("approved"))
5. llm "draft rejection reason" (after 3, if contains("rejected"))

Analysis:

- Step 1 => page: referenced by step 2 ({page}). Assign to variable `page`.
- Step 2 => summary: referenced by step 4 ({summary}). extract=True because
  downstream tool step uses it. Prompt contains {page} -> f-string substitution.
- Step 3 => decision: wait_human. Used by steps 4 and 5 via contains().
- Step 4: if contains("approved") -> "approved" in decision. Tool command uses
  {summary} -> f-string.
- Step 5: if contains("rejected") -> "rejected" in decision. No {var} refs,
  generative LLM -> extract=False.
"""
import argparse
import os
import shutil
import subprocess
import sys

# ── Agent configuration ──────────────────────────────────────

SUPPORTED_AGENTS = ("claude", "gemini", "codex", "opencode", "rovodev")
AGENT_BINARIES = {
    "claude": "claude",
    "gemini": "gemini",
    "codex": "codex",
    "opencode": "opencode",
    "rovodev": "acli",
}
DEFAULT_AGENT = "claude"
DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "gemini": "gemini-3-flash-preview",
    "codex": "gpt-5.2",
    "opencode": "gpt-5.2",
    "rovodev": None,
}
INSTALL_HINTS = {
    "claude": "Install Claude Code and ensure 'claude' is on PATH.",
    "gemini": "Install Gemini CLI and ensure 'gemini' is on PATH.",
    "codex": "Install Codex CLI and ensure 'codex' is on PATH.",
    "opencode": "Install OpenCode CLI and ensure 'opencode' is on PATH.",
    "rovodev": "Install Atlassian CLI and ensure 'acli' is on PATH.",
}


def resolve_agent(args):
    """Return the selected coding agent and model."""
    agent = args.agent or os.environ.get("SFN_AGENT") or DEFAULT_AGENT
    if agent not in SUPPORTED_AGENTS:
        print(
            f"ERROR: unsupported agent '{agent}'. "
            f"Supported agents: {', '.join(SUPPORTED_AGENTS)}",
            file=sys.stderr,
        )
        sys.exit(1)
    model = args.model or os.environ.get("SFN_MODEL")
    if not model:
        model = DEFAULT_MODELS[agent]
    return agent, model


def check_agent(agent):
    """Verify the selected coding agent CLI is available."""
    binary = AGENT_BINARIES[agent]
    if shutil.which(binary):
        return
    print(
        f"ERROR: '{binary}' CLI not found on PATH.\n"
        "\n"
        f"{INSTALL_HINTS[agent]}\n"
        "\n"
        "Then run this script again.",
        file=sys.stderr,
    )
    sys.exit(1)


def build_agent_command(agent, model, prompt):
    """Return (command, env) for the selected coding agent."""
    env = os.environ.copy()
    if agent == "claude":
        env.pop("CLAUDECODE", None)
        command = ["claude"]
        if model:
            command.extend(["--model", model])
        command.extend(["-p", prompt, "--dangerously-skip-permissions"])
        return command, env
    if agent == "gemini":
        command = ["gemini"]
        if model:
            command.extend(["--model", model])
        command.extend(["-y", "-p", prompt])
        return command, env
    if agent == "codex":
        command = ["codex", "exec"]
        if model:
            command.extend(["--model", model])
        command.append(prompt)
        return command, env
    if agent == "rovodev":
        command = ["acli", "rovodev", "run", prompt, "--yolo"]
        return command, env
    command = ["opencode", "run"]
    if model:
        command.extend(["--model", model])
    command.extend(["-p", prompt])
    return command, env


# ── Step runners ─────────────────────────────────────────────

def run_llm(prompt, agent, model, extract=False):
    """Call coding agent CLI. Returns (result, error)."""
    if extract:
        prompt += (
            "\n\nIMPORTANT: Respond with ONLY the raw result — "
            "no explanation, no markdown, no code fences. "
            "If you cannot complete this task, respond with "
            "exactly: ERROR: <brief reason>"
        )
    preview = (prompt[:100] + "...") if len(prompt) > 100 else prompt
    preview = preview.replace("\n", " ")
    print(f"  > llm[{agent}]: {preview}")
    command, env = build_agent_command(agent, model, prompt)
    result = subprocess.run(
        command, capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        error = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit code {result.returncode}"
        )
        print(f"  x Agent error: {error}")
        return None, error
    text = result.stdout.strip()
    if extract and text.upper().startswith("ERROR:"):
        error = text.split(":", 1)[1].strip()
        print(f"  x LLM could not complete task: {error}")
        return None, error
    print(f"  ok ({len(text)} chars)")
    return text, None


def run_tool(command, label=None):
    """Run a shell command. Returns (stdout, error)."""
    display = label or (command[:80] + "..." if len(command) > 80 else command)
    print(f"  > tool: {display}")
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        error = result.stderr.strip() or f"exit code {result.returncode}"
        print(f"  x Tool failed: {error}")
        return None, error
    text = result.stdout.strip()
    print(f"  ok ({len(text)} chars)")
    return text, None


def wait_human(prompt="Your input"):
    """Pause for human input. Returns (response, error)."""
    print(f"\n  ?  {prompt}")
    response = input("  > ").strip()
    if not response:
        return None, "empty input"
    return response, None


# ── Pipeline ─────────────────────────────────────────────────

def main(args):
    agent, model = resolve_agent(args)
    check_agent(agent)
    print("Pipeline: Review Pipeline")
    print(f"Agent: {agent}" + (f" ({model})" if model else ""))
    print()

    # Step 1: fetch page
    print("[Step 1] Fetch page")
    page, err = run_tool('curl -s https://example.com', label="curl")
    if err:
        print(f"Pipeline stopped at step 1: {err}")
        return

    # Step 2: summarize
    print("[Step 2] Summarize page")
    summary, err = run_llm(
        f"summarize the following:\n\n{page}",
        agent=agent,
        model=model,
        extract=True,
    )
    if err:
        print(f"Pipeline stopped at step 2: {err}")
        return

    # Step 3: human review
    print("[Step 3] Human review")
    decision, err = wait_human("Type 'approved' or 'rejected'")
    if err:
        print(f"Pipeline stopped at step 3: {err}")
        return

    # Steps 4-5: branch on decision
    if "approved" in decision:
        # Step 4 (after 3, if contains("approved"))
        print("[Step 4] Save to database")
        _, err = run_tool(
            f'save_db --payload="{summary}"',
            label="save_db",
        )
        if err:
            print(f"Pipeline stopped at step 4: {err}")
            return
    elif "rejected" in decision:
        # Step 5 (after 3, if contains("rejected"))
        print("[Step 5] Draft rejection reason")
        _, err = run_llm(
            "draft a rejection reason for the submitted page",
            agent=agent,
            model=model,
        )
        if err:
            print(f"Pipeline stopped at step 5: {err}")
            return
    else:
        print(f"Unexpected decision: '{decision}' (expected 'approved' or 'rejected')")
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline: Review Pipeline")
    parser.add_argument(
        "--agent",
        choices=SUPPORTED_AGENTS,
        help="Coding agent CLI to use for llm steps",
    )
    parser.add_argument(
        "--model",
        help="Override the default model for the selected agent",
    )
    parser.add_argument(
        "--max-loops", type=int, default=10,
        help="Maximum iterations for any loop",
    )
    args = parser.parse_args()
    main(args)
