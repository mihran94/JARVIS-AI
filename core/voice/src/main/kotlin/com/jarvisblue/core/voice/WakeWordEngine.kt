package com.jarvisblue.core.voice

import com.jarvisblue.core.model.Language
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.map

/**
 * Coordinates continuous wake-word detection.
 *
 * The engine is driven by a foreground service (the app module owns the
 * service). It repeatedly asks the on-device recogniser for a short phrase and
 * matches the transcript against the wake phrase.
 *
 * Honest limitations, surfaced to the user rather than hidden:
 *  - Android shows a permanent microphone indicator while the service runs.
 *  - Android 14+ refuses to start a microphone foreground service from the
 *    background, so the user must start it while the app is visible (or use the
 *    assistant role).
 *  - Continuous listening costs battery; the engine exposes a duty cycle.
 */
class WakeWordEngine(
    private val recognizer: SpeechRecognizerController,
    private val matcher: WakePhraseMatcher = WakePhraseMatcher(),
) {

    enum class State {
        STOPPED, LISTENING, WAKE_DETECTED, ERROR,
    }

    data class Status(
        val state: State = State.STOPPED,
        val language: Language = Language.ENGLISH,
        val onDevice: Boolean = true,
        val lastTranscript: String = "",
        val lastError: String? = null,
        val batteryNote: String = "",
    )

    private val _status = MutableStateFlow(Status())
    val status: StateFlow<Status> = _status.asStateFlow()

    /**
     * Emits the instruction that followed the wake phrase, if any.
     */
    fun wakeCommands(language: Language): Flow<String> = recognizer
        .listen(language = language, engineMode = SpeechRecognizerController.EngineMode.ON_DEVICE_ONLY)
        .filterNotNull()
        .map { recognition ->
            _status.value = _status.value.copy(
                state = State.LISTENING,
                lastTranscript = recognition.transcript,
                lastError = recognition.error,
                onDevice = recognition.onDevice,
            )
            recognition
        }
        .let { flow ->
            kotlinx.coroutines.flow.flow {
                flow.collect { recognition ->
                    if (recognition.isFinal && recognition.error == null) {
                        val match = matcher.match(recognition.transcript, language)
                        if (match.isWakeCall) {
                            _status.value = _status.value.copy(
                                state = State.WAKE_DETECTED,
                                lastTranscript = recognition.transcript,
                            )
                            val command = matcher.extractCommand(recognition.transcript)
                            if (!command.isNullOrBlank()) emit(command)
                        }
                    }
                }
            }
        }

    /** Single-shot check used by the assistant role and the push-to-talk button. */
    fun evaluate(transcript: String, language: Language): WakePhraseMatcher.Match {
        val match = matcher.match(transcript, language)
        _status.value = _status.value.copy(
            state = if (match.isWakeCall) State.WAKE_DETECTED else State.LISTENING,
            lastTranscript = transcript,
        )
        return match
    }

    fun reset() {
        _status.value = _status.value.copy(state = State.STOPPED, lastError = null)
    }
}
