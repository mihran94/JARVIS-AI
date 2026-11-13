package com.jarvisblue.core.common

/**
 * Removes anything that looks like a credential before it reaches a log sink,
 * an audit row or an exported file. The app never logs API keys, even by accident.
 *
 * Rules are applied in order; the first rule that matches a span wins, so the
 * more specific patterns (authorization headers, URLs with inline credentials)
 * run before the generic key/value assignment rule.
 */
object Redactor {

    private const val SECRET = "[REDACTED_SECRET]"
    private const val KEY = "[REDACTED_API_KEY]"

    private data class Rule(val regex: Regex, val replace: (MatchResult) -> String)

    private val rules: List<Rule> = listOf(
        // Authorization: Bearer <token> / Basic <token>
        Rule(
            Regex("""(?i)(Authorization\s*:\s*)(Bearer|Basic|Token)\s+([A-Za-z0-9._\-+/=]{6,})""")
        ) { m -> "${m.groupValues[1]}${m.groupValues[2]} $SECRET" },

        // Credentials embedded in a URL: scheme://user:pass@host
        Rule(
            Regex("""(?i)\b([a-z][a-z0-9+.\-]*://)([^/\s:@]+):([^/\s:@]+)@""")
        ) { m -> "${m.groupValues[1]}${m.groupValues[2]}:$SECRET@" },

        // Provider-shaped API keys: sk-…, ghp_…, xoxb-…, AKIA…, JWTs
        Rule(
            Regex(
                """(?i)\b(sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|""" +
                    """xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}|""" +
                    """eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,})"""
            )
        ) { _ -> KEY },

        // key = value / key: value assignments
        Rule(
            Regex(
                """(?i)\b(api[_-]?key|apikey|secret|password|passwd|token|bearer|""" +
                    """authorization|client[_-]?secret|access[_-]?key|private[_-]?key)\b""" +
                    """(\s*[:=]\s*)("?)([^\s"',;}\]]{4,})("?)"""
            )
        ) { m ->
            "${m.groupValues[1]}${m.groupValues[2]}${m.groupValues[3]}$SECRET${m.groupValues[5]}"
        },
    )

    fun redact(input: String): String {
        var out = input
        for (rule in rules) {
            out = rule.regex.replace(out, rule.replace)
        }
        return out
    }

    /** Masks all but the last 4 characters — used when echoing a secret in the UI. */
    fun mask(secret: String): String {
        if (secret.isEmpty()) return ""
        if (secret.length <= 4) return "•".repeat(secret.length)
        return "•".repeat(secret.length - 4) + secret.takeLast(4)
    }
}
