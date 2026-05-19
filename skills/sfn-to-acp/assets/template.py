#!/usr/bin/env python3
"""Pipeline: <descriptive name>
Generated from SFN by sfn-to-acp
"""
import argparse
import asyncio
import os
import shlex
import shutil
import subprocess
import sys
from uuid import uuid4

# import concurrent.futures  # only when parallel branches exist

# ── Agent configuration ──────────────────────────────────────

SUPPORTED_AGENTS = ('claude', 'gemini', 'codex', 'opencode')
DEFAULT_AGENT = 'claude'
DEFAULT_MODELS = {
    'claude': None,
    'gemini': None,
    'codex': None,
    'opencode': None,
}
AGENT_COMMANDS = {
    'claude': ['npx', '-y', '@agentclientprotocol/claude-agent-acp'],
    'gemini': ['npx', '-y', '@google/gemini-cli', '--acp'],
    'codex': ['npx', '-y', '@zed-industries/codex-acp'],
    'opencode': ['opencode', 'acp'],
}
COMMAND_ENV_VARS = {
    'claude': 'SFN_CLAUDE_COMMAND',
    'gemini': 'SFN_GEMINI_COMMAND',
    'codex': 'SFN_CODEX_COMMAND',
    'opencode': 'SFN_OPENCODE_COMMAND',
}
INSTALL_HINTS = {
    'claude': (
        "Install the Claude ACP agent or set SFN_CLAUDE_COMMAND to your local "
        "ACP launch command."
    ),
    'gemini': (
        "Install Gemini CLI with ACP support or set SFN_GEMINI_COMMAND to your "
        "local ACP launch command."
    ),
    'codex': (
        "Install codex-acp or set SFN_CODEX_COMMAND to your local ACP launch "
        "command."
    ),
    'opencode': (
        "Install OpenCode with ACP support or set SFN_OPENCODE_COMMAND to your "
        "local ACP launch command."
    ),
}
CHECKED_AGENTS = set()


def resolve_agent(args):
    """Return the default agent and model for plain llm steps."""
    agent = args.agent or os.environ.get('SFN_AGENT') or DEFAULT_AGENT
    if agent not in SUPPORTED_AGENTS:
        print(
            f"ERROR: unsupported agent '{agent}'. "
            f"Supported agents: {', '.join(SUPPORTED_AGENTS)}",
            file=sys.stderr,
        )
        sys.exit(1)
    model = args.model or os.environ.get('SFN_MODEL')
    if model is None:
        model = DEFAULT_MODELS[agent]
    return agent, model


def resolve_llm_config(default_agent, default_model, step_agent=None, step_model=None):
    """Return the effective agent/model for one llm step."""
    if step_model and not step_agent:
        raise ValueError('step_model requires step_agent')
    agent = step_agent or default_agent
    if step_model is not None:
        model = step_model
    elif step_agent:
        model = DEFAULT_MODELS[agent]
    else:
        model = default_model
    return agent, model


def resolve_agent_command(agent):
    """Return the ACP launch command for one agent."""
    env_var = COMMAND_ENV_VARS[agent]
    override = os.environ.get(env_var)
    if override:
        return shlex.split(override)
    return list(AGENT_COMMANDS[agent])


def check_agent(agent):
    """Verify the selected ACP launch command is available."""
    if agent in CHECKED_AGENTS:
        return
    command = resolve_agent_command(agent)
    binary = command[0]
    if shutil.which(binary):
        CHECKED_AGENTS.add(agent)
        return
    print(
        f"ERROR: ACP launch command not found for agent '{agent}'.\n"
        f"Tried: {' '.join(command)}\n\n"
        f"{INSTALL_HINTS[agent]}\n"
        f"You can also override the command with {COMMAND_ENV_VARS[agent]}.\n",
        file=sys.stderr,
    )
    sys.exit(1)


