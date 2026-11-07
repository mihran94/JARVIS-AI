package com.jarvisblue.core.voice

import com.jarvisblue.core.model.Language

/**
 * Maps the app's languages onto the locales Android's speech services accept.
 *
 * Only locales that are actually installed on the device are offered, because
 * requesting an uninstalled locale silently degrades to a much worse engine.
 */
object VoiceLanguageProfile {

    data class LocaleCapability(
        val language: Language,
        val localeTag: String,
        val displayName: String,
        val onDeviceRecommended: Boolean,
    )

    val supported: List<LocaleCapability> = listOf(
        LocaleCapability(Language.ENGLISH, "en-US", "English (United States)", true),
        LocaleCapability(Language.ENGLISH, "en-IN", "English (India)", true),
        LocaleCapability(Language.TAMIL, "ta-IN", "Tamil (India)", true),
        LocaleCapability(Language.FRENCH, "fr-FR", "French (France)", false),
    )

    fun forLanguage(language: Language): LocaleCapability =
        supported.firstOrNull { it.language == language } ?: supported.first()

    /**
     * Orders the locales to try for a given language: the preferred locale first,
     * then the other locales of the same language, then any remaining locale.
     */
    fun fallbackChain(language: Language): List<LocaleCapability> {
        val primary = forLanguage(language)
        val sameLanguage = supported.filter { it.language == language && it.localeTag != primary.localeTag }
        val rest = supported.filter { it.language != language }
        return listOf(primary) + sameLanguage + rest
    }
}
