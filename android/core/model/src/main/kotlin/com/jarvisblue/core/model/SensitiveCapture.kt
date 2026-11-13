package com.jarvisblue.core.model

/**
 * The sensitive captures that need an explicit, revocable consent.
 *
 * A grant in Android is not enough for these: the user has to say yes in the
 * app as well, and the app has to be able to take that yes back. Every
 * capture below is denied until the user grants it, and the grant is checked
 * again at the moment of the capture, so a revocation takes effect at once.
 *
 * The ids are stored in the encrypted grant file, so they must not change.
 */
enum class SensitiveCapture(
    val id: String,
    val label: String,
    val description: String,
    val permission: Permission,
) {
    MICROPHONE(
        "microphone.capture", "Microphone capture",
        "Listen for the wake phrase and for spoken commands. The microphone indicator " +
            "stays on for as long as JARVIS listens.",
        Permission.MICROPHONE,
    ),
    SCREEN_READING(
        "accessibility.screen", "Screen reading",
        "Read the visible text of the screen so that a command you gave can be " +
            "matched against what is on screen. No gestures are performed.",
        Permission.ACCESSIBILITY,
    ),
    NOTIFICATION_CONTENT(
        "notifications.content", "Notification content",
        "Read and keep the title and the text of notifications that other apps post.",
        Permission.NOTIFICATIONS_READ,
    ),
    BACKGROUND_SERVICE(
        "background.service", "Background service",
        "Keep reminders and scheduled work running while the app is closed.",
        Permission.BACKGROUND_SERVICE,
    ),
}

/**
 * What the user allowed.
 *
 * The empty set is the safe default: nothing is captured until the user says
 * otherwise.
 */
data class CaptureConsent(val allowed: Set<SensitiveCapture> = emptySet()) {

    /** Whether one capture is allowed. */
    fun allows(capture: SensitiveCapture): Boolean = capture in allowed

    /** Whether any of the captures is allowed. */
    fun allowsAny(captures: Iterable<SensitiveCapture>): Boolean = captures.any { it in allowed }

    /** The captures that are not allowed. */
    fun denied(captures: Iterable<SensitiveCapture> = SensitiveCapture.entries): List<SensitiveCapture> =
        captures.filterNot { it in allowed }

    companion object {
        /** Nothing is allowed. */
        val NONE = CaptureConsent(emptySet())
    }
}
