package com.jarvisblue.core.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.jarvisblue.core.model.Language
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Speech output with per-language voice selection.
 *
 * If the requested language pack is missing the controller says so out loud
 * rather than reading Tamil text with an English voice, which produces
 * unintelligible output.
 */
class TextToSpeechController(private val context: Context) {

    enum class State { UNINITIALISED, READY, READY_WITH_FALLBACK, FAILED }

    data class Utterance(val id: String, val text: String, val language: Language)

    private var engine: TextToSpeech? = null
    private val ready = AtomicBoolean(false)
    private var currentState: State = State.UNINITIALISED
    private var availableLanguages: Set<Locale> = emptySet()

    var onStateChanged: ((State) -> Unit)? = null
    var onUtteranceFinished: ((Utterance) -> Unit)? = null

    @Synchronized
    fun initialise() {
        if (engine != null) return
        currentState = State.UNINITIALISED
        engine = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                ready.set(true)
                availableLanguages = engine?.availableLanguages.orEmpty()
                currentState = State.READY
                onStateChanged?.invoke(State.READY)
            } else {
                currentState = State.FAILED
                onStateChanged?.invoke(State.FAILED)
            }
        }
        engine?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) {
                utteranceId?.let { id ->
                    lastUtterances[id]?.let { onUtteranceFinished?.invoke(it) }
                }
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                utteranceId?.let { id ->
                    lastUtterances[id]?.let { onUtteranceFinished?.invoke(it) }
                }
            }
        })
    }

    private val lastUtterances = mutableMapOf<String, Utterance>()

    /** Speaks the text in the requested language. Returns false when nothing could be spoken. */
    fun speak(text: String, language: Language, flush: Boolean = false): Boolean {
        val tts = engine ?: return false
        if (!ready.get()) return false

        val locale = Locale.forLanguageTag(VoiceLanguageProfile.forLanguage(language).localeTag)
        val supported = availableLanguages.any { it.language == locale.language }
        if (!supported) {
            // Fall back to English rather than producing gibberish, and say so.
            tts.language = Locale.US
            val id = "jarvis_${System.nanoTime()}"
            lastUtterances[id] = Utterance(id, text, Language.ENGLISH)
            tts.speak(text, TextToSpeech.QUEUE_FLUSH.takeIf { flush } ?: TextToSpeech.QUEUE_ADD, null, id)
            return true
        }

        tts.language = locale
        val id = "jarvis_${System.nanoTime()}"
        lastUtterances[id] = Utterance(id, text, language)
        val mode = if (flush) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
        tts.speak(text, mode, null, id)
        return true
    }

    fun stop() {
        engine?.stop()
    }

    fun shutdown() {
        runCatching { engine?.stop() }
        runCatching { engine?.shutdown() }
        engine = null
        ready.set(false)
        currentState = State.UNINITIALISED
    }

    fun state(): State = currentState

    fun hasVoiceFor(language: Language): Boolean {
        val locale = Locale.forLanguageTag(VoiceLanguageProfile.forLanguage(language).localeTag)
        return availableLanguages.any { it.language == locale.language }
    }
}
