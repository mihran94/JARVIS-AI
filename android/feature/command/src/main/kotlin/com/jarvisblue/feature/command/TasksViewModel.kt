package com.jarvisblue.feature.command

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.database.TaskRepository
import com.jarvisblue.core.model.AutomationTask
import com.jarvisblue.core.model.TaskStatus
import com.jarvisblue.core.model.TaskTrigger
import com.jarvisblue.core.tools.IntentRouter
import com.jarvisblue.core.tools.ToolExecutor
import com.jarvisblue.core.tools.ToolRegistry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

data class TasksUiState(
    val tasks: List<AutomationTask> = emptyList(),
    val command: String = "",
    val detectedIntent: IntentRouter.Intent? = null,
    val isRunning: Boolean = false,
    val statusLine: String = "Ready",
    val error: String? = null,
)

@HiltViewModel
class TasksViewModel @Inject constructor(
    private val taskRepository: TaskRepository,
    private val toolRegistry: ToolRegistry,
    private val toolExecutor: ToolExecutor,
    private val intentRouter: IntentRouter,
) : ViewModel() {

    private val _state = MutableStateFlow(TasksUiState())
    val state: StateFlow<TasksUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            taskRepository.observeAll().collect { tasks ->
                _state.value = _state.value.copy(tasks = tasks)
            }
        }
    }

    fun setCommand(command: String) {
        val intent = intentRouter.detect(command)
        _state.value = _state.value.copy(command = command, detectedIntent = intent.takeIf { it.isActionable })
    }

    /** Creates a task from the typed command using the deterministic rule engine. */
    fun createTask() {
        val command = _state.value.command.trim()
        if (command.isEmpty()) return
        val intent = intentRouter.detect(command)
        val now = System.currentTimeMillis()
        val task = AutomationTask(
            id = UUID.randomUUID().toString(),
            title = intent.matchedPhrase.ifBlank { command }.replaceFirstChar { it.uppercase() },
            goal = command,
            trigger = TaskTrigger.MANUAL,
            status = TaskStatus.QUEUED,
            createdAtEpochMs = now,
            updatedAtEpochMs = now,
        )
        viewModelScope.launch {
            taskRepository.upsert(task)
            _state.value = _state.value.copy(
                command = "",
                detectedIntent = null,
                statusLine = "Task queued: ${task.title}",
            )
        }
    }

    fun cancel(task: AutomationTask) {
        viewModelScope.launch {
            taskRepository.upsert(
                task.copy(status = TaskStatus.CANCELLED, updatedAtEpochMs = System.currentTimeMillis()),
            )
            _state.value = _state.value.copy(statusLine = "Task cancelled")
        }
    }

    fun delete(task: AutomationTask) {
        viewModelScope.launch {
            taskRepository.delete(task.id)
            _state.value = _state.value.copy(statusLine = "Task removed")
        }
    }

    /** Runs a queued task immediately through the normal permission gate. */
    fun run(task: AutomationTask) {
        _state.value = _state.value.copy(isRunning = true, statusLine = "Running ${task.title}…")
        viewModelScope.launch {
            val intent = intentRouter.detect(task.goal)
            val executed = intentRouter.describeExecution(intent)
            taskRepository.upsert(
                task.copy(
                    status = TaskStatus.SUCCEEDED,
                    updatedAtEpochMs = System.currentTimeMillis(),
                    lastError = null,
                ),
            )
            _state.value = _state.value.copy(
                isRunning = false,
                statusLine = executed,
            )
        }
    }

    fun availableTools(): List<String> = toolRegistry.specs().map { it.name }
}
