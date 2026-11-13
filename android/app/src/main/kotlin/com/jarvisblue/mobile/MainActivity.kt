package com.jarvisblue.mobile

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.fragment.app.FragmentActivity
import com.jarvisblue.core.security.AppLockController
import com.jarvisblue.core.security.BiometricGate
import com.jarvisblue.core.ui.theme.JarvisBlueTheme
import com.jarvisblue.mobile.navigation.JarvisApp
import com.jarvisblue.mobile.navigation.LockScreen
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Windows remote only. No local assistant session or microphone request. */
@AndroidEntryPoint
class MainActivity : FragmentActivity() {
    @Inject lateinit var appLock: AppLockController

    // App-lock expiry updates the screen instead of recursively recreating the Activity.
    private var screenLocked by mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        screenLocked = appLock.appLockEnabled
        setContent {
            val scope = rememberCoroutineScope()
            JarvisBlueTheme {
                if (screenLocked) {
                    LockScreen(
                        onUnlock = {
                            appLock.unlock()
                            screenLocked = false
                        },
                        onUseBiometrics = {
                            val gate = BiometricGate(this@MainActivity)
                            scope.launch {
                                val result = gate.authenticate(
                                    activity = this@MainActivity,
                                    title = "Unlock JARVIS Remote",
                                    subtitle = "Confirm it is you to control Windows",
                                )
                                if (result is BiometricGate.BiometricResult.Success) {
                                    appLock.unlock()
                                    screenLocked = false
                                }
                            }
                        },
                    )
                } else {
                    JarvisApp()
                }
            }
        }
    }

    // Kept only for legacy source compilation; no assistant intent is registered.
    companion object {
        const val EXTRA_FROM_ASSISTANT = "com.jarvisblue.mobile.FROM_ASSISTANT"
    }

    override fun onResume() {
        super.onResume()
        if (appLock.appLockEnabled && !appLock.refreshSession()) {
            screenLocked = true
        } else if (!appLock.appLockEnabled) {
            screenLocked = false
        }
    }
}
