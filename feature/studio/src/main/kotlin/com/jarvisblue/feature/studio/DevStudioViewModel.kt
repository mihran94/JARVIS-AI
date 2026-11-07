package com.jarvisblue.feature.studio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.ai.AiRouter
import com.jarvisblue.core.ai.LanguageDetector
import com.jarvisblue.core.ai.TaskKind
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.tools.CodeQualityChecker
import com.jarvisblue.core.tools.SecurityScanner
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

enum class StudioLanguage(val id: String, val label: String) {
    KOTLIN("kotlin", "Kotlin"),
    JAVA("java", "Java"),
    PYTHON("python", "Python"),
    JAVASCRIPT("javascript", "JavaScript"),
    TYPESCRIPT("typescript", "TypeScript"),
    HTML("html", "HTML"),
    CSS("css", "CSS"),
    SQL("sql", "SQL"),
    BASH("bash", "Bash"),
    JSON("json", "JSON"),
}

data class DevStudioUiState(
    val code: String = DevStudioViewModel.SAMPLE_CODE,
    val language: StudioLanguage = StudioLanguage.KOTLIN,
    val explanationLanguage: Language = Language.ENGLISH,
    val output: String = "",
    val isBusy: Boolean = false,
    val qualityIssues: List<CodeQualityChecker.CodeIssue> = emptyList(),
    val findings: List<com.jarvisblue.core.model.SecurityFinding> = emptyList(),
    val providerId: ProviderId? = null,
    val statusLine: String = "Ready",
    val error: String? = null,
) {
    val lineCount: Int get() = code.lines().size
}

