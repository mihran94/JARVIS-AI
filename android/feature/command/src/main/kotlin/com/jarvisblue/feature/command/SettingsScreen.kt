package com.jarvisblue.feature.command

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvisblue.core.model.ProviderHealthState
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.JarvisScaffold
import com.jarvisblue.core.ui.components.MetricChip
import com.jarvisblue.core.ui.components.NoticeBanner
import com.jarvisblue.core.ui.components.SectionHeader
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.AmberWarn
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent
import com.jarvisblue.core.ui.theme.GreenOk
import com.jarvisblue.core.ui.theme.RedCritical

@Composable
fun SettingsRoute(
    modifier: Modifier = Modifier,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    SettingsScreen(
        state = state,
        onProviderEnabled = viewModel::setProviderEnabled,
        onProviderBaseUrl = viewModel::setProviderBaseUrl,
        onProviderModel = viewModel::setProviderModel,
        onSaveKey = viewModel::saveApiKey,
        onHealthCheck = viewModel::runHealthCheck,
        onDarkTheme = viewModel::setDarkTheme,
        onAppLock = viewModel::setAppLockEnabled,
        onBiometric = viewModel::setBiometricRequired,
        onSessionTimeout = viewModel::setSessionTimeout,
        onClearMemory = viewModel::clearMemory,
        onClearAudit = viewModel::clearAudit,
        onEmergencyStop = viewModel::engageEmergencyStop,
        onReleaseStop = viewModel::releaseEmergencyStop,
        modifier = modifier,
    )
}

