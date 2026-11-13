package com.jarvisblue.core.security

import android.content.Context
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * Biometric confirmation used for app unlock and for sensitive actions.
 *
 * Every prompt is bound to a live [FragmentActivity] and is cancelled if the
 * user navigates away — there is no silent fallback path that bypasses the check.
 */
class BiometricGate(private val context: Context) {

    fun availability(): BiometricAvailability {
        val manager = BiometricManager.from(context)
        val canAuth = manager.canAuthenticate(BIOMETRIC_STRONG)
        return when (canAuth) {
            BiometricManager.BIOMETRIC_SUCCESS -> BiometricAvailability.AVAILABLE
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> BiometricAvailability.NOT_ENROLLED
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE -> BiometricAvailability.NO_HARDWARE
            BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE -> BiometricAvailability.HARDWARE_UNAVAILABLE
            else -> BiometricAvailability.UNAVAILABLE
        }
    }

    suspend fun authenticate(
        activity: FragmentActivity,
        title: String,
        subtitle: String,
        description: String = "",
    ): BiometricResult = suspendCancellableCoroutine { continuation ->
        val executor = ContextCompat.getMainExecutor(activity)
        val prompt = BiometricPrompt(
            activity,
            executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    if (continuation.isActive) continuation.resume(BiometricResult.Success)
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    if (continuation.isActive) {
                        continuation.resume(BiometricResult.Failed(errorCode, errString.toString()))
                    }
                }

                override fun onAuthenticationFailed() {
                    // A single failed fingerprint attempt is not terminal; the prompt stays open.
                }
            },
        )

        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setDescription(description)
            .setNegativeButtonText("Cancel")
            .setAllowedAuthenticators(BIOMETRIC_STRONG)
            .setConfirmationRequired(false)
            .build()

        continuation.invokeOnCancellation { prompt.cancelAuthentication() }
        prompt.authenticate(info)
    }

    enum class BiometricAvailability {
        AVAILABLE, NOT_ENROLLED, NO_HARDWARE, HARDWARE_UNAVAILABLE, UNAVAILABLE,
    }

    sealed interface BiometricResult {
        data object Success : BiometricResult
        data class Failed(val errorCode: Int, val message: String) : BiometricResult
    }

    companion object {
        private const val BIOMETRIC_STRONG = BiometricManager.Authenticators.BIOMETRIC_STRONG
    }
}
