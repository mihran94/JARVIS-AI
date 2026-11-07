package com.jarvisblue.feature.command

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.jarvisblue.core.model.MemoryKind
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

// ---------------------------------------------------------------- permissions

@Composable
fun PermissionsRoute(
    modifier: Modifier = Modifier,
    viewModel: PermissionsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    PermissionsScreen(
        state = state,
        onPermissionChange = viewModel::setPermission,
        onToolChange = viewModel::setToolEnabled,
        onEmergencyStop = viewModel::engageEmergencyStop,
        onReleaseStop = viewModel::releaseEmergencyStop,
        onAppLockChange = viewModel::setAppLockEnabled,
        onBiometricChange = viewModel::setBiometricRequired,
        onSessionTimeout = viewModel::setSessionTimeout,
        onRevokeAll = viewModel::revokeEverything,
        modifier = modifier,
    )
}

@Composable
fun PermissionsScreen(
    state: PermissionsUiState,
    onPermissionChange: (com.jarvisblue.core.model.Permission, Boolean) -> Unit,
    onToolChange: (String, Boolean) -> Unit,
    onEmergencyStop: () -> Unit,
    onReleaseStop: () -> Unit,
    onAppLockChange: (Boolean) -> Unit,
    onBiometricChange: (Boolean) -> Unit,
    onSessionTimeout: (Int) -> Unit,
    onRevokeAll: () -> Unit,
    modifier: Modifier = Modifier,
) {
    JarvisScaffold(
        title = "Permissions",
        subtitle = state.statusLine,
        modifier = modifier,
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                GlowCard(
                    title = "Emergency stop",
                    subtitle = "Halts every tool, service and remote command until released",
                    accent = if (state.emergencyStopEngaged) RedCritical else AmberWarn,
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = if (state.emergencyStopEngaged) {
                                "STOPPED — ${state.emergencyReason ?: "engaged"}"
                            } else {
                                "The assistant is live. Engage the stop to freeze all activity."
                            },
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (state.emergencyStopEngaged) RedCritical else MaterialTheme.colorScheme.onSurface,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = onEmergencyStop,
                                enabled = !state.emergencyStopEngaged,
                            ) { Text("Engage stop") }
                            OutlinedButton(
                                onClick = onReleaseStop,
                                enabled = state.emergencyStopEngaged,
                            ) { Text("Release") }
                        }
                    }
                }
            }

            item {
                GlowCard(title = "App lock", accent = BlueCore) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        ToggleRow(
                            label = "Require unlock on launch",
                            description = "The app locks after the session timeout",
                            checked = state.appLockEnabled,
                            onCheckedChange = onAppLockChange,
                        )
                        ToggleRow(
                            label = "Biometric confirmation for sensitive tools",
                            description = "Sending messages, deleting files and remote commands",
                            checked = state.biometricRequired,
                            onCheckedChange = onBiometricChange,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf(5, 15, 60).forEach { minutes ->
                                FilterChip(
                                    selected = state.sessionTimeoutMinutes == minutes,
                                    onClick = { onSessionTimeout(minutes) },
                                    label = { Text("$minutes min", style = MaterialTheme.typography.labelSmall) },
                                )
                            }
                        }
                    }
                }
            }

            item {
                SectionHeader(
                    title = "Capabilities",
                    subtitle = "Each bucket is independent; granting one never grants another",
                )
            }

            items(state.permissions, key = { it.permission.id }) { row ->
                GlowCard(
                    title = row.permission.label,
                    subtitle = row.permission.description,
                    accent = if (row.granted) GreenOk else BlueCore,
                    trailing = {
                        Switch(
                            checked = row.granted,
                            onCheckedChange = { onPermissionChange(row.permission, it) },
                        )
                    },
                ) {
                    if (row.permission.sensitive) {
                        StatusPill(text = "Sensitive", color = AmberWarn)
                    }
                }
            }

            item {
                SectionHeader(
                    title = "Tools",
                    subtitle = "Individual tools can be switched off without revoking a whole capability",
                )
            }

            items(state.tools, key = { it.name }) { tool ->
                GlowCard(
                    title = tool.displayName,
                    subtitle = "${tool.category} · risk ${tool.riskLevel}",
                    accent = if (tool.enabled) CyanAccent else BlueCore,
                    trailing = {
                        Switch(
                            checked = tool.enabled,
                            onCheckedChange = { onToolChange(tool.name, it) },
                        )
                    },
                ) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        if (tool.requiresConfirmation) {
                            StatusPill(text = "Confirmation required", color = AmberWarn)
                        }
                        if (tool.requiredPermissions.isNotEmpty()) {
                            Text(
                                text = "Needs: ${tool.requiredPermissions.joinToString(", ")}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }

            item {
                Spacer(Modifier.height(8.dp))
                OutlinedButton(onClick = onRevokeAll) { Text("Revoke every in-app grant") }
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@Composable
private fun ToggleRow(
    label: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.titleMedium)
            Text(
                description,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

// -------------------------------------------------------------------- memory

@Composable
fun MemoryRoute(
    modifier: Modifier = Modifier,
    viewModel: MemoryViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    MemoryScreen(
        state = state,
        onTitleChange = viewModel::setTitle,
        onBodyChange = viewModel::setBody,
        onKindChange = viewModel::setKind,
        onSave = viewModel::save,
        onDelete = viewModel::delete,
        onClearAll = viewModel::clearAll,
        modifier = modifier,
    )
}

@Composable
fun MemoryScreen(
    state: MemoryUiState,
    onTitleChange: (String) -> Unit,
    onBodyChange: (String) -> Unit,
    onKindChange: (MemoryKind) -> Unit,
    onSave: () -> Unit,
    onDelete: (com.jarvisblue.core.model.MemoryItem) -> Unit,
    onClearAll: () -> Unit,
    modifier: Modifier = Modifier,
) {
    JarvisScaffold(
        title = "Memory",
        subtitle = "${state.items.size} item(s) · encrypted at rest",
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlowCard(title = "New memory", accent = BlueCore) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = state.draftTitle,
                        onValueChange = onTitleChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Title") },
                        shape = RoundedCornerShape(12.dp),
                    )
                    OutlinedTextField(
                        value = state.draftBody,
                        onValueChange = onBodyChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Detail") },
                        shape = RoundedCornerShape(12.dp),
                    )
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        MemoryKind.entries.forEach { kind ->
                            FilterChip(
                                selected = state.draftKind == kind,
                                onClick = { onKindChange(kind) },
                                label = { Text(kind.name, style = MaterialTheme.typography.labelSmall) },
                            )
                        }
                    }
                    Button(
                        onClick = onSave,
                        enabled = state.draftTitle.isNotBlank() && state.draftBody.isNotBlank(),
                    ) { Text("Store") }
                }
            }

            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(state.items, key = { it.id }) { item ->
                    GlowCard(
                        title = item.title,
                        subtitle = "${item.kind.name} · ${item.source}",
                        accent = CyanAccent,
                        trailing = {
                            TextButton(onClick = { onDelete(item) }) { Text("Delete") }
                        },
                    ) {
                        Text(item.body, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }

            if (state.items.isNotEmpty()) {
                OutlinedButton(onClick = onClearAll) { Text("Delete all memories") }
            }
            Text(
                text = state.statusLine,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(16.dp))
        }
    }
}
