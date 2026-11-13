package com.jarvisblue.core.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.ui.theme.BlueBright
import com.jarvisblue.core.ui.theme.BlueCore
import kotlin.math.abs
import kotlin.math.sin

/**
 * Reactive voice waveform.
 *
 * @param amplitudes normalised 0..1 amplitudes, newest last. When the list is
 *        empty an idle breathing waveform is drawn instead.
 */
@Composable
fun VoiceWaveform(
    amplitudes: List<Float>,
    modifier: Modifier = Modifier,
    barCount: Int = 48,
    active: Boolean = true,
    accent: Color = BlueCore,
) {
    val transition = rememberInfiniteTransition(label = "wave")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 6.28318f,
        animationSpec = infiniteRepeatable(tween(1600, easing = LinearEasing), RepeatMode.Restart),
        label = "phase",
    )

    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(64.dp),
    ) {
        val barWidth = size.width / (barCount * 1.6f)
        val gap = (size.width - barWidth * barCount) / (barCount - 1).coerceAtLeast(1)
        val centerY = size.height / 2f

        for (i in 0 until barCount) {
            val sourceIndex = amplitudes.size - barCount + i
            val raw = if (sourceIndex in amplitudes.indices) amplitudes[sourceIndex] else 0f
            val idle = (abs(sin(phase + i * 0.35f)) * 0.22f).toFloat()
            val amplitude = if (active) kotlin.math.max(raw, idle) else idle
            val barHeight = (size.height * 0.92f * amplitude.coerceIn(0.02f, 1f))
            val x = i * (barWidth + gap)
            drawRoundRect(
                brush = Brush.verticalGradient(
                    listOf(BlueBright.copy(alpha = 0.95f), accent.copy(alpha = 0.45f)),
                ),
                topLeft = androidx.compose.ui.geometry.Offset(x, centerY - barHeight / 2f),
                size = androidx.compose.ui.geometry.Size(barWidth, barHeight),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(barWidth / 2f, barWidth / 2f),
            )
        }
    }
}
