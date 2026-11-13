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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvisblue.core.model.BridgeJobKind
import com.jarvisblue.core.model.PcState
import com.jarvisblue.core.model.TaskStatus
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.JarvisScaffold
import com.jarvisblue.core.ui.components.MetricChip
import com.jarvisblue.core.ui.components.NoticeBanner
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.AmberWarn
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent
import com.jarvisblue.core.ui.theme.GreenOk
import com.jarvisblue.core.ui.theme.RedCritical

// --------------------------------------------------------------------- tasks

@Composable
fun TasksRoute(
    modifier: Modifier = Modifier,
    viewModel: TasksViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    TasksScreen(
        state = state,
        onCommandChange = viewModel::setCommand,
        onCreate = viewModel::createTask,
        onRun = viewModel::run,
        onCancel = viewModel::cancel,
        onDelete = viewModel::delete,
        modifier = modifier,
    )
}

@Composable
fun TasksScreen(
    state: TasksUiState,
    onCommandChange: (String) -> Unit,
    onCreate: () -> Unit,
    onRun: (com.jarvisblue.core.model.AutomationTask) -> Unit,
    onCancel: (com.jarvisblue.core.model.AutomationTask) -> Unit,
    onDelete: (com.jarvisblue.core.model.AutomationTask) -> Unit,
    modifier: Modifier = Modifier,
) {
    JarvisScaffold(
        title = "Tasks",
        subtitle = state.statusLine,
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            GlowCard(
                title = "New task",
                subtitle = "Rules are matched deterministically — the AI never decides what runs",
                accent = BlueCore,
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = state.command,
                        onValueChange = onCommandChange,
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("e.g. organize my downloaded PDF files") },
                        shape = RoundedCornerShape(12.dp),
                    )
                    state.detectedIntent?.let { intent ->
                        NoticeBanner(
                            "Matched rule: ${intent.type.name} (${(intent.confidence * 100).toInt()}% confidence). " +
                                "This mapping is executed through the same permission and risk gate as a chat request.",
                            accent = CyanAccent,
                        )
                    }
                    Button(onClick = onCreate, enabled = state.command.isNotBlank()) { Text("Queue task") }
                }
            }

            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(state.tasks, key = { it.id }) { task ->
                    GlowCard(
                        title = task.title,
                        subtitle = "${task.trigger.name} · ${task.status.name}",
                        accent = when (task.status) {
                            TaskStatus.SUCCEEDED -> GreenOk
                            TaskStatus.FAILED, TaskStatus.CANCELLED -> RedCritical
                            TaskStatus.RUNNING -> CyanAccent
                            else -> BlueCore
                        },
                        trailing = {
                            TextButton(onClick = { onDelete(task) }) { Text("Delete") }
                        },
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(task.goal, style = MaterialTheme.typography.bodyMedium)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = { onRun(task) }) { Text("Run now") }
                                OutlinedButton(onClick = { onCancel(task) }) { Text("Cancel") }
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

// ------------------------------------------------------------------- windows

@Composable
fun WindowsRoute(
    modifier: Modifier = Modifier,
    viewModel: WindowsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    WindowsScreen(
        state = state,
        onHostChange = viewModel::setHost,
        onPortChange = viewModel::setPort,
        onSecretChange = viewModel::setSecret,
        onPair = viewModel::pair,
        onUnpair = viewModel::unpair,
        onRefresh = viewModel::refresh,
        onSubmitJob = viewModel::submitJob,
        onCancelJob = viewModel::cancelJob,
        modifier = modifier,
    )
}

@Composable
fun WindowsScreen(
    state: WindowsUiState,
    onHostChange: (String) -> Unit,
    onPortChange: (String) -> Unit,
    onSecretChange: (String) -> Unit,
    onPair: () -> Unit,
    onUnpair: () -> Unit,
    onRefresh: () -> Unit,
    onSubmitJob: (String, BridgeJobKind) -> Unit,
    onCancelJob: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var jobTitle by remember { mutableStateOf("Render job") }
    var jobKind by remember { mutableStateOf(BridgeJobKind.AFTER_EFFECTS_RENDER) }

    JarvisScaffold(
        title = "JARVIS Remote",
        subtitle = state.statusLine,
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            NoticeBanner(
                "Your Windows PC is the AI brain. This phone is only its remote: " +
                    "check status, request jobs and cancel jobs. PC actions need approval on Windows.",
                accent = BlueCore,
            )
            if (state.peer == null) {
                GlowCard(title = "Connect to Windows JARVIS", accent = AmberWarn) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        NoticeBanner(
                            "Start the HTTPS Mobile Bridge on your Windows JARVIS PC. " +
                                "Connect via a trusted private network or HTTPS tunnel. " +
                                "Do not publish the control port on the internet.",
                            accent = AmberWarn,
                        )
                        OutlinedTextField(
                            value = state.hostInput,
                            onValueChange = onHostChange,
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("HTTPS Windows host or private network address") },
                            singleLine = true,
                            shape = RoundedCornerShape(12.dp),
                        )
                        OutlinedTextField(
                            value = state.portInput,
                            onValueChange = onPortChange,
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Port") },
                            singleLine = true,
                            shape = RoundedCornerShape(12.dp),
                        )
                        OutlinedTextField(
                            value = state.secretInput,
                            onValueChange = onSecretChange,
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Pairing secret (32+ characters)") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            shape = RoundedCornerShape(12.dp),
                        )
                        Button(
                            onClick = onPair,
                            enabled = state.hostInput.isNotBlank() && state.secretInput.length >= 32,
                        ) { Text("Pair") }
                    }
                }
            } else {
                GlowCard(
                    title = state.peer.displayName,
                    subtitle = "${state.peer.host}:${state.peer.port}",
                    accent = when (state.status?.state) {
                        PcState.ONLINE -> GreenOk
                        PcState.OFFLINE -> RedCritical
                        else -> AmberWarn
                    },
                    trailing = {
                        Row {
                            TextButton(onClick = onRefresh) { Text("Refresh") }
                            TextButton(onClick = onUnpair) { Text("Unpair") }
                        }
                    },
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricChip("State", state.status?.state?.name ?: "unknown")
                        MetricChip("Running", "${state.status?.runningJobs ?: 0}")
                        MetricChip("Queued", "${state.status?.queuedJobs ?: 0}")
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MetricChip("CPU", "${state.status?.cpuPercent?.toInt() ?: "?"}%")
                        MetricChip("RAM", "${state.status?.memoryPercent?.toInt() ?: "?"}%")
                        MetricChip("Disk free", "${state.status?.diskFreeGb ?: "?"} GB")
                    }
                }

                GlowCard(title = "Queue a job", accent = BlueCore) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = jobTitle,
                            onValueChange = { jobTitle = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Job title") },
                            shape = RoundedCornerShape(12.dp),
                        )
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            BridgeJobKind.entries.forEach { kind ->
                                FilterChip(
                                    selected = jobKind == kind,
                                    onClick = { jobKind = kind },
                                    label = {
                                        Text(
                                            kind.name.replace('_', ' '),
                                            style = MaterialTheme.typography.labelSmall,
                                        )
                                    },
                                )
                            }
                        }
                        Button(onClick = { onSubmitJob(jobTitle, jobKind) }) { Text("Submit job") }
                    }
                }

                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(state.jobs, key = { it.id }) { job ->
                        GlowCard(
                            title = job.title,
                            subtitle = "${job.kind.name} · ${job.state.name}",
                            accent = when (job.state) {
                                com.jarvisblue.core.model.BridgeJobState.SUCCEEDED -> GreenOk
                                com.jarvisblue.core.model.BridgeJobState.FAILED -> RedCritical
                                com.jarvisblue.core.model.BridgeJobState.RUNNING -> CyanAccent
                                else -> BlueCore
                            },
                        ) {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(
                                    text = "Progress ${(job.progress * 100).toInt()}%",
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                                job.logPreview.take(5).forEach { line ->
                                    Text(
                                        text = line,
                                        style = MaterialTheme.typography.labelSmall
                                            .copy(fontFamily = FontFamily.Monospace),
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                OutlinedButton(onClick = { onCancelJob(job.id) }) { Text("Cancel job") }
                            }
                        }
                    }
                }
            }
            state.error?.let { NoticeBanner(it, accent = RedCritical) }
            Spacer(Modifier.height(16.dp))
        }
    }
}
