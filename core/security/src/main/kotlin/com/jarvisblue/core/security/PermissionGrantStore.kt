package com.jarvisblue.core.security

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import com.jarvisblue.core.model.Permission

/**
 * Per-capability, per-tool grants.
 *
 * Grants are *not* implied by the Android runtime permission: recording audio,
 * for example, needs both the runtime permission and an explicit in-app grant.
 * Every grant is user-visible in the Permissions dashboard and can be revoked.
 */
class PermissionGrantStore(
    private val context: Context,
    private val cipherBox: CipherBox = CipherBox(),
) {

    private val prefs get() = context.getSharedPreferences(FILE_NAME, Context.MODE_PRIVATE)

    private val _grants = MutableStateFlow<Map<String, Boolean>>(emptyMap())
    val grants: StateFlow<Map<String, Boolean>> = _grants.asStateFlow()

    init {
        _grants.value = load()
    }

    private fun load(): Map<String, Boolean> = runCatching {
        val raw = prefs.getString(KEY_GRANTS, null) ?: return emptyMap()
        cipherBox.decryptToString(raw)
            .split(';')
            .filter { it.isNotBlank() }
            .mapNotNull { entry ->
                val parts = entry.split('=')
                if (parts.size == 2) parts[0] to (parts[1] == "1") else null
            }
            .toMap()
    }.getOrDefault(emptyMap())

    private fun persist(map: Map<String, Boolean>) {
        runCatching {
            val encoded = map.entries.joinToString(";") { "${it.key}=${if (it.value) "1" else "0"}" }
            prefs.edit { putString(KEY_GRANTS, cipherBox.encrypt(encoded)) }
        }
    }

    suspend fun grant(permission: Permission, enabled: Boolean) = withContext(Dispatchers.IO) {
        val updated = _grants.value.toMutableMap()
        updated[permission.id] = enabled
        persist(updated)
        _grants.value = updated
    }

    suspend fun grantTool(toolName: String, enabled: Boolean) = withContext(Dispatchers.IO) {
        val updated = _grants.value.toMutableMap()
        updated[toolKey(toolName)] = enabled
        persist(updated)
        _grants.value = updated
    }

    fun isGranted(permission: Permission): Boolean = _grants.value[permission.id] == true

    fun isToolGranted(toolName: String): Boolean {
        val map = _grants.value
        // A tool is enabled unless explicitly switched off; the *permission* buckets
        // are always required and default to denied until the user grants them.
        return map[toolKey(toolName)] ?: true
    }

    fun grantedPermissions(): Set<Permission> =
        _grants.value.filterValues { it }.keys
            .mapNotNull { id -> Permission.entries.firstOrNull { it.id == id } }
            .toSet()

    suspend fun revokeAll() = withContext(Dispatchers.IO) {
        prefs.edit { clear() }
        _grants.value = emptyMap()
    }

    private fun toolKey(toolName: String) = "tool.$toolName"

    companion object {
        const val FILE_NAME = "jarvis_blue_grants"
        const val KEY_GRANTS = "grants"
    }
}
