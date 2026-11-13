package com.jarvisblue.mobile.assistant

import android.os.Bundle
import android.service.voice.VoiceInteractionService

/**
 * Registers JARVIS BLUE as a system voice assistant.
 *
 * The user must select this app in
 * Settings → Apps → Default apps → Assistant app (or by long-pressing the
 * assistant gesture and choosing JARVIS BLUE). Until then Android will not
 * route the assistant gesture or the "assist" hotword here.
 *
 * The recognition metadata lives in res/xml/recognition_service.xml and points
 * at [JarvisRecognitionService].
 */
class JarvisVoiceInteractionService : VoiceInteractionService() {

    override fun onReady() {
        super.onReady()
    }

    /**
     * Called before the assistant UI is shown. The session service supplies the
     * UI; this hook exists so the app can record that the gesture was used.
     */
    override fun onPrepareToShowSession(args: Bundle, showFlags: Int) {
        super.onPrepareToShowSession(args, showFlags)
    }
}
