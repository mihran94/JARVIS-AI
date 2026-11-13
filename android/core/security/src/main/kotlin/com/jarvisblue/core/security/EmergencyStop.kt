package com.jarvisblue.core.security

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Global kill switch.
 *
 * When engaged, no tool may execute, no remote command may be dispatched and no
 * background service may start. The switch is sticky — it survives restarts until
 * the user explicitly releases it, so a panic button always works.
 */
class EmergencyStop(private val context: Context) {

    private val prefs get() = context.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE)

    private val _engaged = MutableStateFlow(prefs.getBoolean(KEY_ENGAGED, false))
    val engaged: StateFlow<Boolean> = _engaged.asStateFlow()

    fun engage(reason: String = "User pressed the emergency stop") {
        prefs.edit { putBoolean(KEY_ENGAGED, true).putString(KEY_REASON, reason) }
        _engaged.value = true
    }

    fun release() {
        prefs.edit { putBoolean(KEY_ENGAGED, false).remove(KEY_REASON) }
        _engaged.value = false
    }

    fun reason(): String? = prefs.getString(KEY_REASON, null)

    companion object {
        const val FILE_NAME = "jarvis_blue_emergency"
        const val KEY_ENGAGED = "engaged"
        const val KEY_REASON = "reason"
    }
}
