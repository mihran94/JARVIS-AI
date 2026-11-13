package com.jarvisblue.mobile.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assistant
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Code
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.security.EmergencyStop
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.JarvisOrb
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent
import com.jarvisblue.core.ui.theme.RedCritical
import com.jarvisblue.feature.assistant.AssistantRoute
import com.jarvisblue.feature.chat.ChatRoute
import com.jarvisblue.feature.command.MemoryRoute
import com.jarvisblue.feature.command.PermissionsRoute
import com.jarvisblue.feature.command.SettingsRoute
import com.jarvisblue.feature.command.TasksRoute
import com.jarvisblue.feature.command.WindowsRoute
import com.jarvisblue.feature.studio.StudioRoute
import dagger.hilt.android.lifecycle.HiltViewModel
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject

private enum class JarvisTab(
    val label: String,
    val icon: ImageVector,
) {
    ASSISTANT("Assistant", Icons.Filled.Assistant),
    CHAT("Chat", Icons.Filled.Chat),
    STUDIO("Studio", Icons.Filled.Code),
    CONTROL("Control", Icons.Filled.Dashboard),
    SETTINGS("Settings", Icons.Filled.Settings),
}

@Composable
fun JarvisApp(
    assistantRequested: Boolean,
    onAssistantHandled: () -> Unit,
    onRequestMicrophone: () -> Unit,
    microphoneGranted: Boolean,
) {
    var tab by remember { mutableStateOf(JarvisTab.ASSISTANT) }
    val emergencyViewModel: EmergencyViewModel = hiltViewModel()
    val emergencyState by emergencyViewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(assistantRequested) {
        if (assistantRequested) {
            tab = JarvisTab.ASSISTANT
            onAssistantHandled()
        }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                JarvisTab.entries.forEach { entry ->
                    NavigationBarItem(
                        selected = tab == entry,
                        onClick = { tab = entry },
                        icon = { Icon(entry.icon, contentDescription = entry.label) },
                        label = { Text(entry.label, style = MaterialTheme.typography.labelSmall) },
                    )
                }
            }
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(
                    Brush.verticalGradient(
                        listOf(
                            MaterialTheme.colorScheme.background,
                            MaterialTheme.colorScheme.surface.copy(alpha = 0.35f),
                            MaterialTheme.colorScheme.background,
                        ),
                    ),
                ),
        ) {
            when (tab) {
                JarvisTab.ASSISTANT -> AssistantRoute(
                    onRequestMicrophone = onRequestMicrophone,
                    microphoneGranted = microphoneGranted,
                )
                JarvisTab.CHAT -> ChatRoute()
                JarvisTab.STUDIO -> StudioRoute()
                JarvisTab.CONTROL -> ControlCenterScreen()
                JarvisTab.SETTINGS -> SettingsRoute()
            }

            if (emergencyState.engaged) {
                EmergencyBanner(
                    reason = emergencyState.reason,
                    onRelease = emergencyViewModel::release,
                )
            }
        }
    }
}

@Composable
private fun EmergencyBanner(reason: String?, onRelease: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(12.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(RedCritical.copy(alpha = 0.16f))
            .padding(14.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                text = "EMERGENCY STOP ACTIVE",
                style = MaterialTheme.typography.labelLarge,
                color = RedCritical,
            )
            Text(
                text = reason ?: "All tool execution is blocked until you release the stop.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Button(onClick = onRelease) { Text("Release the stop") }
        }
    }
}

/**
 * The control centre groups the permission dashboard, the task queue, the
 * memory manager and the Windows link behind one tab bar.
 */
@Composable
private fun ControlCenterScreen() {
    var tab by remember { mutableIntStateOf(0) }
    Column(modifier = Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = tab) {
            listOf("Permissions", "Tasks", "Memory", "Windows").forEachIndexed { index, label ->
                Tab(
                    selected = tab == index,
                    onClick = { tab = index },
                    text = { Text(label, style = MaterialTheme.typography.labelSmall) },
                )
            }
        }
        when (tab) {
            0 -> PermissionsRoute()
            1 -> TasksRoute()
            2 -> MemoryRoute()
            else -> WindowsRoute()
        }
    }
}

/**
 * Shown when the app lock is enabled and the session has expired.
 */
@Composable
fun LockScreen(
    onUnlock: () -> Unit,
    onUseBiometrics: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        JarvisOrb(size = 160.dp, active = false)
        Text(
            text = "JARVIS BLUE is locked",
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 20.dp),
        )
        Text(
            text = "Confirm your identity to continue. Nothing runs while the app is locked.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
        )
        Button(onClick = onUseBiometrics) { Text("Unlock with biometrics") }
        androidx.compose.material3.TextButton(onClick = onUnlock) { Text("Continue without biometrics") }
    }
}

@HiltViewModel
class EmergencyViewModel @Inject constructor(
    private val emergencyStop: EmergencyStop,
) : ViewModel() {

    data class EmergencyState(val engaged: Boolean = false, val reason: String? = null)

    private val _state = MutableStateFlow(EmergencyState())
    val state: StateFlow<EmergencyState> = _state.asStateFlow()

    init {
        _state.value = EmergencyState(emergencyStop.engaged.value, emergencyStop.reason())
    }

    fun release() {
        emergencyStop.release()
        _state.value = EmergencyState(false, null)
    }
}
