package com.jarvisblue.mobile.assistant

import android.speech.RecognitionService
import android.speech.SpeechRecognizer
import android.speech.RecognitionListener
import android.os.Bundle
import android.content.Intent
import android.content.ComponentName

/**
 * The system's [RecognitionService] entry point.
 *
 * Android routes "voice input" requests to whichever app provides this service.
 * JARVIS BLUE hands the work to the platform [SpeechRecognizer] so the audio
 * path, the privacy indicator and the on-device engine all stay under Android's
 * control — this service never captures audio itself.
 */
class JarvisRecognitionService : RecognitionService() {

    private var recognizer: SpeechRecognizer? = null
    private var activeCallback: Callback? = null

    override fun onStartListening(intent: Intent?, callback: Callback?) {
        val target = callback ?: return
        activeCallback = target

        // Do not proxy recognition to our own service; it causes recursion
        // when JARVIS BLUE is the system-selected recognition provider.
        val external = packageManager.queryIntentServices(
            Intent(RecognitionService.SERVICE_INTERFACE), 0,
        ).firstNotNullOfOrNull { info ->
            val service = info.serviceInfo
            if (service == null || service.packageName == packageName) null
            else ComponentName(service.packageName, service.name)
        }
        if (external == null) {
            runCatching { target.error(SpeechRecognizer.ERROR_CLIENT) }
            return
        }
        val instance = recognizer ?: SpeechRecognizer.createSpeechRecognizer(this, external).also { created ->
            recognizer = created
            created.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    runCatching { target.readyForSpeech(params ?: Bundle()) }
                }

                override fun onBeginningOfSpeech() = runCatching { target.beginningOfSpeech() }.let { }

                override fun onRmsChanged(rmsdB: Float) = runCatching { target.rmsChanged(rmsdB) }.let { }

                override fun onBufferReceived(buffer: ByteArray?) {
                    runCatching { target.bufferReceived(buffer ?: ByteArray(0)) }
                }

                override fun onEndOfSpeech() = runCatching { target.endOfSpeech() }.let { }

                override fun onError(error: Int) = runCatching { target.error(error) }.let { }

                override fun onResults(results: Bundle?) {
                    runCatching { target.results(results ?: Bundle()) }
                }

                override fun onPartialResults(partialResults: Bundle?) {
                    runCatching { target.partialResults(partialResults ?: Bundle()) }
                }

                override fun onEvent(eventType: Int, params: Bundle?) {
                    runCatching { target.languageDetection(params ?: Bundle()) }
                }
            })
        }

        val recognizerIntent = Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        runCatching { instance.startListening(recognizerIntent) }
    }

    override fun onCancel(callback: Callback?) {
        runCatching { recognizer?.cancel() }
        activeCallback = null
    }

    override fun onStopListening(callback: Callback?) {
        runCatching { recognizer?.stopListening() }
    }

    override fun onDestroy() {
        runCatching { recognizer?.destroy() }
        recognizer = null
        activeCallback = null
        super.onDestroy()
    }
}
