"""Read-only capability reporting from actual JARVIS runtime state.

Nothing here loads plugins, opens devices, grants permission, or sends network
requests. Enabled plugins are a preference, not proof of installation.
"""
from __future__ import annotations


def snapshot(window):
    from video_studio.planning import VIDEO_TOOLS
    from automation.windows import EDITOR_EXECUTABLES
    provider = window.chat_provider.currentText()
    local = bool(window.router.spec(provider).local)
    plugins = tuple(dict.fromkeys((*VIDEO_TOOLS, *EDITOR_EXECUTABLES)))
    return {
        'provider': provider,
        'local': local,
        'microphone': bool(window.voice_panel.consent.listening),
        'phone_bridge': bool(window.bridge.listener.running),
        'stopped': bool(window.policy.stopped),
        'plugins': [name for name in plugins if window.plugin_enabled(name)],
    }


def summary(window):
    state = snapshot(window)
    plugins = ', '.join(state['plugins']) or 'none enabled'
    return (
        f'Current AI: {state["provider"]} ({"local" if state["local"] else "hosted"}). '
        'Model connectivity has not been verified here.\n'
        f'Microphone permission: {"granted" if state["microphone"] else "not granted"}. '
        'Hands-free needs explicit consent and local Ollama.\n'
        f'PC control: restricted approved actions; '
        f'{"Emergency Stop active" if state["stopped"] else "owner approval required"}.\n'
        'Conversation plans: up to six supported app launches with per-step approval, '
        'optionally ending in Notepad typing; /cancel stops remaining steps.\n'
        'Coding: project-aware change reviews using configured Codex/MiniMax.\n'
        f'Android remote bridge: {"listening" if state["phone_bridge"] else "off"}; '
        'real hardware pairing still needs verification.\n'
        'Other JARVIS services: local memory, video planning, business drafts, '
        'system readings and plugin switches.\n'
        f'Enabled plugin switches: {plugins}. Enabled is not the same as installed.\n'
        'Not yet verified: human avatar lip-sync, Whisper/Piper voice engines, '
        'voice interruption, unrestricted desktop automation or signed installer.'
    )


def conversation_context(window):
    """What this conversation is about, so the assistant knows its own context.

    The task card shows the owner what happened; this tells the *model* the
    same thing, so a plain question like "which project were we on?" or
    "what did you just change?" can be answered from the conversation's
    memory instead of being a guess.
    """
    memory = getattr(window, 'memory', None)
    if memory is None:
        return ''
    try:
        context = memory.load()
    except Exception:
        return ''
    parts = []
    if context.project:
        parts.append(f'This conversation is about the saved project {context.project}.')
    task = context.last_task
    if task is not None:
        sentence = f'The last task was on {task.project}'
        if task.change:
            sentence += f', asking for {task.change}'
        if task.status:
            sentence += f', and it ended {task.status}'
        parts.append(sentence + '.')
        if task.worktree:
            parts.append(f'Its worktree is {task.worktree}.')
        if task.starting_commit:
            parts.append(f'It started from revision {task.starting_commit[:12]}.')
    if not parts:
        return ''
    return ' '.join(parts)


def system_context(window):
    state = snapshot(window)
    return (
        f'Runtime: selected provider {state["provider"]}; '
        f'microphone permission {"granted" if state["microphone"] else "not granted"}; '
        f'Android bridge {"on" if state["phone_bridge"] else "off"}; '
        f'Emergency Stop {"active" if state["stopped"] else "inactive"}. '
        'There are separate owner-approved workflows for PC automation, '
        'coding and creative tools, but plain chat has no tool execution. '
        'Do not claim an action completed unless the app reports verified evidence.'
    )
