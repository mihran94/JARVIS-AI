package com.jarvisblue.core.tools

import com.jarvisblue.core.model.Language
import com.jarvisblue.core.common.TextTools

/**
 * Rule-based natural-language intent detection.
 *
 * This is deliberately *not* an AI model: routing a command to a tool must be
 * deterministic and auditable. The AI is used to compose the answer, but the
 * mapping from "organise my downloaded PDFs" to `organize_files` happens here,
 * where it can be tested and shown to the user.
 *
 * Matching works on normalised tokens, so it works in English, Tamil and French
 * as long as the trigger vocabulary is provided.
 */
class IntentRouter {

    enum class IntentType {
        ORGANIZE_FILES, OPEN_PROJECT, EXPLAIN_CODE, SET_REMINDER, CHECK_REMOTE_JOB,
        SECURITY_REVIEW, OPEN_APP, SET_ALARM, CALL_CONTACT, SEND_MESSAGE, SYSTEM_DIAGNOSTICS,
        PLAY_MEDIA, GENERAL_CHAT,
    }

    data class Intent(
        val type: IntentType,
        val confidence: Double,
        val slots: Map<String, String> = emptyMap(),
        val matchedPhrase: String = "",
    ) {
        val isActionable: Boolean get() = type != IntentType.GENERAL_CHAT
    }

    private data class Rule(
        val intent: IntentType,
        val phrases: List<String>,
        val slotPatterns: Map<String, Regex> = emptyMap(),
        val confidence: Double = 0.85,
    )

    private val rules: List<Rule> = listOf(
        Rule(
            intent = IntentType.ORGANIZE_FILES,
            phrases = listOf(
                "organize my downloaded files", "organise my downloaded files",
                "organize my downloads", "organise my downloads",
                "sort my pdf files", "arrange my downloaded pdf files",
                "group my downloads", "clean up my downloads",
            ),
            slotPatterns = mapOf(
                "extension" to Regex("""\b([a-z0-9]{2,5})\b"""),
            ),
            confidence = 0.9,
        ),
        Rule(
            intent = IntentType.OPEN_PROJECT,
            phrases = listOf(
                "open my development project", "open my dev project", "open my project",
                "open project", "show my project",
            ),
            slotPatterns = mapOf(
                "path" to Regex("""(?:project|folder|directory)\s+([\w\-./\\ ]+)"""),
            ),
        ),
        Rule(
            intent = IntentType.EXPLAIN_CODE,
            phrases = listOf(
                "explain this code", "explain this code in tamil", "explain this code in english",
                "explain this code in french", "explain the code", "review this code",
                "explain this snippet", "explain this function",
            ),
            slotPatterns = mapOf(
                "explanationLanguage" to Regex(
                    """(?:in|இல்|en)\s+(tamil|english|french|தமிழ்)"""
                ),
            ),
        ),
        Rule(
            intent = IntentType.SET_REMINDER,
            phrases = listOf(
                "remind me", "set a reminder", "remind me about", "create a reminder",
                "schedule a reminder",
            ),
            slotPatterns = mapOf(
                "when" to Regex(
                    """(?:about|on|at|for)?\s*(tomorrow|today|tonight|next week|in \d+ (?:minutes|hours|days))\b"""
                ),
                "what" to Regex("""(?:about|regarding|that|to)\s+(.+)$"""),
            ),
        ),
        Rule(
            intent = IntentType.CHECK_REMOTE_JOB,
            phrases = listOf(
                "check the progress of my windows render job",
                "check my render job", "check the progress of my windows job",
                "status of my render job", "check my windows job", "job progress",
                "check my python project",
            ),
            slotPatterns = mapOf(
                "kind" to Regex("""(render|after effects|python|code review|document)\s*job"""),
            ),
            confidence = 0.88,
        ),
        Rule(
            intent = IntentType.SECURITY_REVIEW,
            phrases = listOf(
                "inspect this application for security issues",
                "check this app for security issues", "security review",
                "audit this app", "security check", "run a security scan",
            ),
            slotPatterns = mapOf(
                "target" to Regex("""(?:application|app|apk|file)\s+(.+)$"""),
            ),
        ),
        Rule(
            intent = IntentType.OPEN_APP,
            phrases = listOf(
                "open app", "launch app", "open the app", "launch the app",
                "open whatsapp", "open chrome", "open settings", "open camera",
                "open my development project app",
            ),
            slotPatterns = mapOf(
                "appName" to Regex("""(?:open|launch)\s+(?:the\s+)?(?:app\s+)?([\w\s]+?)\s*(?:app)?$"""),
            ),
            confidence = 0.75,
        ),
        Rule(
            intent = IntentType.SET_ALARM,
            phrases = listOf(
                "set an alarm", "wake me up", "set alarm", "create an alarm",
            ),
            slotPatterns = mapOf(
                "time" to Regex("""(\d{1,2}[:.]?\d{0,2}\s*(?:am|pm)?)"""),
            ),
        ),
        Rule(
            intent = IntentType.CALL_CONTACT,
            phrases = listOf("call ", "place a call to", "phone "),
            confidence = 0.8,
        ),
        Rule(
            intent = IntentType.SEND_MESSAGE,
            phrases = listOf("send a message to", "send a whatsapp message", "message "),
            confidence = 0.8,
        ),
        Rule(
            intent = IntentType.SYSTEM_DIAGNOSTICS,
            phrases = listOf(
                "battery status", "how much storage", "check my battery",
                "diagnostics", "system status", "how much memory",
            ),
        ),
        Rule(
            intent = IntentType.PLAY_MEDIA,
            phrases = listOf("play ", "pause the music", "resume playback", "next track"),
            confidence = 0.7,
        ),
    )

