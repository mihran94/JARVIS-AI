package com.jarvisblue.feature.command

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.database.MemoryRepository
import com.jarvisblue.core.model.MemoryItem
import com.jarvisblue.core.model.MemoryKind
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class MemoryUiState(
    val items: List<MemoryItem> = emptyList(),
    val query: String = "",
    val draftTitle: String = "",
    val draftBody: String = "",
    val draftKind: MemoryKind = MemoryKind.FACT,
    val statusLine: String = "Ready",
)

@HiltViewModel
class MemoryViewModel @Inject constructor(
    private val repository: MemoryRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(MemoryUiState())
    val state: StateFlow<MemoryUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            repository.observeAll().collect { items ->
                _state.value = _state.value.copy(items = items)
            }
        }
    }

    fun setQuery(query: String) {
        _state.value = _state.value.copy(query = query)
    }

    fun setTitle(value: String) {
        _state.value = _state.value.copy(draftTitle = value)
    }

    fun setBody(value: String) {
        _state.value = _state.value.copy(draftBody = value)
    }

    fun setKind(kind: MemoryKind) {
        _state.value = _state.value.copy(draftKind = kind)
    }

    fun save() {
        val title = _state.value.draftTitle.trim()
        val body = _state.value.draftBody.trim()
        if (title.isEmpty() || body.isEmpty()) {
            _state.value = _state.value.copy(statusLine = "A title and a body are required")
            return
        }
        viewModelScope.launch {
            repository.remember(kind = _state.value.draftKind, title = title, body = body, source = "user")
            _state.value = _state.value.copy(
                draftTitle = "",
                draftBody = "",
                statusLine = "Saved to encrypted memory",
            )
        }
    }

    fun delete(item: MemoryItem) {
        viewModelScope.launch {
            repository.delete(item.id)
            _state.value = _state.value.copy(statusLine = "Deleted '${item.title}'")
        }
    }

    fun clearAll() {
        viewModelScope.launch {
            repository.clearAll()
            _state.value = _state.value.copy(statusLine = "All memories deleted")
        }
    }
}
