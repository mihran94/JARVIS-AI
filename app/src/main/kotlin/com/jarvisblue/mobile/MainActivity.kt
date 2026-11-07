package com.jarvisblue.mobile

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.jarvisblue.core.security.AppLockController
import com.jarvisblue.core.security.BiometricGate
import com.jarvisblue.core.ui.theme.JarvisBlueTheme
import com.jarvisblue.mobile.navigation.JarvisApp
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * The single Compose host.
 *
 * It extends [FragmentActivity] because the biometric gate needs a fragment
 * host to attach its prompt to.
 */
@AndroidEntryPoint
class MainActivity : FragmentActivity() {

    @Inject lateinit var appLock: AppLockController

    private val microphonePermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        microphonePermissionGranted = granted
    }

    private var microphonePermissionGranted = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        microphonePermissionGranted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECORD_AUDIO,
        ) == PackageManager.PERMISSION_GRANTED

        setContent {
            val scope = rememberCoroutineScope()
            var locked by remember { mutableStateOf(appLock.appLockEnabled) }
            var assistantRequested by remember {
                mutableStateOf(intent?.getBooleanExtra(EXTRA_FROM_ASSISTANT, false) == true)
            }

            JarvisBlueTheme {
                if (locked) {
                    com.jarvisblue.mobile.navigation.LockScreen(
                        onUnlock = {
                            appLock.unlock()
                            locked = false
                        },
                        onUseBiometrics = {
                            val gate = BiometricGate(this@MainActivity)
                            scope.launch {
                                val result = gate.authenticate(
                                    activity = this@MainActivity,
                                    title = "Unlock JARVIS BLUE",
                                    subtitle = "Confirm it is you to continue",
                                )
                                if (result is BiometricGate.BiometricResult.Success) {
                                    appLock.unlock()
                                    locked = false
                                }
                            }
                        },
                    )
                } else {
                    JarvisApp(
                        assistantRequested = assistantRequested,
                        onAssistantHandled = { assistantRequested = false },
                        onRequestMicrophone = {
                            microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                        },
                        microphoneGranted = microphonePermissionGranted,
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (appLock.appLockEnabled && !appLock.refreshSession()) {
            // Session expired while the app was in the background.
            recreate()
        }
    }

    companion object {
        const val EXTRA_FROM_ASSISTANT = "com.jarvisblue.mobile.FROM_ASSISTANT"
    }
}
