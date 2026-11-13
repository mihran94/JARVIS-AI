package com.jarvisblue.core.tools

import android.content.Context
import com.jarvisblue.core.common.AuditSink
import com.jarvisblue.core.security.EmergencyStop
import com.jarvisblue.core.security.PermissionGrantStore
import java.io.File

/**
 * Builds the runtime [ToolContext] from the app's security components.
 *
 * The context deliberately exposes *read-only views* of the permission state so
 * a tool handler cannot widen its own permissions: it can check what is granted
 * but only the [PermissionGrantStore] itself can change it.
 */
fun buildToolContext(
    appContext: Context,
    audit: AuditSink,
    grantStore: PermissionGrantStore,
    emergencyStop: EmergencyStop,
    confirmationGate: ConfirmationGate,
    workspaceRoot: File,
): ToolContext = ToolContext(
    appContext = appContext,
    audit = audit,
    grantedPermissions = { grantStore.grantedPermissions().map { it.id }.toSet() },
    isToolEnabled = { toolName -> grantStore.isToolGranted(toolName) },
    emergencyStopEngaged = { emergencyStop.engaged.value },
    requestConfirmation = { request -> confirmationGate.request(request) },
    workspaceRoot = workspaceRoot,
)
