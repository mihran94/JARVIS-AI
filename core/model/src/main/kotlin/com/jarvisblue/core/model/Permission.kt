package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

/**
 * Fine-grained capability buckets. A tool declares the buckets it needs; the user
 * grants them individually from the Permissions dashboard. There is no "all access"
 * switch — grants are per bucket *and* per tool.
 */
@Serializable
enum class Permission(
    val id: String,
    val label: String,
    val description: String,
    val sensitive: Boolean,
) {
    MICROPHONE(
        "microphone", "Microphone",
        "Capture audio for speech recognition and wake-word detection.", true,
    ),
    NOTIFICATIONS_READ(
        "notifications.read", "Read notifications",
        "Read and summarise notification content posted by other apps.", true,
    ),
    NOTIFICATIONS_POST(
        "notifications.post", "Post notifications",
        "Post JARVIS BLUE notifications (reminders, alerts, job events).", false,
    ),
    CONTACTS(
        "contacts", "Contacts & calls",
        "Look up contacts and place calls. Messages always require confirmation.", true,
    ),
    FILES(
        "files", "File access",
        "Read and organise files you explicitly grant access to via the system picker.", true,
    ),
    ASSISTANT(
        "assistant", "Assistant role",
        "Appear as a voice assistant and respond to long-press / assistant gestures.", false,
    ),
    AUTOMATION(
        "automation", "Automation",
        "Run scheduled and chained routines on your behalf.", false,
    ),
    SCREEN_CAPTURE(
        "screen_capture", "Screen capture",
        "Read visible screen content after you grant a MediaProjection consent prompt.", true,
    ),
    ACCESSIBILITY(
        "accessibility", "Limited UI automation",
        "Perform a small, fixed set of UI steps you explicitly trigger. Always visible to you.", true,
    ),
    AI_NETWORK(
        "ai.network", "Cloud AI",
        "Send prompts to the cloud AI providers you configure.", false,
    ),
    REMOTE(
        "remote", "Remote control",
        "Send approved commands to your JARVIS BLUE Windows desktop.", true,
    ),
    OVERLAY(
        "overlay", "Overlay",
        "Draw the assistant overlay on top of other apps.", false,
    ),
    PACKAGE_QUERY(
        "package.query", "App inventory",
        "Read the list of installed apps so you can launch them by name.", false,
    ),
    SYSTEM_SETTINGS(
        "system_settings", "Open system settings",
        "Deep-link into Android system settings screens you select.", false,
    ),
    MEDIA_CONTROL(
        "media_control", "Media control",
        "Control media playback through the official MediaSession APIs.", false,
    ),
    DEVELOPMENT(
        "development", "Development tools",
        "Analyse, generate and review code; run checks in an isolated sandbox.", false,
    ),
    SECURITY_SCAN(
        "security_scan", "Security scanning",
        "Run defensive diagnostics against networks and files you own or are authorised for.", true,
    ),
    MEMORY_STORE(
        "memory.store", "Personal memory",
        "Persist long-term notes about you so the assistant can personalise replies.", false,
    ),
    BACKGROUND_SERVICE(
        "background.service", "Background service",
        "Keep reminders and scheduled work running while the app is closed.", true,
    ),
}
