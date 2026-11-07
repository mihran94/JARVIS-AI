package com.jarvisblue.feature.studio

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.JarvisScaffold
import com.jarvisblue.core.ui.components.NoticeBanner
import com.jarvisblue.core.ui.components.SectionHeader
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.AmberWarn
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent
import com.jarvisblue.core.ui.theme.GreenOk
import com.jarvisblue.core.ui.theme.RedCritical

@Composable
fun StudioRoute(
    modifier: Modifier = Modifier,
    initialTab: Int = 0,
    viewModel: DevStudioViewModel = hiltViewModel(),
) {
    var tab by remember { mutableIntStateOf(initialTab) }
    val devState by viewModel.state.collectAsStateWithLifecycle()
    val cyberViewModel: CyberLabViewModel = hiltViewModel()
    val cyberState by cyberViewModel.state.collectAsStateWithLifecycle()
    val quantumViewModel: QuantumLabViewModel = hiltViewModel()
    val quantumState by quantumViewModel.state.collectAsStateWithLifecycle()

    JarvisScaffold(
        title = "Studio",
        subtitle = when (tab) {
            0 -> "AI development workbench"
            1 -> "Defensive security laboratory"
            else -> "Quantum research laboratory"
        },
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Dev") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Cyber") })
                Tab(selected = tab == 2, onClick = { tab = 2 }, text = { Text("Quantum") })
            }
            when (tab) {
                0 -> DevStudioScreen(
                    state = devState,
                    onCodeChange = viewModel::updateCode,
                    onLanguageChange = viewModel::setLanguage,
                    onExplanationLanguageChange = viewModel::setExplanationLanguage,
                    onExplain = viewModel::explain,
                    onReview = viewModel::review,
                    onGenerateTests = viewModel::generateTests,
                    onQualityCheck = viewModel::runQualityCheck,
                    onSecurityScan = viewModel::runSecurityScan,
                )
                1 -> CyberLabScreen(
                    state = cyberState,
                    onHostChange = cyberViewModel::setHost,
                    onPortChange = cyberViewModel::setPort,
                    onReviewTargetChange = cyberViewModel::setReviewTarget,
                    onAuthorize = cyberViewModel::grantAuthorization,
                    onRevoke = cyberViewModel::revokeAuthorization,
                    onProbe = cyberViewModel::probeHost,
                    onReview = cyberViewModel::reviewText,
                )
                else -> QuantumLabScreen(
                    state = quantumState,
                    onPreset = quantumViewModel::loadPreset,
                    onSimulate = quantumViewModel::simulate,
                    onAddGate = quantumViewModel::addGate,
                    onRemoveGate = quantumViewModel::removeLastGate,
                )
            }
        }
    }
}

@Composable
private fun DevStudioScreen(
    state: DevStudioUiState,
    onCodeChange: (String) -> Unit,
    onLanguageChange: (StudioLanguage) -> Unit,
    onExplanationLanguageChange: (Language) -> Unit,
    onExplain: () -> Unit,
    onReview: () -> Unit,
    onGenerateTests: () -> Unit,
    onQualityCheck: () -> Unit,
    onSecurityScan: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            StudioLanguage.entries.forEach { language ->
                FilterChip(
                    selected = state.language == language,
                    onClick = { onLanguageChange(language) },
                    label = { Text(language.label, style = MaterialTheme.typography.labelSmall) },
                )
            }
        }

        GlowCard(
            title = "Source",
            subtitle = "${state.lineCount} lines · ${state.language.label}",
            accent = CyanAccent,
        ) {
            OutlinedTextField(
                value = state.code,
                onValueChange = onCodeChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(260.dp),
                textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                shape = RoundedCornerShape(12.dp),
            )
        }

        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(onClick = onExplain, enabled = !state.isBusy) { Text("Explain") }
            OutlinedButton(onClick = onReview, enabled = !state.isBusy) { Text("Review") }
            OutlinedButton(onClick = onGenerateTests, enabled = !state.isBusy) { Text("Tests") }
            OutlinedButton(onClick = onQualityCheck) { Text("Quality check") }
            OutlinedButton(onClick = onSecurityScan) { Text("Security scan") }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Language.entries.forEach { language ->
                FilterChip(
                    selected = state.explanationLanguage == language,
                    onClick = { onExplanationLanguageChange(language) },
                    label = { Text(language.nativeName, style = MaterialTheme.typography.labelSmall) },
                )
            }
        }

        state.error?.let { NoticeBanner(it, accent = RedCritical) }

        if (state.output.isNotBlank()) {
            GlowCard(title = "Output", accent = BlueCore) {
                Text(
                    text = state.output,
                    style = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }

        if (state.findings.isNotEmpty()) {
            GlowCard(title = "Security findings", accent = AmberWarn) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    state.findings.forEach { finding ->
                        StatusPill(text = finding.severity.name, color = RedCritical)
                        Text(finding.title, style = MaterialTheme.typography.titleMedium)
                        Text(finding.remediation, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }

        SectionHeader(
            title = "Execution policy",
            subtitle = "Generated code is never executed on the device with unrestricted privileges",
        )
        NoticeBanner(
            "Local checks are static only (structure, markers, secret patterns). Anything " +
                "that needs a real toolchain — a full build, a test run, a package install — is " +
                "delegated to your Windows JARVIS BLUE machine.",
            accent = AmberWarn,
        )
    }
}
