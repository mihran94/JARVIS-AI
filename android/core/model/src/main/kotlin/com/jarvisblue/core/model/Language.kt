package com.jarvisblue.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Languages JARVIS BLUE can understand and speak.
 *
 * @property tag BCP-47 / ISO-639-1 tag used by Android SpeechRecognizer & TextToSpeech.
 * @property displayName Human readable name (English).
 * @property nativeName Name in the language itself.
 */
@Serializable
enum class Language(
    val tag: String,
    val displayName: String,
    val nativeName: String,
) {
    @SerialName("en")
    ENGLISH("en-US", "English", "English"),

    @SerialName("ta")
    TAMIL("ta-IN", "Tamil", "தமிழ்"),

    @SerialName("fr")
    FRENCH("fr-FR", "French", "Français");

    companion object {
        fun fromTag(tag: String?): Language? {
            if (tag.isNullOrBlank()) return null
            val primary = tag.substringBefore('-').lowercase()
            return entries.firstOrNull { it.tag.substringBefore('-').lowercase() == primary }
        }
    }
}
