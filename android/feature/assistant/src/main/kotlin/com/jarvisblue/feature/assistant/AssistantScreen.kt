package com.jarvisblue.feature.assistant

import androidx.compose.foundation.layout.Arrangement
import android.content.Intent
import android.provider.Settings
import android.speech.tts.TextToSpeech
import androidx.core.content.ContextCompat
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.JarvisOrb
import com.jarvisblue.core.ui.components.JarvisScaffold
import com.jarvisblue.core.ui.components.NoticeBanner
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.components.VoiceWaveform
import com.jarvisblue.core.ui.theme.AmberWarn
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent
import com.jarvisblue.core.ui.theme.GreenOk
import com.jarvisblue.core.ui.theme.RedCritical

@Composable
fun AssistantRoute(
    modifier: Modifier = Modifier,
    onRequestMicrophone: () -> Unit = {},
    microphoneGranted: Boolean = false,
    viewModel: AssistantViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val appContext = LocalContext.current
    AssistantScreen(
        state = state,
        onRequestMicrophone = onRequestMicrophone,
        microphoneGranted = microphoneGranted,
        onLanguageChange = viewModel::setLanguage,
        onStartListening = viewModel::startListening,
        onStopListening = viewModel::stopListening,
        onWakeWordToggle = { enabled ->
            val service = Intent().setClassName(
                appContext.packageName, "com.jarvisblue.mobile.assistant.WakeWordService",
            )
            if (enabled && microphoneGranted && state.onDeviceAvailable) {
                runCatching { ContextCompat.startForegroundService(appContext, service) }
                    .onSuccess { viewModel.setWakeWordEnabled(true) }
                    .onFailure { viewModel.setWakeWordEnabled(false) }
            } else {
                service.action = "com.jarvisblue.mobile.wake.STOP"
                runCatching { appContext.startService(service) }
                viewModel.setWakeWordEnabled(false)
            }
        },
        onConfirm = { approved -> viewModel.respondToConfirmation(approved) },
        modifier = modifier,
    )
}

@Composable
fun AssistantScreen(
    state: AssistantUiState,
    onRequestMicrophone: () -> Unit,
    microphoneGranted: Boolean,
    onLanguageChange: (Language) -> Unit,
    onStartListening: () -> Unit,
    onStopListening: () -> Unit,
    onWakeWordToggle: (Boolean) -> Unit,
    onConfirm: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    JarvisScaffold(
        title = "Assistant",
        subtitle = state.statusLine,
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(8.dp))

            Box(contentAlignment = Alignment.Center) {
                JarvisOrb(
                    size = 190.dp,
                    active = state.isListening || state.isSpeaking,
                    accent = if (state.isListening) CyanAccent else BlueCore,
                )
            }

            Spacer(Modifier.height(4.dp))
            VoiceWaveform(
                amplitudes = state.amplitudes,
                active = state.isListening,
            )

            LazyRow(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(Language.entries.toList()) { language ->
                    FilterChip(
                        selected = state.language == language,
                        onClick = { onLanguageChange(language) },
                        label = { Text(language.nativeName, style = MaterialTheme.typography.labelSmall) },
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            Row(
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(
                    onClick = {
                        if (!microphoneGranted) {
                            onRequestMicrophone()
                        } else if (state.isListening) {
                            onStopListening()
                        } else {
                            onStartListening()
                        }
                    },
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Icon(
                        imageVector = if (state.isListening) Icons.Filled.Stop else Icons.Filled.Mic,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.size(8.dp))
                    Text(
                        when {
                            !microphoneGranted -> "Allow microphone"
                            state.isListening -> "Stop"
                            else -> "Talk"
                        },
                    )
                }
                OutlinedButton(onClick = {
                    runCatching { context.startActivity(Intent(Settings.ACTION_VOICE_INPUT_SETTINGS)) }
                        .onFailure { runCatching { context.startActivity(Intent(Settings.ACTION_SETTINGS)) } }
                }) {
                    Text("Voice settings")
                }
            }

            Spacer(Modifier.height(10.dp))

            GlowCard(
                title = "Wake word",
                subtitle = "“${state.wakePhrase}”",
                trailing = {
                    Switch(
                        checked = state.wakeWordEnabled,
                        enabled = state.onDeviceAvailable && state.recognitionAvailable && microphoneGranted,
                        onCheckedChange = onWakeWordToggle,
                    )
                },
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    NoticeBanner(
                        text = "Background wake-word listening runs in a microphone foreground " +
                            "service. Android shows a permanent microphone indicator and, on " +
                            "Android 14+, the service can only be started while the app is " +
                            "visible. It is never started without your action.",
                        accent = AmberWarn,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        StatusPill(
                            text = when {
                                !state.recognitionAvailable -> "ASR unavailable"
                                state.onDeviceRecognition -> "On-device ASR"
                                else -> "System ASR"
                            },
                            color = if (state.recognitionAvailable && state.onDeviceRecognition) GreenOk else AmberWarn,
                        )
                        StatusPill(
                            text = if (state.ttsAvailableFor.contains(state.language)) {
                                "Voice ${state.language.nativeName}"
                            } else {
                                "No ${state.language.nativeName} voice pack"
                            },
                            color = if (state.ttsAvailableFor.contains(state.language)) GreenOk else AmberWarn,
                        )
                    }
                    if (!state.onDeviceAvailable && state.recognitionAvailable) {
                        NoticeBanner(
                            text = "Push-to-talk may use a cloud speech service. " +
                                "Wake word requires an on-device recognizer.",
                            accent = AmberWarn,
                        )
                    }
                    if (!state.recognitionAvailable) {
                        NoticeBanner(
                            text = "No Android speech service detected. Install or enable a " +
                                "speech recognition service, then select it in Voice settings.",
                            accent = AmberWarn,
                        )
                    }
                    if (!state.ttsAvailableFor.contains(state.language)) {
                        OutlinedButton(onClick = {
                            runCatching { context.startActivity(Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA)) }
                                .onFailure { runCatching { context.startActivity(Intent(Settings.ACTION_SETTINGS)) } }
                        }) {
                            Text("Install ${state.language.nativeName} voice")
                        }
                    }
                }
            }

            if (state.response.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                GlowCard(title = "JARVIS response", accent = GreenOk) {
                    Text(state.response, style = MaterialTheme.typography.bodyLarge)
                }
            }

            state.error?.let { error ->
                Spacer(Modifier.height(8.dp))
                NoticeBanner(text = error, accent = RedCritical)
            }

            if (state.transcript.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                GlowCard(title = "Heard", accent = CyanAccent) {
                    Text(
                        text = state.transcript,
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurface,
                        textAlign = TextAlign.Start,
                    )
                }
            }

            Spacer(Modifier.height(16.dp))
        }
    }

    state.pendingConfirmation?.let { request ->
        AlertDialog(
            onDismissRequest = { onConfirm(false) },
            title = { Text(request.title) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(request.detail)
                    request.effects.forEach { Text("• $it") }
                }
            },
            confirmButton = { TextButton(onClick = { onConfirm(true) }) { Text("Approve once") } },
            dismissButton = { TextButton(onClick = { onConfirm(false) }) { Text("Decline") } },
        )
    }
}