@Composable
fun SettingsScreen(
    state: SettingsUiState,
    onProviderEnabled: (ProviderId, Boolean) -> Unit,
    onProviderBaseUrl: (ProviderId, String) -> Unit,
    onProviderModel: (ProviderId, String) -> Unit,
    onSaveKey: (ProviderId, String) -> Unit,
    onHealthCheck: () -> Unit,
    onDarkTheme: (Boolean) -> Unit,
    onAppLock: (Boolean) -> Unit,
    onBiometric: (Boolean) -> Unit,
    onSessionTimeout: (Int) -> Unit,
    onClearMemory: () -> Unit,
    onClearAudit: () -> Unit,
    onEmergencyStop: () -> Unit,
    onReleaseStop: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var keyDrafts by remember { mutableStateOf<Map<ProviderId, String>>(emptyMap()) }
    var urlDrafts by remember { mutableStateOf<Map<ProviderId, String>>(emptyMap()) }
    var modelDrafts by remember { mutableStateOf<Map<ProviderId, String>>(emptyMap()) }

    JarvisScaffold(
        title = "Settings",
        subtitle = state.statusLine,
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlowCard(
                title = "AI providers",
                subtitle = "Keys are encrypted with the Android Keystore and never leave this device unencrypted",
                accent = BlueCore,
                trailing = { OutlinedButton(onClick = onHealthCheck) { Text("Health check") } },
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    state.providers.forEach { provider ->
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Text(provider.providerId.displayName, style = MaterialTheme.typography.titleMedium)
                                Switch(
                                    checked = provider.enabled,
                                    onCheckedChange = { onProviderEnabled(provider.providerId, it) },
                                )
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                StatusPill(
                                    text = provider.health?.state?.name?.replace('_', ' ') ?: "not checked",
                                    color = when (provider.health?.state) {
                                        ProviderHealthState.HEALTHY -> GreenOk
                                        ProviderHealthState.DEGRADED -> AmberWarn
                                        ProviderHealthState.UNAVAILABLE -> RedCritical
                                        else -> BlueCore
                                    },
                                )
                                provider.maskedKey?.let {
                                    StatusPill(text = "key $it", color = CyanAccent)
                                }
                            }
                            OutlinedTextField(
                                value = urlDrafts[provider.providerId] ?: provider.baseUrl,
                                onValueChange = { urlDrafts = urlDrafts + (provider.providerId to it) },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("Base URL") },
                                singleLine = true,
                                shape = RoundedCornerShape(12.dp),
                            )
                            OutlinedTextField(
                                value = modelDrafts[provider.providerId] ?: provider.modelId,
                                onValueChange = { modelDrafts = modelDrafts + (provider.providerId to it) },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("Model id") },
                                singleLine = true,
                                shape = RoundedCornerShape(12.dp),
                            )
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(
                                    onClick = {
                                        onProviderBaseUrl(
                                            provider.providerId,
                                            urlDrafts[provider.providerId] ?: provider.baseUrl,
                                        )
                                        onProviderModel(
                                            provider.providerId,
                                            modelDrafts[provider.providerId] ?: provider.modelId,
                                        )
                                    },
                                ) { Text("Save") }
                            }
                            if (provider.providerId != ProviderId.OFFLINE_ECHO) {
                                OutlinedTextField(
                                    value = keyDrafts[provider.providerId].orEmpty(),
                                    onValueChange = {
                                        keyDrafts = keyDrafts + (provider.providerId to it)
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    label = { Text("API key (stored encrypted)") },
                                    singleLine = true,
                                    shape = RoundedCornerShape(12.dp),
                                )
                                OutlinedButton(
                                    onClick = {
                                        onSaveKey(
                                            provider.providerId,
                                            keyDrafts[provider.providerId].orEmpty(),
                                        )
                                        keyDrafts = keyDrafts - provider.providerId
                                    },
                                ) { Text("Save key") }
                            }
                        }
                    }
                }
            }

            GlowCard(title = "Appearance & security", accent = CyanAccent) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Dark theme", style = MaterialTheme.typography.titleMedium)
                        Switch(checked = state.darkTheme, onCheckedChange = onDarkTheme)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("App lock", style = MaterialTheme.typography.titleMedium)
                        Switch(checked = state.appLockEnabled, onCheckedChange = onAppLock)
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Biometric for sensitive tools", style = MaterialTheme.typography.titleMedium)
                        Switch(checked = state.biometricRequired, onCheckedChange = onBiometric)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(5, 15, 60).forEach { minutes ->
                            FilterChip(
                                selected = state.sessionTimeoutMinutes == minutes,
                                onClick = { onSessionTimeout(minutes) },
                                label = { Text("$minutes min", style = MaterialTheme.typography.labelSmall) },
                            )
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricChip(
                            label = "Keystore",
                            value = if (state.hardwareBackedKey) "hardware backed" else "software",
                            accent = if (state.hardwareBackedKey) GreenOk else AmberWarn,
                        )
                    }
                }
            }

            GlowCard(title = "Your data", accent = BlueCore) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = onClearMemory) { Text("Delete all memories") }
                        OutlinedButton(onClick = onClearAudit) { Text("Clear audit log") }
                    }
                    Text(
                        text = "You can revoke every permission and disconnect the Windows machine " +
                            "at any time. Deleting the app removes the encrypted database and the " +
                            "Keystore key with it.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            SectionHeader(title = "Audit trail", subtitle = "${state.auditEvents.size} recent event(s)")
            GlowCard(accent = BlueCore) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    state.auditEvents.take(40).forEach { event ->
                        Row(modifier = Modifier.fillMaxWidth()) {
                            Text(
                                text = event.title,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.weight(1f),
                            )
                            StatusPill(
                                text = event.severity.name,
                                color = when (event.severity) {
                                    com.jarvisblue.core.model.AuditSeverity.CRITICAL -> RedCritical
                                    com.jarvisblue.core.model.AuditSeverity.WARNING -> AmberWarn
                                    else -> BlueCore
                                },
                            )
                        }
                    }
                    if (state.auditEvents.isEmpty()) {
                        Text(
                            text = "No audit events yet.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            GlowCard(title = "Build", accent = CyanAccent) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = "JARVIS BLUE MOBILE · 1.0.0 · private sideload build",
                        style = MaterialTheme.typography.bodyMedium,
                        fontFamily = FontFamily.Monospace,
                    )
                    Text(
                        text = "minSdk 31 (Android 12) · targetSdk 35 (Android 15)",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}
