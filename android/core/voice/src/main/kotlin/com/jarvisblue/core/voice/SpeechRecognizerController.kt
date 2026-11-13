package com.jarvisblue.core.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import com.jarvisblue.core.model.Language
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/**
 * Thin wrapper over the platform [SpeechRecognizer].
 *
 * On Android 12+ the app can ask for the *on-device* engine, which keeps audio
 * on the phone. When that engine is unavailable for the requested locale the
 * controller falls back to the normal recogniser and reports which engine was
 * used, so the UI never misrepresents where the audio went.
 */
class SpeechRecognizerController(private val context: Context) {

    enum class EngineMode {
        /** Prefer the offline recogniser; fall back to the network engine. */
        PREFER_ON_DEVICE,
        /** Wake word NEVER falls back to cloud recognition. */
        ON_DEVICE_ONLY,
        /** Use whatever the system picks. */
        SYSTEM_DEFAULT,
    }

    data class Recognition(
        val transcript: String,
        val confidence: Float,
        val isFinal: Boolean,
        val onDevice: Boolean,
        val error: String? = null,
    )

    /**
     * Emits recognition results until the flow is cancelled.
     * The recogniser is released when collection stops.
     */
    fun listen(
        language: Language,
        engineMode: EngineMode = EngineMode.PREFER_ON_DEVICE,
        partialResults: Boolean = true,
        maxResults: Int = 5,
    ): Flow<Recognition> = callbackFlow {
        val selected = createRecognizer(engineMode)
        if (selected == null) {
            trySend(Recognition("", 0f, true, false, error =
                "No Android speech recognition service is installed or enabled. " +
                "Open Voice settings and select a working speech recognizer."))
            close()
            return@callbackFlow
        }
        val (recognizer, onDevice) = selected

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, VoiceLanguageProfile.forLanguage(language).localeTag)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, partialResults)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, maxResults)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
        }

        val listener = object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
            override fun onError(error: Int) {
                trySend(Recognition("", 0f, true, onDevice, error = describeError(error)))
                close()
            }

            override fun onResults(results: Bundle?) {
                val transcript = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()
                    .orEmpty()
                val confidence = results?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)
                    ?.firstOrNull() ?: 0f
                trySend(Recognition(transcript, confidence, true, onDevice))
                close()
            }

            override fun onPartialResults(partialResults: Bundle?) {
                if (partialResults == null) return
                val transcript = partialResults
                    .getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()
                    .orEmpty()
                trySend(Recognition(transcript, 0f, false, onDevice))
            }
        }

        try {
            recognizer.setRecognitionListener(listener)
            recognizer.startListening(intent)
        } catch (exception: Exception) {
            trySend(Recognition("", 0f, true, onDevice, error =
                "Could not start Android speech recognition: ${exception.message ?: "service unavailable"}"))
            runCatching { recognizer.destroy() }
            close()
            return@callbackFlow
        }
        awaitClose {
            runCatching { recognizer.cancel() }
            runCatching { recognizer.destroy() }
        }
    }

    private data class SelectedRecognizer(val recognizer: SpeechRecognizer, val onDevice: Boolean)

    /** True if Android reports an on-device recognizer service. */
    fun supportsOnDevice(): Boolean = runCatching {
        SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
    }.getOrDefault(false)

    /** A normal recognizer can exist without a downloaded offline pack. */
    fun supportsRecognition(): Boolean = supportsOnDevice() || runCatching {
        SpeechRecognizer.isRecognitionAvailable(context)
    }.getOrDefault(false)

    private fun createRecognizer(engineMode: EngineMode): SelectedRecognizer? {
        if (engineMode != EngineMode.SYSTEM_DEFAULT && supportsOnDevice()) {
            runCatching { SpeechRecognizer.createOnDeviceSpeechRecognizer(context) }
                .getOrNull()?.let { return SelectedRecognizer(it, onDevice = true) }
        }
        if (engineMode == EngineMode.ON_DEVICE_ONLY) return null
        // System speech recognition may use a cloud provider; explicit push-to-talk only.
        if (runCatching { SpeechRecognizer.isRecognitionAvailable(context) }.getOrDefault(false)) {
            runCatching { SpeechRecognizer.createSpeechRecognizer(context) }
                .getOrNull()?.let { return SelectedRecognizer(it, onDevice = false) }
        }
        return null
    }

    private fun describeError(code: Int): String = when (code) {
        SpeechRecognizer.ERROR_AUDIO -> "Audio capture error"
        SpeechRecognizer.ERROR_CLIENT -> "Recognition client error"
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission is missing"
        SpeechRecognizer.ERROR_NETWORK -> "Network error while recognising speech"
        SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout while recognising speech"
        SpeechRecognizer.ERROR_NO_MATCH -> "No speech was recognised"
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "The recogniser is busy"
        SpeechRecognizer.ERROR_SERVER -> "The recognition server returned an error"
        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech was detected"
        else -> "Speech recognition error $code"
    }
}
