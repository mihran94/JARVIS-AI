package com.jarvisblue.feature.assistant

import androidx.lifecycle.ViewModel
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
    val ttsAvailableFor: Set<Language> = emptySet(),
    val statusLine: String = "Idle",
    val error: String? = null,
    val registeredTools: List<String> = emptyList(),
    val pendingConfirmation: com.jarvisblue.core.tools.ConfirmationRequest? = null,
)

@HiltViewModel
class AssistantViewModel @Inject constructor(
    private val recognizer: SpeechRecognizerController,
    private val tts: TextToSpeechController,
    private val wakeWordEngine: WakeWordEngine,
    private val toolRegistry: ToolRegistry,
    private val toolExecutor: ToolExecutor,
    private val confirmationCoordinator: ConfirmationCoordinator,
) : ViewModel() {

    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    init {
        _state.value = _state.value.copy(
            onDeviceRecognition = recognizer.supportsOnDevice(),
            registeredTools = toolRegistry.specs().map { it.name },
        )
        viewModelScope.launch {
            tts.initialise()
            _state.value = _state.value.copy(
                ttsAvailableFor = Language.entries.filter { tts.hasVoiceFor(it) }.toSet(),
            )
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

    /** Push-to-talk: listen once and run what was heard. */
    fun startListening() {
        if (_state.value.isListening) return
        _state.value = _state.value.copy(isListening = true, transcript = "", error = null, statusLine = "Listening…")
        viewModelScope.launch {
            recognizer.listen(_state.value.language).collect { recognition ->
                if (recognition.error != null) {
                    _state.value = _state.value.copy(
                        isListening = false,
                        statusLine = "Idle",
                        error = recognition.error,
                    )
                    return@collect
                }
                _state.value = _state.value.copy(
                    transcript = recognition.transcript,
                    amplitudes = (recognition.transcript.length.coerceAtMost(48)).let { count ->
                        List(count) { index -> ((index * 37 % 17) / 17f).coerceIn(0.15f, 1f) }
                    },
                    onDeviceRecognition = recognition.onDevice,
                )
                if (recognition.isFinal) {
                    _state.value = _state.value.copy(isListening = false, statusLine = "Processing…")
                }
            }
        }
    }

    fun stopListening() {
        _state.value = _state.value.copy(isListening = false, statusLine = "Idle")
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
        super.onCleared()
        tts.shutdown()
    }
}
