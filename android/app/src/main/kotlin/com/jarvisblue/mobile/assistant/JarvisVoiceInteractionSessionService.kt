package com.jarvisblue.mobile.assistant

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService

/**
 * Provides the assistant session UI.
 *
 * The session hands control to the main activity, which renders the assistant
 * surface (orb, waveform, quick actions). Using [VoiceInteractionSession.startAssistantActivity]
 * means the activity is launched through the system assistant flow, so the
 * assistant gesture behaves the way the user expects on every OEM build.
 */
class JarvisVoiceInteractionSessionService : VoiceInteractionSessionService() {

    override fun onNewSession(args: Bundle?): VoiceInteractionSession =
        JarvisVoiceInteractionSession(this)
}

class JarvisVoiceInteractionSession(
    context: Context,
) : VoiceInteractionSession(context) {

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        startAssistantActivity(
            Intent(context, com.jarvisblue.mobile.MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                putExtra(EXTRA_FROM_ASSISTANT, true)
            },
            args ?: Bundle(),
        )
    }

    override fun onBackPressed() {
        finish()
    }

    companion object {
        const val EXTRA_FROM_ASSISTANT = "com.jarvisblue.mobile.FROM_ASSISTANT"
    }
}
