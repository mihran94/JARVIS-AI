"""Which engine answers one step of a JARVIS mission.

WHAT THIS IS
    JARVIS is local first. The on-device model answers a step whenever it
    can, and nothing leaves the machine unless the owner asked for it.

    The owner can turn on "Use Gemini automatically when needed". When that
    is on, the step the local model cannot complete is sent to Gemini, and
    only that step: the context is cut down to what the step needs, and the
    reason is recorded, so the interface can say which engine answered and
    why it was used.

THE RULES
    * Routine work stays local. Only a planning step may be handed to
      Gemini, and only after the local model actually failed that step.
    * Nothing sensitive leaves the machine without the owner's approval.
      Protected files, screen content and microphone audio are named before
      they are shared, and the owner is asked through the same approval
      gateway as every other action.
    * A Gemini failure is not a JARVIS failure. The step that needed it is
      reported as blocked, and the mission carries on with the parts the
      local model can do.

WHAT THIS IS NOT
    * It is not a chat router. The conversation in the chat window keeps the
      provider the owner chose there; this is about the steps of a mission.
    * It never retries a cloud model silently, and it never sends a prompt
      the owner did not agree to send.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: The name of the engine that runs on this computer.
LOCAL = 'Local'

#: The name of the cloud engine that may be used for one step.
GEMINI = 'Gemini'

#: The engines, in the order the interface shows them.
ENGINE_NAMES = (LOCAL, GEMINI)

#: Why a step was handed to Gemini. These are codes, not sentences: the
#: sentence the owner reads lives in `REASON_WORDS`.
REASON_LOCAL_UNAVAILABLE = 'local_model_unavailable'
REASON_LOCAL_UNUSABLE = 'local_model_could_not_complete_the_step'
REASON_LOCAL_CAPABILITY = 'capability_unavailable_locally'

#: The sentence the interface shows for each reason.
REASON_WORDS = {
    REASON_LOCAL_UNAVAILABLE:
        'The on-device model could not be reached, so Gemini answered this step.',
    REASON_LOCAL_UNUSABLE:
        'The on-device model could not complete this step, so Gemini answered it.',
    REASON_LOCAL_CAPABILITY:
        'This step needs a capability the on-device model does not have, '
        'so Gemini answered it.',
}

#: The kinds of content that need the owner's approval before they are
#: shared with a cloud model.
SHARED_FILE = 'a protected file'
SHARED_SCREEN = 'the content of the screen'
SHARED_MICROPHONE = 'the microphone'

#: The key the owner's choice is remembered under.
FALLBACK_KEY = 'engines:gemini_fallback'

#: The key the last engine records are remembered under.
HISTORY_KEY = 'engines:history'

#: How many engine records are kept.
MAX_HISTORY = 50


class EngineUnavailable(RuntimeError):
    """The engine for this step could not be used.

    The message says which part of the work is blocked and why, in words
    the owner can read, because the owner is told this directly.

    `blocked` says whether the mission can carry on with the steps the
    local model can do. It is False when the local model itself could
    not be reached, because then nothing can be planned.
    """

    def __init__(self, message: str, *, reason: str = '', blocked: bool = False):
        super().__init__(message)
        self.reason = reason
        self.blocked = bool(blocked)


@dataclass(frozen=True)
class EngineStep:
    """What answered one step, and why."""

    engine: str
    reason: str = ''
    detail: str = ''
    step: int = 0
    shared: tuple = ()

    @property
    def used_gemini(self) -> bool:
        """True when this step was answered by Gemini."""
        return self.engine == GEMINI

    @property
    def explanation(self) -> str:
        """The sentence the interface shows for this step."""
        if not self.used_gemini:
            return 'Answered on this computer.'
        return REASON_WORDS.get(self.reason, self.detail or self.reason)

    def as_dict(self) -> dict:
        return {'engine': self.engine, 'reason': self.reason, 'detail': self.detail,
                'step': self.step, 'shared': list(self.shared)}


def step_context(messages, keep: int = 2) -> list:
    """The smallest context a step needs.

    A mission's conversation grows: the goal, then an answer and an
    observation for every tool that ran. Only the recent observations
    matter for the next decision, and the goal always matters. So the
    system instructions and the goal are always kept, and the last
    `keep` answer/observation pairs are kept with them.

    Everything else is dropped, so a step that goes to the cloud carries
    only what that step needs.
    """
    if not isinstance(messages, list):
        return []
    system = [m for m in messages[:1] if isinstance(m, dict) and m.get('role') == 'system']
    rest = [m for m in messages if isinstance(m, dict) and m.get('role') != 'system']
    goal = rest[:1]
    tail = rest[1:]
    keep = max(0, int(keep))
    recent = tail[-2 * keep:] if keep else []
    return system + goal + recent


def classify_context(messages, *, voice: bool = False,
                     protected_paths=()) -> tuple:
    """What sensitive content the step context carries.

    The answer decides whether the owner is asked before the context is
    shared with a cloud model. Nothing is inspected for secrets here: the
    question is only which kinds of content are present.
    """
    kinds = []
    if not isinstance(messages, list):
        return ()
    text = '\n'.join(str(m.get('content', '')) for m in messages if isinstance(m, dict))
    if 'observe_screen' in text:
        kinds.append(SHARED_SCREEN)
    if voice:
        kinds.append(SHARED_MICROPHONE)
    for path in protected_paths or ():
        if path and str(path) in text:
            kinds.append(SHARED_FILE)
            break
    return tuple(kinds)


def shared_note(kinds) -> str:
    """One line naming what would be shared, for the approval question."""
    if not kinds:
        return ''
    if len(kinds) == 1:
        return kinds[0]
    return ', '.join(kinds[:-1]) + ' and ' + kinds[-1]


class EngineRouter:
    """Chooses the engine for one step, and records what it chose.

    The router holds no key of its own. The local model and Gemini are
    both reached through callables, so the window keeps the key in the
    vault for the length of one step and clears it afterwards.
    """

    def __init__(self, *, local_model: str = '', local_stream=None,
                 gemini_model: str = '', gemini_key: str = '',
                 gemini_enabled: bool = False, gemini_stream=None,
                 validate=None, approve_share=None, on_record=None,
                 check=None, protected_paths=()):
        self.local_model = local_model
        self.local_stream = local_stream
        self.gemini_model = gemini_model
        self.gemini_key = gemini_key
        self.gemini_enabled = bool(gemini_enabled)
        self.gemini_stream = gemini_stream
        self.validate = validate
        self.approve_share = approve_share
        self.on_record = on_record
        self.check = check or (lambda: None)
        self.protected_paths = tuple(protected_paths)
        #: The records of the steps that ran, newest last.
        self.history: list = []

    # ------------------------------------------------------------------

    @property
    def gemini_configured(self) -> bool:
        """True when Gemini has everything it needs to answer a step."""
        return bool(self.gemini_model and self.gemini_key and self.gemini_stream)

    def set_gemini(self, *, model: str = '', key: str = '', enabled=None):
        """Point the router at the owner's Gemini configuration."""
        self.gemini_model = model or self.gemini_model
        self.gemini_key = key or self.gemini_key
        if enabled is not None:
            self.gemini_enabled = bool(enabled)

    def enable(self, enabled: bool):
        """Turn the automatic Gemini fallback on or off."""
        self.gemini_enabled = bool(enabled)

    # ------------------------------------------------------------------

    def _record(self, record: EngineStep) -> EngineStep:
        self.history.append(record)
        if len(self.history) > MAX_HISTORY:
            del self.history[:-MAX_HISTORY]
        if self.on_record is not None:
            self.on_record(record)
        return record

    def _local(self, messages):
        """Ask the on-device model for one answer."""
        if self.local_stream is None or not self.local_model:
            raise EngineUnavailable(
                'No on-device model is configured, so this step has no local answer.',
                reason=REASON_LOCAL_UNAVAILABLE)
        try:
            return self.local_stream(self.local_model, messages, self.check,
                                     lambda _chunk: None)
        except EngineUnavailable:
            raise
        except Exception as error:
            raise EngineUnavailable(
                'The on-device model could not answer: ' + str(error),
                reason=REASON_LOCAL_UNAVAILABLE) from None

    def _gemini(self, messages, reason: str, step: int, shared=()):
        """Ask Gemini for one step, and only what that step needs."""
        if not self.gemini_configured:
            raise EngineUnavailable(
                'Gemini is not available: no Gemini model or key is configured. '
                'The rest of this work stays on this computer.',
                reason=reason, blocked=True)
        kinds = classify_context(messages, voice=False,
                                 protected_paths=self.protected_paths)
        if kinds and self.approve_share is not None:
            note = shared_note(kinds)
            if not self.approve_share(kinds, note):
                raise EngineUnavailable(
                    'Sharing ' + note + ' with Gemini was not allowed, so this step '
                    'is blocked and the rest stays on this computer.',
                    reason=reason, blocked=True)
            shared = tuple(kinds)
        context = step_context(messages)
        try:
            text = self.gemini_stream(self.gemini_model, self.gemini_key, context,
                                      self.check, lambda _chunk: None)
        except EngineUnavailable:
            raise
        except Exception as error:
            raise EngineUnavailable(
                'Gemini could not answer this step: ' + str(error),
                reason=reason, blocked=True) from None
        return text, EngineStep(GEMINI, reason=reason,
                                detail=REASON_WORDS.get(reason, ''),
                                step=step, shared=shared)

    # ------------------------------------------------------------------

    def plan_step(self, messages, *, step: int = 0, voice: bool = False):
        """Answer one step, and say which engine answered it.

        Returns the answer and an `EngineStep`. Raises
        `EngineUnavailable` when no engine could answer the step.

        The exception carries `blocked`: True when the mission can carry
        on with the steps the local model can do, and False when it
        cannot, because the local model itself could not be reached.
        """
        local_failure = None
        try:
            text = self._local(messages)
        except EngineUnavailable as error:
            local_failure = error
            text = None

        if text is not None:
            if not (self.gemini_enabled and self.validate is not None
                    and not self.validate(text)):
                # The on-device model answered with something usable, or
                # the owner did not allow the automatic fallback. Either
                # way this step stays on this computer.
                return text, self._record(EngineStep(LOCAL, step=step))
            # The on-device model answered, but the answer cannot be used
            # as a decision. This is the "complex planning step" case.
            reason = REASON_LOCAL_UNUSABLE
            unusable = True
        else:
            reason = getattr(local_failure, 'reason', REASON_LOCAL_UNAVAILABLE)
            unusable = False

        if not self.gemini_enabled:
            raise EngineUnavailable(
                'The on-device model could not answer this step.',
                reason=reason, blocked=False)

        try:
            answer, record = self._gemini(messages, reason, step)
        except EngineUnavailable as error:
            raise EngineUnavailable(str(error), reason=reason,
                                    blocked=unusable) from None
        return answer, self._record(record)

    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """What the interface shows about the engines."""
        return {
            'local_model': self.local_model,
            'local_ready': bool(self.local_model and self.local_stream),
            'gemini_enabled': self.gemini_enabled,
            'gemini_ready': self.gemini_configured,
            'gemini_model': self.gemini_model,
        }


