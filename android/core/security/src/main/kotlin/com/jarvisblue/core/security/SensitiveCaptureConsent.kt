package com.jarvisblue.core.security

import com.jarvisblue.core.model.CaptureConsent
import com.jarvisblue.core.model.SensitiveCapture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The consent the user gave for the sensitive captures.
 *
 * The consent is stored in the same encrypted grant file as the other
 * permissions, so it survives a restart and can be revoked from the
 * Permissions dashboard.
 *
 * Two rules matter here:
 *
 *  - the default is **denied**. A fresh install captures nothing;
 *  - the check happens **at the moment of the capture**, not when the service
 *    was created, so a revocation takes effect immediately and the data that
 *    was already captured is dropped.
 */
@Singleton
class SensitiveCaptureConsent @Inject constructor(
    private val grantStore: PermissionGrantStore,
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    /** The consent as it stands, updated whenever a grant changes. */
    val consent: StateFlow<CaptureConsent> = grantStore.grants
        .map { grants ->
            CaptureConsent(
                SensitiveCapture.entries
                    .filter { grants[it.permission.id] == true }
                    .toSet(),
            )
        }
        .stateIn(scope, SharingStarted.Eagerly, CaptureConsent.NONE)

    /**
     * Whether one capture is allowed right now.
     *
     * This is the check every sensitive call site uses.
     */
    fun allows(capture: SensitiveCapture): Boolean = grantStore.isGranted(capture.permission)

    /** Grant or take back one capture. */
    suspend fun setAllowed(capture: SensitiveCapture, allowed: Boolean) {
        grantStore.grant(capture.permission, allowed)
    }

    /** Take back every capture and every other grant. */
    suspend fun revokeAll() {
        grantStore.revokeAll()
    }
}