    fun detect(utterance: String): Intent {
        val normalized = TextTools.normalize(utterance)
        if (normalized.isBlank()) return Intent(IntentType.GENERAL_CHAT, 0.0)

        val tokens = TextTools.tokens(normalized)
        var best = Intent(IntentType.GENERAL_CHAT, 0.0)

        for (rule in rules) {
            for (phrase in rule.phrases) {
                val phraseTokens = TextTools.tokens(TextTools.normalize(phrase))
                if (phraseTokens.isEmpty()) continue
                val score = bestWindowScore(tokens, phraseTokens)
                if (score >= MATCH_THRESHOLD && score > best.confidence) {
                    best = Intent(
                        type = rule.intent,
                        confidence = (score * rule.confidence).coerceIn(0.0, 0.99),
                        slots = extractSlots(utterance, rule),
                        matchedPhrase = phrase,
                    )
                }
            }
        }
        return best
    }

    /**
     * Scores the best token window of the utterance against the phrase.
     *
     * A windowed comparison is used instead of whole-string similarity so that
     * prefixes ("Jarvis, …"), trailing words ("… files") and inserted words
     * ("downloaded **PDF** files") do not destroy the match.
     */
    private fun bestWindowScore(tokens: List<String>, phrase: List<String>): Double {
        if (tokens.isEmpty()) return 0.0
        if (phrase.size > tokens.size) {
            return TextTools.fuzzySimilarity(tokens.joinToString(" "), phrase.joinToString(" "))
        }

        var best = 0.0
        val windowSize = phrase.size
        for (start in 0..(tokens.size - windowSize)) {
            val window = tokens.subList(start, start + windowSize)
            var overlap = 0
            val remaining = phrase.toMutableList()
            for (token in window) {
                val index = remaining.indexOfFirst { TextTools.fuzzySimilarity(it, token) >= 0.85 }
                if (index >= 0) {
                    overlap++
                    remaining.removeAt(index)
                }
            }
            val coverage = overlap.toDouble() / phrase.size
            if (coverage > best) best = coverage
        }
        return best
    }

    private fun extractSlots(utterance: String, rule: Rule): Map<String, String> {
        val lower = utterance.lowercase()
        val slots = mutableMapOf<String, String>()
        for ((slot, pattern) in rule.slotPatterns) {
            val match = pattern.find(lower) ?: continue
            val raw = match.groupValues.getOrNull(1)?.trim().orEmpty()
            if (raw.isNotEmpty()) slots[slot] = raw
        }
        return slots
    }

    /**
     * Describes, in plain language, what a detected intent will do.
     *
     * This is shown to the user before a rule-driven task runs, so the mapping
     * from a spoken command to a concrete action is never invisible.
     */
    fun describeExecution(intent: Intent): String = when (intent.type) {
        IntentType.ORGANIZE_FILES ->
            "Group files in the folder you granted into per-type sub-folders (copy first, originals kept)."
        IntentType.OPEN_PROJECT ->
            "Open the development project folder you selected."
        IntentType.EXPLAIN_CODE ->
            "Explain the selected code in ${explanationLanguage(intent.slots).nativeName}."
        IntentType.SET_REMINDER ->
            "Create a reminder and schedule a notification for it."
        IntentType.CHECK_REMOTE_JOB ->
            "Read the job list from your paired Windows machine."
        IntentType.SECURITY_REVIEW ->
            "Run the on-device defensive review over the selected file."
        IntentType.OPEN_APP ->
            "Launch the app “${intent.slots["appName"].orEmpty()}”."
        IntentType.SET_ALARM ->
            "Create an alarm in the system clock."
        IntentType.CALL_CONTACT ->
            "Open the dialler with the contact you named (the call is placed by you)."
        IntentType.SEND_MESSAGE ->
            "Open a messaging app with the draft text so you can send it."
        IntentType.SYSTEM_DIAGNOSTICS ->
            "Read the battery, storage, memory and network status of this device."
        IntentType.PLAY_MEDIA ->
            "Send a media transport command to the app that is currently playing."
        IntentType.GENERAL_CHAT ->
            "Send the message to the AI provider for an answer."
    }

    /** Maps the requested explanation language onto a supported [Language]. */
    companion object {
        /** Minimum window coverage before a phrase is accepted as a command. */
        const val MATCH_THRESHOLD = 0.72
    }

    fun explanationLanguage(slots: Map<String, String>): Language {
        val raw = slots["explanationLanguage"]?.lowercase() ?: return Language.ENGLISH
        return when {
            raw.startsWith("tamil") || raw.contains("தமிழ்") -> Language.TAMIL
            raw.startsWith("french") -> Language.FRENCH
            else -> Language.ENGLISH
        }
    }
}
