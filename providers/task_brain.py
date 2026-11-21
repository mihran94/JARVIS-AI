"""Route authorized chat requests using model catalogues and recent local outcomes."""
import re
from statistics import median

from providers import pricing

SPECIALISTS = ('OpenAI', 'MiniMax')
EFFORTS = ('Auto', 'Fast', 'Deep')
COMPLEX = re.compile(r'\b(debug|reason|trade-?offs?|architect(?:ure)?|analyse[rz]?|analy[sz]e|multi.?step|compare|diagnostiquer|comparer|oppidu)\b|ஒப்பிடு|ஆராய்|படிப்படியாக', re.I)
NON_CHAT = re.compile(r'embed|image|audio|tts|realtime|transcri|moderation|vision-only|computer-use|deep-research|robotics|music|video|instruct-preview|code-interpreter', re.I)


def effort_for(text, setting='Auto', analysis=False):
    if setting in ('Fast', 'Deep'):
        return setting.lower()
    return 'deep' if analysis or len(text) > 1800 or COMPLEX.search(text) else 'fast'


def catalogued_model(provider, wanted, catalogue, effort, *, custom=False):
    if not catalogue or wanted in catalogue:
        return wanted
    if custom:
        return None
    prefixes = {'Gemini': ('gemini-',), 'OpenAI': ('gpt-', 'o3', 'o4'), 'MiniMax': ('minimax-m',)}
    allowed = [m for m in catalogue if m.casefold().startswith(prefixes.get(provider, ()))
               and not NON_CHAT.search(m)]
    if not allowed:
        return None
    def rank(model):
        fast = bool(re.search(r'flash|mini|nano|lite|luna', model, re.I))
        experimental = bool(re.search(r'preview|experimental|\bexp\b', model, re.I))
        # Keep unknown prices distinct from zero.
        estimate = pricing.estimate(provider, model, 1000, 1000)
        return (experimental, fast != (effort == 'fast'),
                estimate if estimate is not None else float('inf'), model)
    return min(allowed, key=rank)


def select_route(preferred, effort, *, available, model_for, history):
    candidates = (preferred,) if preferred not in ('Gemini', *SPECIALISTS) else tuple(dict.fromkeys(
        (*SPECIALISTS, preferred, 'Gemini') if effort == 'deep' else (preferred, 'Gemini', *SPECIALISTS)))
    ranked = []
    for priority, provider in enumerate(candidates):
        if not available(provider):
            continue
        model = model_for(provider, effort)
        if not model:
            continue
        recent = [r for r in history if r['provider'] == provider and r['model'] == model
                  and r['status'] in ('completed', 'failed')][:8]
        degraded = len(recent) >= 2 and all(r['status'] == 'failed' for r in recent[:2])
        latency = [r['duration_ms'] for r in recent if r['status'] == 'completed' and r['duration_ms']]
        tier = int(provider not in SPECIALISTS) if effort == 'deep' else int(provider != preferred)
        cost = pricing.estimate(provider, model, 1000, 1000)
        ranked.append(((degraded, tier, -sum(r['status'] == 'completed' for r in recent) / max(1, len(recent)),
                        median(latency) if latency else float('inf'),
                        cost if cost is not None else float('inf'), priority), provider, model))
    if not ranked:
        raise ValueError('No configured model is available for this request. Check your provider settings.')
    _, provider, model = min(ranked)
    return provider, model
