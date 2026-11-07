package com.jarvisblue.core.tools

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Single, app-scoped confirmation channel.
 *
 * A tool that needs approval suspends here; the UI observes [pending], shows the
 * request, and calls [submit] with the user's decision. Only one request can be
 * in flight at a time, which matches the "one thing at a time" nature of a
 * personal assistant and keeps the audit trail unambiguous.
 */
class ConfirmationCoordinator : ConfirmationGate {

    data class Pending(
        val request: ConfirmationRequest,
        private val decision: CompletableDeferred<Boolean>,
    ) {
        suspend fun await(): Boolean = decision.await()
        fun resolve(approved: Boolean) = decision.complete(approved)
    }

    private val _pending = MutableStateFlow<Pending?>(null)
    val pending: StateFlow<Pending?> = _pending.asStateFlow()

    override suspend fun request(request: ConfirmationRequest): Boolean {
        val decision = CompletableDeferred<Boolean>()
        val pending = Pending(request, decision)
        _pending.value = pending
        return try {
            decision.await()
        } finally {
            if (_pending.value === pending) _pending.value = null
        }
    }

    /** Called by the UI when the user approves or declines. */
    fun submit(approved: Boolean) {
        _pending.value?.resolve(approved)
        _pending.value = null
    }

    /** Cancels any in-flight confirmation (used by the emergency stop). */
    fun cancelAll() {
        _pending.value?.resolve(false)
        _pending.value = null
    }
}
