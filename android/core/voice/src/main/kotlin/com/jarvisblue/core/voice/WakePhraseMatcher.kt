package com.jarvisblue.core.voice

import com.jarvisblue.core.common.TextTools
import com.jarvisblue.core.model.Language

/**
 * Matches the wake phrase inside a speech-recognition transcript.
 *
 * On Android there is no supported way for a third-party app to run a true
 * always-on acoustic hotword model without becoming the default assistant.
 * JARVIS BLUE therefore matches the *transcript* of the on-device recogniser
 * against a set of accepted phrasings. This is honest, robust against ASR
 * noise, and — unlike an acoustic hotword SDK — it does not require shipping a
 * proprietary model or bypassing the microphone privacy indicator.
 */
class WakePhraseMatcher(
    private val canonicalPhrase: String = DEFAULT_PHRASE,
) {

    data class Match(
        val matched: Boolean,
        val confidence: Double,
        val matchedPhrase: String? = null,
        val language: Language? = null,
    ) {
        val isWakeCall: Boolean get() = matched && confidence >= ACCEPTANCE_THRESHOLD
    }

    /** Accepted spellings, grouped by the language they belong to. */
    private val variants: Map<Language, List<String>> = mapOf(
        Language.ENGLISH to listOf(
            "hey jarvis blue",
            "hey jarvis",
            "jarvis blue",
            "jarvis",
            "hey jarvis bleu",
        ),
        Language.TAMIL to listOf(
            "ஹே ஜார்விஸ் புளூ",
            "ஹே ஜார்விஸ்",
            "ஜார்விஸ் புளூ",
            "ஜார்விஸ்",
            "hey jarvis blue",
        ),
        Language.FRENCH to listOf(
            "salut jarvis",
            "hey jarvis blue",
            "jarvis bleu",
            "jarvis",
        ),
    )

    /**
     * @param transcript raw text produced by the speech recogniser.
     * @param language language the recogniser was configured for (may be null).
     */
    fun match(transcript: String, language: Language? = null): Match {
        val normalized = TextTools.normalize(transcript)
        if (normalized.isEmpty()) return Match(false, 0.0)

        var best = Match(false, 0.0)

        val languagesToCheck = if (language != null) {
            listOf(language) + Language.entries.filter { it != language }
        } else {
            Language.entries.toList()
        }

        for (lang in languagesToCheck) {
            for (variant in variants[lang].orEmpty()) {
                val normalizedVariant = TextTools.normalize(variant)
                if (normalizedVariant.isEmpty()) continue

                // 1. Exact containment is the strongest signal.
                val contains = normalized.contains(normalizedVariant)
                // 2. Fuzzy similarity catches ASR errors such as "jarviss" or "jarvis bloo".
                val similarity = TextTools.fuzzySimilarity(normalized, normalizedVariant)

                val confidence = when {
                    contains -> 1.0
                    similarity >= 0.82 -> similarity
                    else -> similarity * 0.6
                }

                if (confidence > best.confidence) {
                    best = Match(
                        matched = contains || similarity >= 0.72,
                        confidence = confidence,
                        matchedPhrase = variant,
                        language = lang,
                    )
                }
            }
        }
        return best
    }

    /** True when the transcript contains the wake phrase plus additional instruction. */
    fun extractCommand(transcript: String): String? {
        val normalized = TextTools.normalize(transcript)
        for (variant in variants.values.flatten()) {
            val normalizedVariant = TextTools.normalize(variant)
            val index = normalized.indexOf(normalizedVariant)
            if (index >= 0) {
                val remainder = normalized.substring(index + normalizedVariant.length).trim()
                return remainder.ifEmpty { null }
            }
        }
        return null
    }

    companion object {
        const val DEFAULT_PHRASE = "Hey Jarvis Blue"
        const val ACCEPTANCE_THRESHOLD = 0.75
    }
}
