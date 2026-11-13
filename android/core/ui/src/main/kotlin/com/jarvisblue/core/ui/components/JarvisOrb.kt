package com.jarvisblue.core.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.ui.theme.BlueBright
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.CyanAccent

/**
 * The animated assistant orb.
 *
 * The animation is a single infinite transition driving three phases; it is
 * intentionally cheap (no per-frame allocations, no shaders) so it stays
 * battery-friendly on mid-range devices.
 */
@Composable
fun JarvisOrb(
    modifier: Modifier = Modifier,
    size: Dp = 180.dp,
    active: Boolean = true,
    accent: Color = BlueCore,
) {
    val transition = rememberInfiniteTransition(label = "orb")
    val pulse by transition.animateFloat(
        initialValue = 0.86f,
        targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(2600), RepeatMode.Reverse),
        label = "pulse",
    )
    val spin by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(9000), RepeatMode.Restart),
        label = "spin",
    )
    val breathe by transition.animateFloat(
        initialValue = 0.25f,
        targetValue = 0.65f,
        animationSpec = infiniteRepeatable(tween(1800), RepeatMode.Reverse),
        label = "breathe",
    )

    Box(modifier = modifier.size(size)) {
        Canvas(modifier = Modifier.size(size)) {
            val radius = this.size.minDimension / 2f
            val center = Offset(this.size.width / 2f, this.size.height / 2f)
            val scale = if (active) pulse else 0.92f

            // Outer glow
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(accent.copy(alpha = 0.30f * breathe), Color.Transparent),
                    center = center,
                    radius = radius * scale * 1.25f,
                ),
                radius = radius * scale * 1.25f,
                center = center,
            )

            // Core sphere
            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(
                        BlueBright.copy(alpha = 0.55f),
                        accent.copy(alpha = 0.28f),
                        Color.Transparent,
                    ),
                    center = center - Offset(radius * 0.18f, radius * 0.22f),
                    radius = radius * scale,
                ),
                radius = radius * scale * 0.62f,
                center = center,
            )

            // Rotating latitude ring
            drawCircle(
                color = CyanAccent.copy(alpha = 0.45f),
                radius = radius * 0.82f,
                center = center,
                style = Stroke(width = 1.5f),
            )

            // Meridian arcs
            val arcCount = 3
            for (i in 0 until arcCount) {
                val angle = Math.toRadians((spin + i * 120.0)).toFloat()
                val x = center.x + kotlin.math.cos(angle) * radius * 0.34f
                val y = center.y + kotlin.math.sin(angle) * radius * 0.34f
                drawCircle(
                    color = BlueBright.copy(alpha = 0.75f),
                    radius = 2.6f,
                    center = Offset(x, y),
                )
            }

            // Outer rim
            drawCircle(
                color = accent.copy(alpha = 0.85f),
                radius = radius * 0.95f,
                center = center,
                style = Stroke(width = 2f),
            )
        }
    }
}
