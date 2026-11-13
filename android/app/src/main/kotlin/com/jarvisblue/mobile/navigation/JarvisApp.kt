package com.jarvisblue.mobile.navigation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.ui.components.JarvisOrb
import com.jarvisblue.feature.command.WindowsRoute

/**
 * The phone is a remote control for the *Windows* JARVIS process.
 *
 * It has no local chat provider, execution agent or microphone UI. Windows
 * remains responsible for AI, coding, tool approvals and the emergency stop.
 */
@Composable
fun JarvisApp() {
    WindowsRoute()
}

/** Existing opt-in app-lock/biometric gate remains active for remote access. */
@Composable
fun LockScreen(
    onUnlock: () -> Unit,
    onUseBiometrics: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize().padding(28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        JarvisOrb(size = 160.dp, active = false)
        Text(
            text = "JARVIS Remote is locked",
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 20.dp),
        )
        Text(
            text = "Unlock to control your paired Windows computer. No tools run on this phone.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
        )
        Button(onClick = onUseBiometrics) { Text("Unlock with biometrics") }
        androidx.compose.material3.TextButton(onClick = onUnlock) {
            Text("Continue without biometrics")
        }
    }
}