@HiltViewModel
class DevStudioViewModel @Inject constructor(
    private val router: AiRouter,
    private val qualityChecker: CodeQualityChecker,
    private val scanner: SecurityScanner,
) : ViewModel() {

    private val _state = MutableStateFlow(DevStudioUiState())
    val state: StateFlow<DevStudioUiState> = _state.asStateFlow()

    fun updateCode(code: String) {
        _state.value = _state.value.copy(code = code)
    }

    fun setLanguage(language: StudioLanguage) {
        _state.value = _state.value.copy(language = language)
    }

    fun setExplanationLanguage(language: Language) {
        _state.value = _state.value.copy(explanationLanguage = language)
    }

    /** On-device structural check. No code is executed and nothing leaves the phone. */
    fun runQualityCheck() {
        val report = qualityChecker.check(_state.value.code, _state.value.language.id)
        _state.value = _state.value.copy(
            qualityIssues = report.issues,
            output = if (report.issues.isEmpty()) {
                "No structural issues found in ${report.lines} line(s)."
            } else {
                report.issues.joinToString("\n") { "Line ${it.line}: ${it.message} — ${it.hint}" }
            },
            statusLine = "Quality check finished",
        )
    }

    /** On-device defensive review of the snippet. */
    fun runSecurityScan() {
        val result = scanner.scanText(_state.value.code, "snippet.${_state.value.language.id}")
        _state.value = _state.value.copy(
            findings = result.findings,
            output = if (result.findings.isEmpty()) {
                "No defensive findings in ${result.linesScanned} line(s)."
            } else {
                result.findings.joinToString("\n\n") { finding ->
                    "[${finding.severity}] ${finding.title}\n${finding.description}\nFix: ${finding.remediation}"
                }
            },
            statusLine = "Security review finished",
        )
    }

    /** Sends the snippet to the configured AI provider for an explanation. */
    fun explain() {
        val snapshot = _state.value
        if (snapshot.code.isBlank()) return
        _state.value = snapshot.copy(isBusy = true, statusLine = "Asking the model…", error = null)
        viewModelScope.launch {
            try {
                val languageInstruction = when (snapshot.explanationLanguage) {
                    Language.TAMIL -> "Explain in natural Tamil (தமிழ்)."
                    Language.FRENCH -> "Explain in natural French."
                    Language.ENGLISH -> "Explain in clear English."
                }
                val response = router.route(
                    request = com.jarvisblue.core.ai.AiRequest(
                        messages = listOf(
                            com.jarvisblue.core.ai.AiMessage(
                                role = "system",
                                content = "You are a senior ${snapshot.language.label} engineer. " +
                                    "$languageInstruction Be concrete and reference the code by name. " +
                                    "Never invent APIs that do not exist.",
                            ),
                            com.jarvisblue.core.ai.AiMessage(
                                role = "user",
                                content = "Explain this ${snapshot.language.label} code:\n\n```${snapshot.language.id}\n" +
                                    snapshot.code + "\n```",
                            ),
                        ),
                        enableTools = false,
                    ),
                    taskKind = TaskKind.CODING,
                )
                _state.value = _state.value.copy(
                    output = response.content,
                    isBusy = false,
                    providerId = runCatching { ProviderId.valueOf(response.providerId) }.getOrNull(),
                    statusLine = "Explanation ready",
                )
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    isBusy = false,
                    statusLine = "Failed",
                    error = t.message ?: "The provider could not be reached",
                )
            }
        }
    }

    /** Asks the model for a review with security and correctness notes. */
    fun review() {
        val snapshot = _state.value
        if (snapshot.code.isBlank()) return
        _state.value = snapshot.copy(isBusy = true, statusLine = "Reviewing…", error = null)
        viewModelScope.launch {
            try {
                val response = router.route(
                    request = com.jarvisblue.core.ai.AiRequest(
                        messages = listOf(
                            com.jarvisblue.core.ai.AiMessage(
                                role = "system",
                                content = "You are a meticulous code reviewer. Report correctness " +
                                    "bugs first, then security issues, then maintainability. Be " +
                                    "specific about line content. Do not invent issues.",
                            ),
                            com.jarvisblue.core.ai.AiMessage(
                                role = "user",
                                content = "Review this ${snapshot.language.label} code:\n\n```${snapshot.language.id}\n" +
                                    snapshot.code + "\n```",
                            ),
                        ),
                        enableTools = false,
                    ),
                    taskKind = TaskKind.CODING,
                )
                _state.value = _state.value.copy(
                    output = response.content,
                    isBusy = false,
                    statusLine = "Review ready",
                )
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    isBusy = false,
                    statusLine = "Failed",
                    error = t.message ?: "The provider could not be reached",
                )
            }
        }
    }

    /** Generates a test skeleton for the current snippet. */
    fun generateTests() {
        val snapshot = _state.value
        _state.value = snapshot.copy(isBusy = true, statusLine = "Generating tests…", error = null)
        viewModelScope.launch {
            try {
                val response = router.route(
                    request = com.jarvisblue.core.ai.AiRequest(
                        messages = listOf(
                            com.jarvisblue.core.ai.AiMessage(
                                role = "system",
                                content = "Write focused unit tests for the given code. Output only " +
                                    "a test file with a short header comment. Use the standard test " +
                                    "framework for the language.",
                            ),
                            com.jarvisblue.core.ai.AiMessage(
                                role = "user",
                                content = "```${snapshot.language.id}\n${snapshot.code}\n```",
                            ),
                        ),
                        enableTools = false,
                    ),
                    taskKind = TaskKind.CODING,
                )
                _state.value = _state.value.copy(
                    output = response.content,
                    isBusy = false,
                    statusLine = "Tests generated",
                )
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    isBusy = false,
                    statusLine = "Failed",
                    error = t.message ?: "The provider could not be reached",
                )
            }
        }
    }

    fun detectLanguageOfInput(): Language = LanguageDetector.detect(_state.value.code)

    companion object {
        const val SAMPLE_CODE = """fun greet(name: String): String {
    if (name.isBlank()) {
        return "Hello, stranger"
    }
    return "Hello, " + name.trim()
}

fun main() {
    println(greet("  Jarvis  "))
}"""
    }
}
