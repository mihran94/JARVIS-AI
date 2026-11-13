package com.jarvisblue.feature.assistant

import androidx.lifecycle.ViewModel
import com.jarvisblue.core.ai.AiMessage
import com.jarvisblue.core.ai.AiRequest
import com.jarvisblue.core.ai.AiRouter
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.tools.ConfirmationCoordinator
import com.jarvisblue.core.tools.ToolExecutor
import com.jarvisblue.core.tools.ToolRegistry
import com.jarvisblue.core.voice.SpeechRecognizerController
import com.jarvisblue.core.voice.TextToSpeechController
import com.jarvisblue.core.voice.WakePhraseMatcher
import com.jarvisblue.core.voice.WakeWordEngine
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import javax.inject.Inject

data class AssistantUiState(
    val language: Language = Language.ENGLISH,
    val isListening: Boolean = false,
    val isSpeaking: Boolean = false,
    val wakeWordEnabled: Boolean = false,
    val wakePhrase: String = WakePhraseMatcher.DEFAULT_PHRASE,
    val transcript: String = "",
    val response: String = "",
    val amplitudes: List<Float> = emptyList(),
    val onDeviceRecognition: Boolean = false,
    val onDeviceAvailable: Boolean = false,
    val recognitionAvailable: Boolean = false,
    val ttsAvailableFor: Set<Language> = emptySet(),
    val statusLine: String = "Idle",
    val error: String? = null,
    val registeredTools: List<String> = emptyList(),
    val pendingConfirmation: com.jarvisblue.core.tools.ConfirmationRequest? = null,
)

@HiltViewModel
class AssistantViewModel @Inject constructor(
    private val recognizer: SpeechRecognizerController,
    private val aiRouter: AiRouter,
    private val tts: TextToSpeechController,
    private val wakeWordEngine: WakeWordEngine,
    private val toolRegistry: ToolRegistry,
    private val toolExecutor: ToolExecutor,
    private val confirmationCoordinator: ConfirmationCoordinator,
) : ViewModel() {

    private var listeningJob: Job? = null
    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    init {
        _state.value = _state.value.copy(
            onDeviceAvailable = recognizer.supportsOnDevice(),
            recognitionAvailable = recognizer.supportsRecognition(),
            registeredTools = toolRegistry.specs().map { it.name },
        )
        // TTS loads voices asynchronously: do not show "no voice pack" too early.
        tts.onStateChanged = { newState ->
            viewModelScope.launch {
                if (newState == TextToSpeechController.State.READY ||
                    newState == TextToSpeechController.State.READY_WITH_FALLBACK) {
                    _state.value = _state.value.copy(
                        ttsAvailableFor = Language.entries.filter { tts.hasVoiceFor(it) }.toSet(),
                    )
                }
            }
        }
        tts.onUtteranceFinished = {
            viewModelScope.launch {
                _state.value = _state.value.copy(isSpeaking = false, statusLine = "Ready")
            }
        }
        viewModelScope.launch {
            try { tts.initialise() }
            catch (exception: Exception) {
                _state.value = _state.value.copy(error = "Speech output could not initialise on this device")
            }
        }
        viewModelScope.launch {
            confirmationCoordinator.pending.collect { pending ->
                _state.value = _state.value.copy(pendingConfirmation = pending?.request)
            }
        }
    }

    fun setLanguage(language: Language) {
        _state.value = _state.value.copy(language = language)
    }

    /** Push-to-talk: recognize once, then answer using the configured AI. */
    fun startListening() {
        if (_state.value.isListening) return
        _state.value = _state.value.copy(
            isListening = true, transcript = "", error = null, statusLine = "Listening…", response = "",
        )
        listeningJob = viewModelScope.launch {
            try {
                // The Android system recognizer may use a third-party cloud service.
                recognizer.listen(
                    _state.value.language,
                    engineMode = SpeechRecognizerController.EngineMode.SYSTEM_DEFAULT,
                ).collect { recognition ->
                    if (recognition.error != null) {
                        _state.value = _state.value.copy(
                            isListening = false, statusLine = "Idle", error = recognition.error,
                        )
                        return@collect
                    }
                    _state.value = _state.value.copy(
                        transcript = recognition.transcript,
                        onDeviceRecognition = recognition.onDevice,
                        amplitudes = (recognition.transcript.length.coerceAtMost(48)).let { count ->
                            List(count) { index -> ((index * 37 % 17) / 17f).coerceIn(0.15f, 1f) }
                        },
                    )
                    if (recognition.isFinal && recognition.transcript.isNotBlank()) {
                        _state.value = _state.value.copy(isListening = false, statusLine = "Thinking…")
                        answerSpokenQuestion(recognition.transcript, _state.value.language)
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (exception: Exception) {
                _state.value = _state.value.copy(
                    error = exception.message ?: "Voice request failed",
                    statusLine = "Idle", isListening = false,
                )
            } finally {
                if (_state.value.isListening) _state.value = _state.value.copy(isListening = false)
            }
        }
    }

    /** Stop must cancel the recognizer collection and release the microphone. */
    fun stopListening() {
        listeningJob?.cancel()
        listeningJob = null
        _state.value = _state.value.copy(isListening = false, statusLine = "Idle")
    }

    private suspend fun answerSpokenQuestion(transcript: String, language: Language) {
        // Voice replies are text-only; device tools are never run from noisy speech.
        try {
            val answer = aiRouter.route(AiRequest(
                messages = listOf(
                    AiMessage(role = "system", content =
                        "You are JARVIS BLUE, a helpful voice assistant. " +
                        "Answer briefly in ${language.displayName}. " +
                        "No tools or device actions are available; never claim to execute any."),
                    AiMessage(role = "user", content = transcript),
                ),
                responseLanguage = language,
                enableTools = false,
            ))
            val text = answer.content.trim()
            _state.value = _state.value.copy(
                response = text.ifEmpty { "No response was returned by the AI provider." },
                statusLine = "Ready", error = null,
            )
            if (text.isNotEmpty() && tts.hasVoiceFor(language)) speak(text)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (exception: Exception) {
            _state.value = _state.value.copy(
                error = exception.message ?: "AI provider unavailable",
                statusLine = "Idle", isListening = false,
            )
        }
    }

    /** Speaks a response with the device TTS. */
    fun speak(text: String) {
        if (text.isBlank()) return
        _state.value = _state.value.copy(isSpeaking = true, statusLine = "Speaking…", response = text)
        val ok = tts.speak(text, _state.value.language)
        if (!ok) {
            _state.value = _state.value.copy(
                isSpeaking = false,
                statusLine = "Idle",
                error = "Speech output is not available on this device",
            )
        }
    }

    fun setWakeWordEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(
            wakeWordEnabled = enabled,
            statusLine = if (enabled) "Wake word armed" else "Wake word off",
        )
    }

    fun respondToConfirmation(approved: Boolean) {
        confirmationCoordinator.submit(approved)
        _state.value = _state.value.copy(pendingConfirmation = null)
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }

    override fun onCleared() {
        listeningJob?.cancel()
        super.onCleared()
        tts.shutdown()
    }
}
