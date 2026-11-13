package com.jarvisblue.feature.studio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.model.AuthorizationKind
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.NoticeBanner
import com.jarvisblue.core.ui.components.SectionHeader
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.AmberWarn
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.GreenOk
import com.jarvisblue.core.ui.theme.RedCritical

@Composable
fun CyberLabScreen(
    state: CyberLabUiState,
    onHostChange: (String) -> Unit,
    onPortChange: (String) -> Unit,
    onReviewTargetChange: (String) -> Unit,
    onAuthorize: (AuthorizationKind, String, String) -> Unit,
    onRevoke: () -> Unit,
    onProbe: () -> Unit,
    onReview: () -> Unit,
) {
    var kind by remember { mutableStateOf(AuthorizationKind.OWNED_NETWORK) }
    var scope by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var kindMenuOpen by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        NoticeBanner(
            "This module is for defensive work on networks and devices you own or have " +
                "written permission to test. It performs DNS, TCP and TLS observation only — " +
                "no exploitation, no credential testing, no persistence.",
            accent = AmberWarn,
        )

        GlowCard(
            title = "Authorisation",
            subtitle = state.authorization?.let { "${it.kind.name.replace('_', ' ')} · ${it.scope}" }
                ?: "Required before any active inspection",
            accent = if (state.authorization != null) GreenOk else AmberWarn,
            trailing = {
                if (state.authorization != null) {
                    OutlinedButton(onClick = onRevoke) { Text("Revoke") }
                }
            },
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = scope,
                    onValueChange = { scope = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Scope (host, CIDR or lab name)") },
                    shape = RoundedCornerShape(12.dp),
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Authorisation notes") },
                    shape = RoundedCornerShape(12.dp),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { kindMenuOpen = true }) {
                        Text(kind.name.replace('_', ' '))
                    }
                    DropdownMenu(expanded = kindMenuOpen, onDismissRequest = { kindMenuOpen = false }) {
                        AuthorizationKind.entries.forEach { option ->
                            DropdownMenuItem(
                                text = { Text(option.name.replace('_', ' ')) },
                                onClick = {
                                    kind = option
                                    kindMenuOpen = false
                                },
                            )
                        }
                    }
                    Button(
                        onClick = { onAuthorize(kind, scope, notes) },
                        enabled = scope.isNotBlank(),
                    ) { Text("Record authorisation") }
                }
            }
        }

        GlowCard(title = "Host inspection", accent = BlueCore) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = state.host,
                        onValueChange = onHostChange,
                        modifier = Modifier.weight(1f),
                        label = { Text("Host") },
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                    )
                    OutlinedTextField(
                        value = state.port,
                        onValueChange = onPortChange,
                        modifier = Modifier.width(96.dp),
                        label = { Text("Port") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        shape = RoundedCornerShape(12.dp),
                    )
                }
                Button(
                    onClick = onProbe,
                    enabled = state.authorization != null && !state.isBusy,
                ) { Text(if (state.isBusy) "Inspecting…" else "Inspect host") }

                state.probe?.let { probe ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        StatusPill(
                            text = if (probe.reachable) "Reachable" else "Unreachable",
                            color = if (probe.reachable) GreenOk else RedCritical,
                        )
                        DetailRow("Resolved", probe.resolvedAddresses.joinToString(", "))
                        DetailRow("DNS", "${probe.dnsMs ?: "?"} ms")
                        DetailRow("TCP connect", "${probe.tcpConnectMs ?: "?"} ms")
                        DetailRow("TLS version", probe.tlsVersion ?: "n/a")
                        DetailRow("Cipher", probe.tlsCipher ?: "n/a")
                        DetailRow("Subject", probe.tlsSubject ?: "n/a")
                        DetailRow("Issuer", probe.tlsIssuer ?: "n/a")
                        DetailRow("Valid until", probe.tlsNotAfter ?: "n/a")
                        DetailRow("Chain length", "${probe.certificateChainLength ?: "?"}")
                        probe.error?.let { DetailRow("Error", it) }
                        DetailRow("Trust store", state.trustDetail.ifBlank { "not checked" })
                    }
                }
            }
        }

        GlowCard(title = "Defensive code review", accent = BlueCore) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = state.reviewTarget,
                    onValueChange = onReviewTargetChange,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp),
                    label = { Text("Paste source or manifest text") },
                    shape = RoundedCornerShape(12.dp),
                )
                OutlinedButton(onClick = onReview, enabled = state.reviewTarget.isNotBlank()) {
                    Text("Review")
                }
                state.findings.forEach { finding ->
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            StatusPill(text = finding.severity.name, color = RedCritical)
                            StatusPill(text = finding.category, color = BlueCore)
                        }
                        Text(finding.title, style = MaterialTheme.typography.titleMedium)
                        Text(finding.description, style = MaterialTheme.typography.bodyMedium)
                        Text("Fix: ${finding.remediation}", style = MaterialTheme.typography.bodyMedium)
                        Text(finding.reference, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }

        SectionHeader(
            title = "Learning references",
            subtitle = "OWASP Top 10 and CWE mappings are embedded in every finding",
        )
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(120.dp),
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}
