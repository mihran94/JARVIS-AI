package com.jarvisblue.mobile.services

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityEvent
import com.jarvisblue.core.model.SensitiveCapture
import com.jarvisblue.core.security.SensitiveCaptureConsent
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Narrow, user-activated UI automation.
 *
 * Deliberate constraints:
 *  - The service performs **no gestures** (canPerformGestures="false").
 *  - It never performs an action on its own; it only records the visible text
 *    of the current window so that a command the user issued can be matched
 *    against it.
 *  - It is disabled by default and the user must enable it in Android settings.
 *  - The user is always told, via the system's own accessibility status bar,
 *    that this service is running.
 *  - Nothing is read unless the user granted the "Screen reading" consent in
 *    the app. The grant is checked again for every event, so taking it back
 *    stops the reading at once and drops what was read before.
 *
 * It is *not* a general-purpose UI-automation agent and it cannot be used to
 * bypass any app's own security model.
 */
@AndroidEntryPoint
class JarvisAccessibilityService : AccessibilityService() {

    /** The consent that decides whether the screen may be read. */
    @Inject lateinit var consent: SensitiveCaptureConsent

    companion object {
        @Volatile
        var lastVisibleText: String = ""

        @Volatile
        var lastPackageName: String = ""

        private val listeners = mutableListOf<(String) -> Unit>()

        fun addListener(listener: (String) -> Unit) {
            synchronized(listeners) { listeners.add(listener) }
        }

        fun removeListener(listener: (String) -> Unit) {
            synchronized(listeners) { listeners.remove(listener) }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        serviceInfo = (serviceInfo ?: AccessibilityServiceInfo()).apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = flags or AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
            notificationTimeout = 200
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Fail closed: without the consent nothing is read, and whatever was
        // read before the consent was taken back is dropped.
        if (!consent.allows(SensitiveCapture.SCREEN_READING)) {
            forgetCapturedText()
            return
        }
        val source = event?.source ?: return
        val text = source.text?.toString().orEmpty()
        if (text.isBlank()) return
        lastVisibleText = text.take(4000)
        lastPackageName = event.packageName?.toString().orEmpty()
        synchronized(listeners) {
            listeners.forEach { it.invoke(lastVisibleText) }
        }
    }

    override fun onDestroy() {
        forgetCapturedText()
        super.onDestroy()
    }

    override fun onInterrupt() {
        forgetCapturedText()
    }

    /** Drop the text that was read. */
    private fun forgetCapturedText() {
        lastVisibleText = ""
        lastPackageName = ""
    }
}
