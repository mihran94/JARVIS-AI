package com.jarvisblue.mobile.assistant

import android.app.Notification
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.SensitiveCapture
import com.jarvisblue.core.security.SensitiveCaptureConsent
import com.jarvisblue.core.voice.SpeechRecognizerController
import com.jarvisblue.core.voice.WakePhraseMatcher
import com.jarvisblue.core.voice.WakeWordEngine
import com.jarvisblue.mobile.JarvisApplication
import com.jarvisblue.mobile.R
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Foreground service that listens for the wake phrase.
 *
 * Android constraints that are honoured here:
 *  - A microphone foreground service must post a visible, ongoing notification
 *    and Android shows the system microphone indicator for as long as it runs.
 *  - On Android 14+ (API 34) a microphone foreground service may only be
 *    started while the app is visible. Starting it from the background throws
 *    ForegroundServiceStartNotAllowedException, which this service catches and
 *    reports instead of crashing.
 */
@AndroidEntryPoint
class WakeWordService : Service() {

    @Inject lateinit var recognizer: SpeechRecognizerController

    @Inject lateinit var wakeWordEngine: WakeWordEngine

    @Inject lateinit var matcher: WakePhraseMatcher

    /** The consent that decides whether the microphone may be used. */
    @Inject lateinit var consent: SensitiveCaptureConsent

    // SpeechRecognizer methods must run on Android's main thread.
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var listenJob: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startForegroundSafely()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopListening()
            stopSelf()
            return START_NOT_STICKY
        }
        // Fail closed: the microphone is only used when the user granted the
        // consent in the app. Android's runtime permission on its own is not
        // enough.
        if (!consent.allows(SensitiveCapture.MICROPHONE)) {
            stopListening()
            stopSelf()
            return START_NOT_STICKY
        }
        startListening()
        return START_STICKY
    }

    private fun startForegroundSafely() {
        val notification = buildNotification()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
                )
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (t: Throwable) {
            // Android 14+ refuses to start a microphone FGS from the background.
            // The UI surfaces this instead of the app crashing.
            stopSelf()
        }
    }

    private fun startListening() {
        if (listenJob?.isActive == true) return
        listenJob = scope.launch {
            while (true) {
                try {
                    var failed = false
                    recognizer.listen(
                        Language.ENGLISH,
                        SpeechRecognizerController.EngineMode.ON_DEVICE_ONLY,
                    ).collect { recognition ->
                        if (recognition.error != null) {
                            failed = true
                            return@collect
                        }
                        if (!recognition.isFinal) return@collect
                        val match = matcher.match(recognition.transcript, Language.ENGLISH)
                        if (match.isWakeCall) {
                            launchAssistant()
                        }
                    }
                    if (failed) {
                        stopSelf()
                        break
                    }
                    kotlinx.coroutines.delay(500)
                } catch (cancelled: kotlinx.coroutines.CancellationException) {
                    throw cancelled
                } catch (t: Throwable) {
                    kotlinx.coroutines.delay(1500)
                }
            }
        }
    }

    private fun launchAssistant() {
        val intent = Intent(this, com.jarvisblue.mobile.MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra(JarvisVoiceInteractionSession.EXTRA_FROM_ASSISTANT, true)
        }
        runCatching { startActivity(intent) }
            // Android may block an activity launch from a background service.
    }

    private fun stopListening() {
        listenJob?.cancel()
        listenJob = null
    }

    private fun buildNotification(): Notification =
        NotificationCompat.Builder(this, JarvisApplication.WAKE_CHANNEL_ID)
            .setContentTitle("JARVIS BLUE is listening")
            .setContentText("Say “Hey Jarvis Blue”. Tap to stop.")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

    override fun onDestroy() {
        stopListening()
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.jarvisblue.mobile.wake.STOP"
        private const val NOTIFICATION_ID = 1099

        fun start(context: Context) {
            val intent = Intent(context, WakeWordService::class.java)
            try {
                context.startForegroundService(intent)
            } catch (t: Throwable) {
                // Background start is not permitted on Android 14+; the caller
                // shows a message asking the user to open the app first.
            }
        }

        fun stop(context: Context) {
            context.startService(
                Intent(context, WakeWordService::class.java).apply { action = ACTION_STOP },
            )
        }
    }
}
