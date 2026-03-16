#!/usr/bin/env python3
"""Pipeline: <descriptive name>
Generated from SFN by sfn-to-python
"""
import os
import argparse
import shutil
import subprocess
import sys
# import concurrent.futures  # only when parallel branches exist

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
    """Call coding agent CLI. Returns (result, error).

    extract=True adds clean-output instructions and detects semantic
    failures (LLM responding with ERROR: prefix).
    """
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
    print("Pipeline: <name>")
    print(f"Agent: {agent}" + (f" ({model})" if model else ""))
    print()

    # ... generated step code here ...


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline: <name>")
    parser.add_argument(
        "--agent",
        choices=SUPPORTED_AGENTS,
        help="Coding agent CLI to use for llm steps",
    )
    parser.add_argument(
        "--model",
        help="Override the default model for the selected agent",
    )
    parser.add_argument("--max-loops", type=int, default=10,
                        help="Maximum iterations for any loop")
    args = parser.parse_args()
    main(args)
