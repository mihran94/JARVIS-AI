package com.jarvisblue.core.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.jarvisblue.core.ui.theme.BlueCore
import com.jarvisblue.core.ui.theme.RedCritical

/**
 * The command-centre scaffold: gradient backdrop, a title bar and a slot for
 * the emergency stop so it is always reachable from every screen.
 */
@Composable
fun JarvisScaffold(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    emergencyStopActive: Boolean = false,
    onEmergencyStop: (() -> Unit)? = null,
    actions: @Composable (() -> Unit)? = null,
    content: @Composable (PaddingValues) -> Unit,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        Brush.verticalGradient(
                            listOf(
                                MaterialTheme.colorScheme.surface,
                                MaterialTheme.colorScheme.background,
                            ),
                        ),
                    )
                    .padding(horizontal = 18.dp, vertical = 14.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = title,
                            style = MaterialTheme.typography.headlineMedium,
                            color = MaterialTheme.colorScheme.onBackground,
                        )
                        if (subtitle != null) {
                            Text(
                                text = subtitle,
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    actions?.invoke()
                    if (onEmergencyStop != null) {
                        Spacer(modifier = Modifier.size(6.dp))
                        IconButton(onClick = onEmergencyStop) {
                            Icon(
                                imageVector = Icons.Filled.Shield,
                                contentDescription = "Emergency stop",
                                tint = if (emergencyStopActive) RedCritical else MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.size(22.dp),
                            )
                        }
                    }
                }
            }
        },
        content = content,
    )
}

/** A thin luminous divider used between panels. */
@Composable
fun HologramDivider(modifier: Modifier = Modifier, accent: Color = BlueCore) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(1.dp)
            .background(
                Brush.horizontalGradient(
                    listOf(Color.Transparent, accent.copy(alpha = 0.55f), Color.Transparent),
                ),
            ),
    )
}

/** A compact legend explaining the availability markers used across the app. */
@Composable
fun AvailabilityLegend(modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        StatusPill(text = "Working", color = BlueCore)
        StatusPill(text = "Partial", color = com.jarvisblue.core.ui.theme.AmberWarn)
        StatusPill(text = "Unavailable", color = RedCritical)
    }
}

/** Rounded container used for inline notices. */
@Composable
fun NoticeBanner(
    text: String,
    modifier: Modifier = Modifier,
    accent: Color = BlueCore,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(accent.copy(alpha = 0.12f))
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}
