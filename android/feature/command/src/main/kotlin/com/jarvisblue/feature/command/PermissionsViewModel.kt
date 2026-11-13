package com.jarvisblue.feature.command

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jarvisblue.core.model.Permission
import com.jarvisblue.core.model.SensitiveCapture
import com.jarvisblue.core.security.AppLockController
import com.jarvisblue.core.security.EmergencyStop
import com.jarvisblue.core.security.PermissionGrantStore
import com.jarvisblue.core.security.SensitiveCaptureConsent
import com.jarvisblue.core.tools.ToolRegistry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class PermissionRow(
    val permission: Permission,
    val granted: Boolean,
)

/**
 * One sensitive capture and whether the user allowed it.
 *
 * These are the switches that decide what the services may read. They are
 * shown separately from the capability buckets, because they answer a
 * different question: not "may this tool run" but "may the assistant read
 * this".
 */
data class CaptureRow(
    val capture: SensitiveCapture,
    val allowed: Boolean,
)

data class ToolRow(
    val name: String,
    val displayName: String,
    val category: String,
    val riskLevel: String,
    val enabled: Boolean,
    val requiresConfirmation: Boolean,
    val requiredPermissions: List<String>,
)

data class PermissionsUiState(
    val permissions: List<PermissionRow> = emptyList(),
    val captures: List<CaptureRow> = emptyList(),
    val tools: List<ToolRow> = emptyList(),
    val emergencyStopEngaged: Boolean = false,
    val emergencyReason: String? = null,
    val appLockEnabled: Boolean = false,
    val biometricRequired: Boolean = true,
    val sessionTimeoutMinutes: Int = 15,
    val statusLine: String = "Ready",
)

@HiltViewModel
class PermissionsViewModel @Inject constructor(
    private val grantStore: PermissionGrantStore,
    private val captureConsent: SensitiveCaptureConsent,
    private val emergencyStop: EmergencyStop,
    private val appLock: AppLockController,
    private val toolRegistry: ToolRegistry,
) : ViewModel() {

    private val _state = MutableStateFlow(PermissionsUiState())
    val state: StateFlow<PermissionsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            grantStore.grants.collect { refresh() }
        }
        viewModelScope.launch {
            captureConsent.consent.collect { consent ->
                _state.value = _state.value.copy(
                    captures = SensitiveCapture.entries.map { CaptureRow(it, consent.allows(it)) },
                )
            }
        }
        viewModelScope.launch {
            emergencyStop.engaged.collect { engaged ->
                _state.value = _state.value.copy(
                    emergencyStopEngaged = engaged,
                    emergencyReason = emergencyStop.reason(),
                )
            }
        }
    }

    private fun refresh() {
        val granted = grantStore.grantedPermissions()
        _state.value = _state.value.copy(
            permissions = Permission.entries.map { permission ->
                PermissionRow(permission, permission in granted)
            },
            tools = toolRegistry.all().map { registered ->
                ToolRow(
                    name = registered.spec.name,
                    displayName = registered.spec.displayName,
                    category = registered.spec.category.name,
                    riskLevel = registered.spec.riskLevel.name,
                    enabled = grantStore.isToolGranted(registered.spec.name),
                    requiresConfirmation = registered.spec.requiresConfirmation,
                    requiredPermissions = registered.spec.requiredPermissions.map { it.label },
                )
            },
            appLockEnabled = appLock.appLockEnabled,
            biometricRequired = appLock.biometricRequiredForTools,
            sessionTimeoutMinutes = appLock.sessionTimeoutMinutes,
        )
    }

    fun setPermission(permission: Permission, enabled: Boolean) {
        viewModelScope.launch {
            grantStore.grant(permission, enabled)
            _state.value = _state.value.copy(statusLine = "${permission.label} ${if (enabled) "granted" else "revoked"}")
        }
    }

    /**
     * Allow or take back one sensitive capture.
     *
     * The change is written straight away, so the services see it at their
     * next check and stop at once.
     */
    fun setCapture(capture: SensitiveCapture, allowed: Boolean) {
        viewModelScope.launch {
            captureConsent.setAllowed(capture, allowed)
            _state.value = _state.value.copy(
                statusLine = "${capture.label} ${if (allowed) "allowed" else "revoked"}",
            )
        }
    }

    fun setToolEnabled(name: String, enabled: Boolean) {
        viewModelScope.launch {
            grantStore.grantTool(name, enabled)
            _state.value = _state.value.copy(statusLine = "$name ${if (enabled) "enabled" else "disabled"}")
        }
    }

    fun engageEmergencyStop() {
        emergencyStop.engage()
        _state.value = _state.value.copy(statusLine = "Emergency stop engaged")
    }

    fun releaseEmergencyStop() {
        emergencyStop.release()
        _state.value = _state.value.copy(statusLine = "Emergency stop released")
    }

    fun setAppLockEnabled(enabled: Boolean) {
        appLock.appLockEnabled = enabled
        refresh()
    }

    fun setBiometricRequired(enabled: Boolean) {
        appLock.biometricRequiredForTools = enabled
        refresh()
    }

    fun setSessionTimeout(minutes: Int) {
        appLock.sessionTimeoutMinutes = minutes
        refresh()
    }

    fun revokeEverything() {
        viewModelScope.launch {
            grantStore.revokeAll()
            _state.value = _state.value.copy(statusLine = "All in-app grants revoked")
        }
    }
}
