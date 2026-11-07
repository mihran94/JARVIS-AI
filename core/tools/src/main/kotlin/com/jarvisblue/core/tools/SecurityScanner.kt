package com.jarvisblue.core.tools

import com.jarvisblue.core.model.FindingSeverity
import com.jarvisblue.core.model.SecurityFinding
import java.util.Locale
import java.util.UUID

/**
 * Defensive static analysis.
 *
 * This scanner only *reads* files the user has explicitly selected and reports
 * findings with remediation advice. It has no exploit capability, no payload
 * generation, and no credential harvesting.
 */
class SecurityScanner {

    data class ScanResult(
        val findings: List<SecurityFinding>,
        val linesScanned: Int,
        val filesScanned: Int,
    ) {
        val highest: FindingSeverity? get() = findings.maxByOrNull { it.severity.ordinal }?.severity
    }

    fun scanText(content: String, fileName: String = "source.txt"): ScanResult {
        val findings = mutableListOf<SecurityFinding>()
        val lines = content.lines()

        lines.forEachIndexed { index, raw ->
            val line = raw.trim()
            val lineNumber = index + 1

            if (line.contains("http://", ignoreCase = true) && !line.contains("http://localhost") &&
                !line.contains("http://127.0.0.1") && !line.contains("http://10.") &&
                !line.contains("schemas.android.com")
            ) {
                findings += finding(
                    title = "Cleartext HTTP endpoint",
                    severity = FindingSeverity.MEDIUM,
                    category = "Transport security",
                    description = "Line $lineNumber references an unencrypted http:// endpoint. " +
                        "Traffic can be observed and modified on the network.",
                    remediation = "Use https://, or scope a cleartextTrafficPolicy exception to " +
                        "explicitly trusted local hosts only.",
                    evidence = line.take(160),
                    reference = "OWASP A02:2021 Cryptographic Failures",
                    fileName = fileName,
                )
            }

            if (TRUST_ALL_PATTERNS.any { line.contains(it) }) {
                findings += finding(
                    title = "Certificate validation disabled",
                    severity = FindingSeverity.CRITICAL,
                    category = "Transport security",
                    description = "Line $lineNumber disables or bypasses TLS certificate validation. " +
                        "Connections can be silently intercepted.",
                    remediation = "Remove the custom TrustManager/HostnameVerifier and use the " +
                        "platform default trust store.",
                    evidence = line.take(160),
                    reference = "OWASP A02:2021 / CWE-295",
                    fileName = fileName,
                )
            }

            if (WEBVIEW_JS_PATTERNS.any { line.contains(it, ignoreCase = true) }) {
                findings += finding(
                    title = "WebView with JavaScript enabled",
                    severity = FindingSeverity.LOW,
                    category = "Input handling",
                    description = "Line $lineNumber enables JavaScript in a WebView. If the loaded " +
                        "content is not fully trusted this can enable script injection.",
                    remediation = "Only enable JavaScript for first-party content and serve it over https.",
                    evidence = line.take(160),
                    reference = "OWASP A03:2021 Injection",
                    fileName = fileName,
                )
            }

            if (HARDCODED_SECRET_PATTERNS.any { pattern -> pattern.containsMatchIn(line) } &&
                !line.contains("example") && !line.contains("your-") && !line.contains("changeme")
            ) {
                findings += finding(
                    title = "Possible hard-coded credential",
                    severity = FindingSeverity.HIGH,
                    category = "Secrets management",
                    description = "Line $lineNumber looks like it contains a literal secret value.",
                    remediation = "Move the value into Android Keystore-backed storage or a build-time " +
                        "secret provider; rotate the credential if it was ever committed.",
                    evidence = line.take(120).replace(Regex("""(['"])[^'"]{6,}\1"""), "$1••••••$1"),
                    reference = "OWASP A07:2021 Identification and Authentication Failures / CWE-798",
                    fileName = fileName,
                )
            }

            if (line.contains("android:exported=\"true\"", ignoreCase = true) &&
                !line.contains("intent-filter", ignoreCase = true)
            ) {
                findings += finding(
                    title = "Exported component without intent filter",
                    severity = FindingSeverity.MEDIUM,
                    category = "Access control",
                    description = "Line $lineNumber declares an exported component. Other apps on the " +
                        "device may call it directly.",
                    remediation = "Set android:exported=\"false\" unless the component must be reachable " +
                        "by other apps, and guard it with a signature-level permission if it does.",
                    evidence = line.take(160),
                    reference = "OWASP A01:2021 Broken Access Control / CWE-926",
                    fileName = fileName,
                )
            }

            if (line.contains("usesCleartextTraffic=\"true\"", ignoreCase = true)) {
                findings += finding(
                    title = "Cleartext traffic permitted application-wide",
                    severity = FindingSeverity.MEDIUM,
                    category = "Transport security",
                    description = "Line $lineNumber enables cleartext traffic for the whole application.",
                    remediation = "Remove the flag and rely on the default secure network security config.",
                    evidence = line.take(160),
                    reference = "OWASP A02:2021",
                    fileName = fileName,
                )
            }

            if (line.contains("MODE_WORLD", ignoreCase = true) || line.contains("MODE_WORLD_READABLE", ignoreCase = true) ||
                line.contains("MODE_WORLD_WRITEABLE", ignoreCase = true)
            ) {
                findings += finding(
                    title = "World-readable or world-writable file mode",
                    severity = FindingSeverity.HIGH,
                    category = "Access control",
                    description = "Line $lineNumber creates a file other apps can read or write.",
                    remediation = "Use MODE_PRIVATE, or store the data in a Room database encrypted with " +
                        "SQLCipher or in internal storage.",
                    evidence = line.take(160),
                    reference = "CWE-276",
                    fileName = fileName,
                )
            }

            if (line.contains("allowBackup=\"true\"", ignoreCase = true)) {
                findings += finding(
                    title = "Application backup enabled",
                    severity = FindingSeverity.LOW,
                    category = "Data protection",
                    description = "Line $lineNumber allows the app's data to be included in cloud/device backups.",
                    remediation = "Set android:allowBackup=\"false\" or define an explicit backup rules file " +
                        "that excludes sensitive databases and shared preferences.",
                    evidence = line.take(160),
                    reference = "OWASP A02:2021",
                    fileName = fileName,
                )
            }
        }

        return ScanResult(findings, lines.size, 1)
    }

