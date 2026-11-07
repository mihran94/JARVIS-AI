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
        val recognizer = createRecognizer(engineMode)
        if (recognizer == null) {
            trySend(Recognition("", 0f, true, false, error = "Speech recognition is not available on this device"))
            close()
            return@callbackFlow
        }

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

        recognizer.setRecognitionListener(listener)
        recognizer.startListening(intent)
        awaitClose {
            runCatching { recognizer.stopListening() }
            runCatching { recognizer.destroy() }
        }
    }

    private val onDevice: Boolean by lazy {
        runCatching {
            SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
            true
        }.getOrDefault(false)
    }

    private fun createRecognizer(engineMode: EngineMode): SpeechRecognizer? = runCatching {
        if (engineMode == EngineMode.PREFER_ON_DEVICE) {
            SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
        } else {
            SpeechRecognizer.createSpeechRecognizer(context)
        }
    }.getOrNull()

    /** True when the platform exposes an offline recogniser at all. */
    fun supportsOnDevice(): Boolean = runCatching {
        SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
    }.getOrDefault(false)

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
