"""Safe local-first core for JARVIS Blue November Early Access."""
import json
import urllib.request
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderStatus:
    name: str
    configured: bool
    details: str

def provider_statuses(env):
    return [
        ProviderStatus('Ollama', True, 'Local endpoint; availability checked on demand'),
        ProviderStatus('OpenAI', bool(env.get('OPENAI_API_KEY')), 'API key configured' if env.get('OPENAI_API_KEY') else 'API key not configured'),
        ProviderStatus('Gemini', bool(env.get('GEMINI_API_KEY')), 'API key configured' if env.get('GEMINI_API_KEY') else 'API key not configured'),
        ProviderStatus('MiniMax', bool(env.get('MINIMAX_API_KEY')), 'API key configured' if env.get('MINIMAX_API_KEY') else 'API key not configured'),
    ]

def ollama_chat(prompt, model='llama3.2', endpoint='http://127.0.0.1:11434', timeout=30):
    """Only loopback Ollama; no arbitrary URL or external network access."""
    if endpoint not in ('http://127.0.0.1:11434', 'http://localhost:11434'):
        raise ValueError('Only the default loopback Ollama endpoint is allowed')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
        raise ValueError('Prompt must contain 1–8000 characters')
    if not isinstance(model, str) or not model or len(model) > 80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-' for c in model):
        raise ValueError('Invalid model identifier')
    payload = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False}).encode('utf-8')
    request = urllib.request.Request(endpoint + '/api/chat', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('Ollama response too large')
    data = json.loads(body)
    answer = data.get('message', {}).get('content')
    if not isinstance(answer, str):
        raise ValueError('Invalid Ollama response')
    return answer

def require_owner_approval(action, approved):
    """UI-only decision helper, never executes commands or edits files."""
    if action not in ('open_file', 'edit_file', 'run_code', 'windows_automation'):
        raise ValueError('Unknown action')
    return approved is True

def ollama_health(endpoint='http://127.0.0.1:11434', timeout=2):
    """Explicit, on-demand local health probe; no background polling."""
    if endpoint not in ('http://127.0.0.1:11434', 'http://localhost:11434'):
        raise ValueError('Only loopback Ollama endpoint allowed')
    try:
        with urllib.request.urlopen(endpoint + '/api/tags', timeout=timeout) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                return False
            data = json.loads(raw)
            return isinstance(data.get('models'), list)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