def _load_acp_sdk():
    """Import ACP SDK lazily so tool-only scripts do not require it."""
    try:
        from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
        from acp.interfaces import Client
    except ImportError:
        print(
            "ERROR: Missing Python dependency 'agent-client-protocol'.\n\n"
            "Install it with:\n"
            "  pip install agent-client-protocol\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return PROTOCOL_VERSION, spawn_agent_process, text_block, Client


def _to_plain_data(value):
    """Convert SDK objects into plain Python data."""
    if hasattr(value, 'model_dump'):
        return value.model_dump(by_alias=True)
    if isinstance(value, dict):
        return {key: _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    return value


def _get_field(value, *names, default=None):
    """Read a field from either an object or dict."""
    if value is None:
        return default
    plain = _to_plain_data(value)
    if isinstance(plain, dict):
        for name in names:
            if name in plain:
                return plain[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _extract_text_blocks(content):
    """Return text fragments from ACP text content blocks."""
    plain = _to_plain_data(content)
    if plain is None:
        return []
    if isinstance(plain, str):
        return [plain]
    if isinstance(plain, dict):
        if plain.get('type') == 'text':
            text = plain.get('text')
            return [text] if text else []
        parts = []
        for key in ('content', 'items', 'parts'):
            if key in plain:
                parts.extend(_extract_text_blocks(plain[key]))
        return parts
    if isinstance(plain, list):
        parts = []
        for item in plain:
            parts.extend(_extract_text_blocks(item))
        return parts
    return []


def _normalize_name(value):
    """Normalize strings for loose config-option matching."""
    return ''.join(ch for ch in value.lower() if ch.isalnum())


def _find_model_option(config_options):
    """Find the ACP config option that controls model selection."""
    for option in config_options:
        category = _get_field(option, 'category')
        option_id = _get_field(option, 'optionId', 'option_id', 'id', default='')
        name = _get_field(option, 'name', default='')
        if category == 'model':
            return option
        if 'model' in _normalize_name(option_id) or 'model' in _normalize_name(name):
            return option
    return None


def _resolve_model_value(model_option, requested_model):
    """Resolve a user-facing model string to one ACP option value."""
    choices = _get_field(model_option, 'choices', 'options', default=[]) or []
    if not choices:
        return requested_model

    target = _normalize_name(requested_model)
    candidates = []
    for choice in choices:
        value = _get_field(choice, 'value', default='')
        name = _get_field(choice, 'name', default='')
        for candidate in (value, name):
            if candidate and _normalize_name(candidate) == target:
                return value or name
            if candidate and target in _normalize_name(candidate):
                candidates.append(value or name)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _format_model_choices(model_option):
    """Format model choices for error messages."""
    choices = _get_field(model_option, 'choices', 'options', default=[]) or []
    values = []
    for choice in choices:
        value = _get_field(choice, 'value', default='')
        name = _get_field(choice, 'name', default='')
        if value:
            values.append(value)
        elif name:
            values.append(name)
    if not values:
        return 'agent default only'
    return ', '.join(values)


class _ACPClientBase:
    """Mixin holding streamed text and permission behavior."""

    def __init__(self):
        self.text_chunks = []

    def collected_text(self):
        return ''.join(self.text_chunks).strip()

    async def session_update(self, session_id, update, **_kwargs):
        update_type = _get_field(update, 'sessionUpdate', 'session_update')
        if update_type in ('agent_message_chunk', 'agent_message'):
            content = _get_field(update, 'content')
            self.text_chunks.extend(_extract_text_blocks(content))

    async def request_permission(self, options, session_id=None, tool_call=None, **_kwargs):
        options = _to_plain_data(options) or []
        if not options:
            return {'outcome': {'outcome': 'cancelled'}}
        selected = options[0]
        option_id = _get_field(selected, 'optionId', 'option_id', 'id')
        return {
            'outcome': {
                'outcome': 'selected',
                'optionId': option_id,
            }
        }


async def _run_llm_async(prompt, agent, model):
    """Execute one ACP prompt turn and return (text, error)."""
    PROTOCOL_VERSION, spawn_agent_process, text_block, Client = _load_acp_sdk()

    class ACPClient(_ACPClientBase, Client):
        pass

    client = ACPClient()
    command = resolve_agent_command(agent)

    try:
        async with spawn_agent_process(
            client,
            *command,
            env=os.environ.copy(),
        ) as connection:
            conn = connection[0] if isinstance(connection, tuple) else connection
            await conn.initialize(protocol_version=PROTOCOL_VERSION)
            session = await conn.new_session(cwd=os.getcwd())
            session_id = _get_field(session, 'sessionId', 'session_id')
            model_state = _get_field(session, 'models')
            config_options = _get_field(
                session,
                'configOptions',
                'config_options',
                default=[],
            ) or []

            if model:
                if model_state:
                    available_models = _get_field(
                        model_state,
                        'availableModels',
                        'available_models',
                        default=[],
                    ) or []
                    resolved_model = None
                    target = _normalize_name(model)
                    for model_info in available_models:
                        model_id = _get_field(model_info, 'modelId', 'model_id', default='')
                        model_name = _get_field(model_info, 'name', default='')
                        for candidate in (model_id, model_name):
                            if candidate and _normalize_name(candidate) == target:
                                resolved_model = model_id or candidate
                                break
                            if candidate and target in _normalize_name(candidate):
                                resolved_model = model_id or candidate
                        if resolved_model:
                            break
                    if not resolved_model:
                        available = ', '.join(
                            _get_field(item, 'modelId', 'model_id', default='')
                            or _get_field(item, 'name', default='')
                            for item in available_models
                        )
                        return None, (
                            f"Model '{model}' is not available for ACP agent '{agent}'. "
                            f"Available: {available or 'agent default only'}"
                        )
                    await conn.set_session_model(
                        session_id=session_id,
                        model_id=resolved_model,
                    )
                else:
                    model_option = _find_model_option(config_options)
                    if not model_option:
                        return None, (
                            f"ACP agent '{agent}' does not expose a model selector; "
                            f"cannot apply model '{model}'."
                        )
                    resolved_model = _resolve_model_value(model_option, model)
                    if not resolved_model:
                        return None, (
                            f"Model '{model}' is not available for ACP agent '{agent}'. "
                            f"Available: {_format_model_choices(model_option)}"
                        )
                    await conn.set_config_option(
                        session_id=session_id,
                        config_id=_get_field(model_option, 'optionId', 'option_id', 'id'),
                        value=resolved_model,
                    )

            result = await conn.prompt(
                session_id=session_id,
                prompt=[text_block(prompt)],
                message_id=str(uuid4()),
            )
            stop_reason = _get_field(result, 'stopReason', 'stop_reason', default='')
            text = client.collected_text()
            if stop_reason == 'cancelled':
                return None, 'prompt turn was cancelled'
            return text, None
    except Exception as exc:
        return None, str(exc)


# ── Step runners ─────────────────────────────────────────────

def run_llm(prompt, agent, model, extract=False):
    """Call coding agent over ACP. Returns (result, error)."""
    if extract:
        prompt += (
            '\n\nIMPORTANT: Respond with ONLY the raw result — '
            'no explanation, no markdown, no code fences. '
            'If you cannot complete this task, respond with '
            'exactly: ERROR: <brief reason>'
        )
    check_agent(agent)
    preview = (prompt[:100] + '...') if len(prompt) > 100 else prompt
    preview = preview.replace('\n', ' ')
    print(f'  > llm[{agent}]: {preview}')
    text, error = asyncio.run(_run_llm_async(prompt, agent, model))
    if error:
        print(f'  x Agent error: {error}')
        return None, error
    text = (text or '').strip()
    if extract and text.upper().startswith('ERROR:'):
        error = text.split(':', 1)[1].strip()
        print(f'  x LLM could not complete task: {error}')
        return None, error
    print(f'  ok ({len(text)} chars)')
    return text, None


def run_tool(command, label=None):
    """Run a shell command. Returns (stdout, error)."""
    display = label or (command[:80] + '...' if len(command) > 80 else command)
    print(f'  > tool: {display}')
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        error = result.stderr.strip() or f'exit code {result.returncode}'
        print(f'  x Tool failed: {error}')
        return None, error
    text = result.stdout.strip()
    print(f'  ok ({len(text)} chars)')
    return text, None


def wait_human(prompt='Your input'):
    """Pause for human input. Returns (response, error)."""
    print(f'\n  ?  {prompt}')
    response = input('  > ').strip()
    if not response:
        return None, 'empty input'
    return response, None


# ── Pipeline ─────────────────────────────────────────────────

def main(args):
    agent, model = resolve_agent(args)
    check_agent(agent)
    print('Pipeline: <name>')
    print(f'Default agent: {agent}' + (f' ({model})' if model else ''))
    print()

    # ... generated step code here ...


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pipeline: <name>')
    parser.add_argument(
        '--agent',
        choices=SUPPORTED_AGENTS,
        help='Default ACP agent for plain llm steps',
    )
    parser.add_argument(
        '--model',
        help='Default ACP model value for plain llm steps',
    )
    parser.add_argument(
        '--max-loops', type=int, default=10,
        help='Maximum iterations for any loop',
    )
    args = parser.parse_args()
    main(args)
