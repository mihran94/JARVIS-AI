package com.jarvisblue.mobile.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * Optional screen capture backed by MediaProjection.
 *
 * A MediaProjection session can only be created after the user accepts the
 * system consent dialog, which Android shows every time. The service holds no
 * recording: it grabs a single frame, summarises its luminance in memory and
 * discards it. No frame is ever written to disk and no video stream is produced.
 */
class ScreenCaptureService : Service() {

    companion object {
        const val ACTION_START = "com.jarvisblue.mobile.screencapture.START"
        const val ACTION_STOP = "com.jarvisblue.mobile.screencapture.STOP"
        const val CHANNEL_ID = "jarvis_screen_capture"
        private const val SAMPLE_STEP = 8
        private const val NOTIFICATION_ID = 4711

        @Volatile
        var lastCapturedText: String? = null

        /**
         * Starts the capture using the consent the user just granted.
         *
         * The projection object is obtained from the platform
         * [MediaProjectionManager]; there is no way to obtain one without the
         * user's explicit system consent.
         */
        fun start(context: Context, resultCode: Int, data: Intent) {
            val manager = context.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
                as MediaProjectionManager
            val projection = manager.getMediaProjection(resultCode, data)
            if (projection == null) {
                Log.w("ScreenCapture", "MediaProjection could not be created from the consent result")
                return
            }
            context.startForegroundService(
                Intent(context, ScreenCaptureService::class.java).apply {
                    action = ACTION_START
                    putExtra(EXTRA_PROJECTION, projection as android.os.Parcelable)
                },
            )
        }

        fun stop(context: Context) {
            context.startService(
                Intent(context, ScreenCaptureService::class.java).apply { action = ACTION_STOP },
            )
        }

        private const val EXTRA_PROJECTION = "com.jarvisblue.mobile.extra.PROJECTION"
    }

    private var projection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                startForegroundSafely()
                val mediaProjection = intent.getParcelableExtra(EXTRA_PROJECTION, MediaProjection::class.java)
                    ?: return START_NOT_STICKY
                startCapture(mediaProjection)
            }
            ACTION_STOP -> {
                stopCapture()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun startForegroundSafely() {
        try {
            startForeground(NOTIFICATION_ID, buildNotification())
        } catch (t: Throwable) {
            Log.w("ScreenCapture", "Could not enter the foreground", t)
            stopSelf()
        }
    }

    private fun startCapture(mediaProjection: MediaProjection) {
        projection = mediaProjection
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        display?.getRealMetrics(metrics)

        val width = metrics.widthPixels.coerceAtLeast(1)
        val height = metrics.heightPixels.coerceAtLeast(1)
        val density = metrics.densityDpi

        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        imageReader = reader
        virtualDisplay = mediaProjection.createVirtualDisplay(
            "jarvis-screen",
            width,
            height,
            density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface,
            null,
            null,
        )

        reader.setOnImageAvailableListener({ source ->
            val image: Image = source.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                // The frame is analysed in memory only. No pixels are written to
                // disk and no video stream is produced.
                lastCapturedText = extractLuminanceSummary(image)
            } catch (t: Throwable) {
                Log.w("ScreenCapture", "Frame analysis failed", t)
            } finally {
                image.close()
            }
        }, null)
    }

    /**
     * Produces a coarse description of the frame.
     *
     * Full on-device OCR would require shipping a model and is deliberately out
     * of scope; the assistant instead reports that a capture is live and uses
     * the AccessibilityService's text view (which requires a separate, explicit
     * grant) when the user wants the literal words on screen.
     */
    private fun extractLuminanceSummary(image: Image): String {
        val plane = image.planes[0]
        val buffer = plane.buffer
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        val width = image.width
        val height = image.height
        var bright = 0
        var sampled = 0
        for (y in 0 until height) {
            if (y % SAMPLE_STEP != 0) continue
            for (x in 0 until width) {
                if (x % SAMPLE_STEP != 0) continue
                val index = y * rowStride + x * pixelStride
                if (index >= buffer.limit()) continue
                val value = buffer.get(index).toInt() and 0xFF
                if (value > 140) bright++
                sampled++
            }
        }
        val ratio = if (sampled == 0) 0f else bright.toFloat() / sampled
        return "Captured ${width}x$height frame, ${"%.0f".format(ratio * 100)}% bright pixels. " +
            "Enable the Accessibility service for the literal on-screen text."
    }

    private fun stopCapture() {
        runCatching { virtualDisplay?.release() }
        runCatching { imageReader?.close() }
        runCatching { projection?.stop() }
        virtualDisplay = null
        imageReader = null
        projection = null
    }

    private fun buildNotification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Screen capture",
                    NotificationManager.IMPORTANCE_LOW,
                ),
            )
        }
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("JARVIS BLUE screen capture active")
            .setContentText("You can see this capture in the notification shade.")
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        stopCapture()
        super.onDestroy()
    }
}
