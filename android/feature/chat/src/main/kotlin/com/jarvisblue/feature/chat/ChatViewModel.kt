package com.jarvisblue.feature.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.ai.AiRouter
import com.jarvisblue.core.ai.LanguageDetector
import com.jarvisblue.core.database.ConversationRepository
import com.jarvisblue.core.database.MemoryRepository
import com.jarvisblue.core.model.ChatMessage
import com.jarvisblue.core.model.Conversation
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.MessageRole
import com.jarvisblue.core.model.MessageStatus
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.tools.AgentEvent
import com.jarvisblue.core.tools.AssistantAgent
import com.jarvisblue.core.tools.ConfirmationCoordinator
import com.jarvisblue.core.tools.ConfirmationRequest
import com.jarvisblue.core.tools.ToolContext
import com.jarvisblue.core.tools.ToolExecutor
import com.jarvisblue.core.tools.ToolRegistry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

data class ChatUiState(
    val conversationId: String = "",
    val messages: List<ChatMessage> = emptyList(),
    val conversations: List<Conversation> = emptyList(),
    val draft: String = "",
    val isThinking: Boolean = false,
    val statusLine: String = "Ready",
    val detectedLanguage: Language? = null,
    val providerId: ProviderId? = null,
    val modelId: String? = null,
    val availableProviders: List<ProviderId> = ProviderId.entries.toList(),
    val pendingConfirmation: ConfirmationRequest? = null,
    val error: String? = null,
    val lastToolSummary: String? = null,
)

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val conversationRepository: ConversationRepository,
    private val memoryRepository: MemoryRepository,
    router: AiRouter,
    toolRegistry: ToolRegistry,
    toolExecutor: ToolExecutor,
    toolContext: ToolContext,
    private val confirmationCoordinator: ConfirmationCoordinator,
) : ViewModel() {

    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    private val agent = AssistantAgent(
        router = router,
        registry = toolRegistry,
        executor = toolExecutor,
        memoryRepository = memoryRepository,
        confirmationGate = confirmationCoordinator,
        toolContext = toolContext,
    )

    init {
        viewModelScope.launch {
            val conversation = conversationRepository.ensureConversation(
                id = DEFAULT_CONVERSATION_ID,
                title = "Main conversation",
            )
            _state.value = _state.value.copy(
                conversationId = conversation.id,
                messages = conversationRepository.recentMessages(conversation.id, 50),
            )
        }
        viewModelScope.launch {
            conversationRepository.observeConversations().collect { list ->
                _state.value = _state.value.copy(conversations = list)
            }
        }
        viewModelScope.launch {
            confirmationCoordinator.pending.collect { pending ->
                _state.value = _state.value.copy(pendingConfirmation = pending?.request)
            }
        }
    }

    fun updateDraft(text: String) {
        _state.value = _state.value.copy(
            draft = text,
            detectedLanguage = if (text.isBlank()) null else LanguageDetector.detect(text),
        )
    }

    fun selectProvider(providerId: ProviderId) {
        _state.value = _state.value.copy(providerId = providerId)
    }

    fun send() {
        val text = _state.value.draft.trim()
        if (text.isEmpty() || _state.value.isThinking) return
        _state.value = _state.value.copy(
            draft = "",
            isThinking = true,
            statusLine = "Thinking…",
            error = null,
        )

        viewModelScope.launch {
            val conversationId = _state.value.conversationId
            val userMessage = ChatMessage(
                id = UUID.randomUUID().toString(),
                role = MessageRole.USER,
                content = text,
                createdAtEpochMs = System.currentTimeMillis(),
                status = MessageStatus.COMPLETE,
                language = LanguageDetector.detect(text),
            )
            conversationRepository.appendMessage(conversationId, userMessage)
            _state.value = _state.value.copy(
                messages = _state.value.messages + userMessage,
                detectedLanguage = userMessage.language,
            )

            try {
                val reply = agent.run(
                    userText = text,
                    // AssistantAgent appends userText; avoid duplicate user prompt.
                    history = _state.value.messages.dropLast(1),
                    language = userMessage.language,
                    preferredProvider = _state.value.providerId,
                    onEvent = ::handleEvent,
                )
                conversationRepository.appendMessage(conversationId, reply)
                _state.value = _state.value.copy(
                    messages = _state.value.messages + reply,
                    providerId = runCatching { ProviderId.valueOf(reply.providerId ?: "") }.getOrNull(),
                    modelId = reply.modelId,
                    isThinking = false,
                    statusLine = "Ready",
                    lastToolSummary = reply.toolCalls.lastOrNull()?.resultSummary,
                )
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    isThinking = false,
                    statusLine = "Failed",
                    error = t.message ?: "The request failed",
                )
            }
        }
    }

    fun respondToConfirmation(approved: Boolean) {
        confirmationCoordinator.submit(approved)
        _state.value = _state.value.copy(pendingConfirmation = null)
    }

    fun newConversation() {
        viewModelScope.launch {
            val id = UUID.randomUUID().toString()
            conversationRepository.ensureConversation(id, "Conversation ${_state.value.conversations.size + 1}")
            _state.value = _state.value.copy(conversationId = id, messages = emptyList())
        }
    }

    fun openConversation(conversation: Conversation) {
        viewModelScope.launch {
            _state.value = _state.value.copy(
                conversationId = conversation.id,
                messages = conversationRepository.recentMessages(conversation.id, 50),
            )
        }
    }

    fun deleteConversation(conversation: Conversation) {
        viewModelScope.launch {
            conversationRepository.deleteConversation(conversation.id)
        }
    }

    private fun handleEvent(event: AgentEvent) {
        when (event) {
            is AgentEvent.Thinking -> _state.value = _state.value.copy(statusLine = event.detail)
            is AgentEvent.ToolRequested ->
                _state.value = _state.value.copy(statusLine = "Running ${event.toolName}…")
            is AgentEvent.ToolCompleted ->
                _state.value = _state.value.copy(
                    statusLine = if (event.success) "Tool finished" else "Tool failed",
                    lastToolSummary = event.summary,
                )
            is AgentEvent.ConfirmationNeeded ->
                _state.value = _state.value.copy(pendingConfirmation = event.request)
            is AgentEvent.Notice -> _state.value = _state.value.copy(error = event.text)
        }
    }

    companion object {
        const val DEFAULT_CONVERSATION_ID = "conversation-main"
    }
}
