package com.jarvisblue.feature.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvisblue.core.model.ChatMessage
import com.jarvisblue.core.model.MessageRole
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.ui.components.GlowCard
import com.jarvisblue.core.ui.components.JarvisScaffold
import com.jarvisblue.core.ui.components.StatusPill
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent
import com.jarvisblue.core.ui.theme.GreenOk
import com.jarvisblue.core.ui.theme.RedCritical

@Composable
fun ChatRoute(
    modifier: Modifier = Modifier,
    viewModel: ChatViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    ChatScreen(
        state = state,
        onDraftChange = viewModel::updateDraft,
        onSend = viewModel::send,
        onSelectProvider = viewModel::selectProvider,
        onConfirm = { approved -> viewModel.respondToConfirmation(approved) },
        modifier = modifier,
    )
}

@Composable
fun ChatScreen(
    state: ChatUiState,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onSelectProvider: (ProviderId) -> Unit,
    onConfirm: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()

    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) {
            listState.animateScrollToItem(state.messages.lastIndex)
        }
    }

    JarvisScaffold(
        title = "JARVIS BLUE",
        subtitle = state.statusLine,
        modifier = modifier,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            ProviderBar(
                providers = state.availableProviders,
                selected = state.providerId,
                model = state.modelId,
                onSelect = onSelectProvider,
            )

            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(state.messages, key = { it.id }) { message ->
                    MessageBubble(message)
                }
                if (state.isThinking) {
                    item { ThinkingBubble() }
                }
                state.error?.let { message ->
                    item {
                        GlowCard(accent = RedCritical) {
                            Text(
                                text = message,
                                style = MaterialTheme.typography.bodyMedium,
                                color = RedCritical,
                            )
                        }
                    }
                }
            }

            Composer(
                draft = state.draft,
                enabled = !state.isThinking,
                onDraftChange = onDraftChange,
                onSend = onSend,
            )
        }
    }

    state.pendingConfirmation?.let { request ->
        AlertDialog(
            onDismissRequest = { onConfirm(false) },
            title = { Text(request.title) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(request.detail, style = MaterialTheme.typography.bodyMedium)
                    request.effects.forEach { effect ->
                        Text("• $effect", style = MaterialTheme.typography.bodyMedium)
                    }
                    StatusPill(text = "Risk ${request.riskLevel}", color = RedCritical)
                }
            },
            confirmButton = {
                TextButton(onClick = { onConfirm(true) }) { Text("Approve once") }
            },
            dismissButton = {
                TextButton(onClick = { onConfirm(false) }) { Text("Decline") }
            },
        )
    }
}

@Composable
private fun ProviderBar(
    providers: List<ProviderId>,
    selected: ProviderId?,
    model: String?,
    onSelect: (ProviderId) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        providers.forEach { provider ->
            FilterChip(
                selected = provider == selected,
                onClick = { onSelect(provider) },
                label = { Text(provider.displayName, style = MaterialTheme.typography.labelSmall) },
            )
        }
        if (model != null) {
            StatusPill(text = model, color = CyanAccent)
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isUser = message.role == MessageRole.USER
    val alignment = if (isUser) Alignment.End else Alignment.Start
    val bubbleColor = if (isUser) {
        MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)
    } else {
        MaterialTheme.colorScheme.surface
    }

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = alignment,
    ) {
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(16.dp))
                .background(
                    if (isUser) {
                        Brush.horizontalGradient(
                            listOf(
                                MaterialTheme.colorScheme.primary.copy(alpha = 0.26f),
                                MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                            ),
                        )
                    } else {
                        Brush.horizontalGradient(
                            listOf(
                                MaterialTheme.colorScheme.surface,
                                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
                            ),
                        )
                    },
                )
                .padding(horizontal = 14.dp, vertical = 11.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = message.content,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                if (message.toolCalls.isNotEmpty()) {
                    message.toolCalls.forEach { call ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            StatusPill(
                                text = call.toolName,
                                color = if (call.status == "COMPLETED") GreenOk else RedCritical,
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                text = call.resultSummary.orEmpty().take(120),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
                if (message.providerId != null) {
                    Text(
                        text = "${message.providerId} · ${message.modelId ?: "—"}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun ThinkingBubble() {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.padding(vertical = 6.dp),
    ) {
        CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = BlueCore)
        Text(
            text = "JARVIS is working…",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Composer(
    draft: String,
    enabled: Boolean,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 3.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = draft,
                onValueChange = onDraftChange,
                modifier = Modifier.weight(1f),
                placeholder = { Text("Ask JARVIS…", style = MaterialTheme.typography.bodyMedium) },
                maxLines = 4,
                shape = RoundedCornerShape(14.dp),
            )
            IconButton(
                onClick = onSend,
                enabled = enabled && draft.isNotBlank(),
            ) {
                Icon(
                    imageVector = Icons.Filled.Send,
                    contentDescription = "Send",
                    tint = if (enabled && draft.isNotBlank()) BlueCore else MaterialTheme.colorScheme.outline,
                )
            }
        }
    }
}