    private fun finding(
        title: String,
        severity: FindingSeverity,
        category: String,
        description: String,
        remediation: String,
        evidence: String,
        reference: String,
        fileName: String,
    ) = SecurityFinding(
        id = UUID.randomUUID().toString(),
        title = title,
        severity = severity,
        category = category,
        description = description,
        remediation = remediation,
        evidence = evidence,
        reference = "$reference — $fileName",
    )

    companion object {
        private val TRUST_ALL_PATTERNS = listOf(
            "checkServerTrusted", "X509TrustManager", "ALLOW_ALL_HOSTNAME_VERIFIER",
            "setHostnameVerifier", "trustAllCerts", "trustAll",
        )

        private val WEBVIEW_JS_PATTERNS = listOf(
            "setJavaScriptEnabled(true)", "addJavascriptInterface",
        )

        private val HARDCODED_SECRET_PATTERNS = listOf(
            Regex("""(?i)["']?(api[_-]?key|secret|password|passwd|token)["']?\s*[:=]\s*["'][^"']{6,}["']"""),
            Regex("""(?i)sk-[A-Za-z0-9]{16,}"""),
            Regex("""(?i)AKIA[0-9A-Z]{16}"""),
        )
    }
}

/**
 * Lightweight code-quality checks that run entirely on-device.
 *
 * This is *not* a compiler and does not execute the analysed code. It reports
 * structural smells that are cheap to detect and useful to a reviewer.
 */
class CodeQualityChecker {

    data class QualityReport(
        val issues: List<CodeIssue>,
        val lines: Int,
        val language: String,
    )

    data class CodeIssue(
        val line: Int,
        val severity: FindingSeverity,
        val message: String,
        val hint: String = "",
    )

    fun check(content: String, language: String = "kotlin"): QualityReport {
        val issues = mutableListOf<CodeIssue>()
        val lines = content.lines()
        var depth = 0
        var inBlockComment = false

        lines.forEachIndexed { index, raw ->
            val lineNumber = index + 1
            val line = raw.trim()

            if (inBlockComment) {
                if (line.contains("*/")) inBlockComment = false
                return@forEachIndexed
            }
            if (line.startsWith("/*") && !line.contains("*/")) {
                inBlockComment = true
                return@forEachIndexed
            }
            if (line.startsWith("//") || line.startsWith("*")) return@forEachIndexed

            val opens = line.count { it == '{' || it == '(' || it == '[' }
            val closes = line.count { it == '}' || it == ')' || it == ']' }
            depth += opens - closes
            if (depth < 0) {
                issues += CodeIssue(lineNumber, FindingSeverity.HIGH, "Unbalanced closing bracket", "Extra '}' or ')'")
                depth = 0
            }

            if (line.length > 120) {
                issues += CodeIssue(lineNumber, FindingSeverity.LOW, "Line longer than 120 characters", "Wrap the expression")
            }
            if (line.contains("!!")) {
                issues += CodeIssue(lineNumber, FindingSeverity.MEDIUM, "Non-null assertion operator (!!) used", "Prefer safe calls or an explicit null check")
            }
            if (line.contains("TODO", ignoreCase = true) || line.contains("FIXME", ignoreCase = true)) {
                issues += CodeIssue(lineNumber, FindingSeverity.INFO, "Unresolved TODO/FIXME marker")
            }
            if (line.contains("print(") && language == "python") {
                issues += CodeIssue(lineNumber, FindingSeverity.INFO, "Debug print left in the source", "Use the logging framework instead")
            }
            if (line.contains("catch (Exception ") || line.contains("catch(_: Exception)")) {
                issues += CodeIssue(lineNumber, FindingSeverity.MEDIUM, "Broad exception handler", "Catch the specific exception type you can handle")
            }
        }

        if (depth != 0) {
            issues += CodeIssue(lines.size, FindingSeverity.HIGH, "Unbalanced brackets at end of file", "$depth opening bracket(s) never closed")
        }

        return QualityReport(issues, lines.size, language.lowercase(Locale.ROOT))
    }
}
