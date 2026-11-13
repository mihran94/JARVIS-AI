package com.jarvisblue.core.tools

import android.content.Context
import com.jarvisblue.core.common.AuditSink
import com.jarvisblue.core.security.EmergencyStop
import com.jarvisblue.core.security.PermissionGrantStore
import javax.inject.Inject
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Singleton

/**
 * Produces the runtime [ToolContext] used for every tool invocation.
 *
 * Keeping this in one place means every tool — whether invoked from the chat,
 * the dashboard, a scheduled routine or the Windows bridge — goes through the
 * same permission, risk and audit path.
 */
@Singleton
class ToolContextProvider @Inject constructor(
    @ApplicationContext private val context: Context,
    private val audit: AuditSink,
    private val grantStore: PermissionGrantStore,
    private val emergencyStop: EmergencyStop,
    private val confirmationCoordinator: ConfirmationCoordinator,
) {

    fun create(workspaceRoot: File): ToolContext = ToolContext(
        appContext = context,
        audit = audit,
        grantedPermissions = { grantStore.grantedPermissions().map { it.id }.toSet() },
        isToolEnabled = { toolName -> grantStore.isToolGranted(toolName) },
        emergencyStopEngaged = { emergencyStop.engaged.value },
        requestConfirmation = { request -> confirmationCoordinator.request(request) },
        workspaceRoot = workspaceRoot,
    )
}
