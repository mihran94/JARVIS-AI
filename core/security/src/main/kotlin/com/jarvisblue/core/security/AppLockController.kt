package com.jarvisblue.core.security

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * App-lock and session-expiry state.
 *
 * After [sessionTimeoutMinutes] of inactivity the app locks again and every
 * privileged operation requires fresh biometric confirmation.
 */
class AppLockController(private val context: Context) {

    private val prefs get() = context.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE)

    private val _locked = MutableStateFlow(false)
    val locked: StateFlow<Boolean> = _locked.asStateFlow()

    private val _sessionExpiryEpochMs = MutableStateFlow(Long.MAX_VALUE)
    val sessionExpiryEpochMs: StateFlow<Long> = _sessionExpiryEpochMs.asStateFlow()

    var appLockEnabled: Boolean
        get() = prefs.getBoolean(KEY_LOCK_ENABLED, false)
        set(value) = prefs.edit { putBoolean(KEY_LOCK_ENABLED, value) }

    var biometricRequiredForTools: Boolean
        get() = prefs.getBoolean(KEY_BIO_TOOLS, true)
        set(value) = prefs.edit { putBoolean(KEY_BIO_TOOLS, value) }

    var sessionTimeoutMinutes: Int
        get() = prefs.getInt(KEY_SESSION_TIMEOUT, 15)
        set(value) = prefs.edit { putInt(KEY_SESSION_TIMEOUT, value.coerceIn(1, 240)) }

    fun unlock(validForMinutes: Int = sessionTimeoutMinutes) {
        _locked.value = false
        _sessionExpiryEpochMs.value = System.currentTimeMillis() + validForMinutes * 60_000L
    }

    fun lock() {
        _locked.value = true
        _sessionExpiryEpochMs.value = 0L
    }

    /** Returns true when the session has timed out and the app must be unlocked again. */
    fun refreshSession(): Boolean {
        if (appLockEnabled && !_locked.value && System.currentTimeMillis() > _sessionExpiryEpochMs.value) {
            lock()
        }
        return !_locked.value
    }

    companion object {
        const val FILE_NAME = "jarvis_blue_app_lock"
        const val KEY_LOCK_ENABLED = "lock_enabled"
        const val KEY_BIO_TOOLS = "bio_tools"
        const val KEY_SESSION_TIMEOUT = "session_timeout_minutes"
    }
}
