package com.jarvisblue.mobile.services

import com.jarvisblue.core.tools.NotificationSnapshot
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * In-memory cache of the notifications the listener has seen.
 *
 * The listener only runs after the user grants notification access in Android
 * settings; until then this stays empty and the tools report that honestly.
 */
@Singleton
class NotificationStore @Inject constructor() {

    private val _snapshots = MutableStateFlow<List<NotificationSnapshot>>(emptyList())
    val snapshots: StateFlow<List<NotificationSnapshot>> = _snapshots.asStateFlow()

    fun record(snapshot: NotificationSnapshot) {
        _snapshots.value = (listOf(snapshot) + _snapshots.value).take(MAX_ITEMS)
    }

    fun recent(limit: Int): List<NotificationSnapshot> = _snapshots.value.take(limit)

    fun clear() {
        _snapshots.value = emptyList()
    }

    companion object {
        const val MAX_ITEMS = 200
    }
}