def enabled_from_store(store) -> bool:
    """Whether the owner turned the automatic Gemini fallback on."""
    return bool(store.get(FALLBACK_KEY, False))


def set_enabled_in_store(store, enabled: bool) -> bool:
    """Remember the owner's choice."""
    store.set(FALLBACK_KEY, bool(enabled))
    return bool(enabled)


def history_from_store(store) -> list:
    """The engine records of the steps that ran, newest last."""
    saved = store.get(HISTORY_KEY, [])
    return list(saved) if isinstance(saved, list) else []


def save_history_to_store(store, records) -> None:
    """Remember the engine records, so they survive a restart."""
    rows = []
    for record in records or ():
        if isinstance(record, EngineStep):
            rows.append(record.as_dict())
        elif isinstance(record, dict):
            rows.append(record)
    store.set(HISTORY_KEY, rows[-MAX_HISTORY:])


__all__ = ['ENGINE_NAMES', 'EngineRouter', 'EngineStep', 'EngineUnavailable',
           'FALLBACK_KEY', 'GEMINI', 'HISTORY_KEY', 'LOCAL', 'MAX_HISTORY',
           'REASON_LOCAL_CAPABILITY', 'REASON_LOCAL_UNAVAILABLE',
           'REASON_LOCAL_UNUSABLE', 'REASON_WORDS', 'SHARED_FILE', 'SHARED_MICROPHONE',
           'SHARED_SCREEN', 'classify_context', 'enabled_from_store', 'history_from_store',
           'save_history_to_store', 'set_enabled_in_store', 'shared_note', 'step_context']
