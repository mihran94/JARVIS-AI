package com.jarvisblue.core.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.compose.material3.MaterialTheme as MaterialThemeAlias

private val JarvisDarkScheme = darkColorScheme(
    primary = BlueCore,
    onPrimary = VoidBlack,
    primaryContainer = PanelBlue,
    onPrimaryContainer = BlueGlow,
    secondary = CyanAccent,
    onSecondary = VoidBlack,
    tertiary = VioletAccent,
    onTertiary = VoidBlack,
    background = VoidBlack,
    onBackground = TextPrimaryDark,
    surface = PanelBlack,
    onSurface = TextPrimaryDark,
    surfaceVariant = PanelElevated,
    onSurfaceVariant = TextSecondaryDark,
    outline = HairlineBlue,
    outlineVariant = HairlineBlue,
    error = RedCritical,
    onError = VoidBlack,
)

private val JarvisLightScheme = lightColorScheme(
    primary = BlueDeep,
    onPrimary = Color.White,
    primaryContainer = SurfaceLightAlt,
    onPrimaryContainer = BlueDeep,
    secondary = BlueCore,
    onSecondary = Color.White,
    tertiary = VioletAccent,
    onTertiary = Color.White,
    background = PaperBlue,
    onBackground = TextPrimaryLight,
    surface = SurfaceLight,
    onSurface = TextPrimaryLight,
    surfaceVariant = SurfaceLightAlt,
    onSurfaceVariant = TextSecondaryLight,
    outline = HairlineLight,
    outlineVariant = HairlineLight,
    error = RedCritical,
    onError = Color.White,
)

@Composable
fun JarvisBlueTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val scheme = if (darkTheme) JarvisDarkScheme else JarvisLightScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window ?: return@SideEffect
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !darkTheme
        }
    }
    MaterialThemeAlias(
        colorScheme = scheme,
        typography = JarvisTypography,
        content = content,
    )
}

/** Extra semantic colours that Material's scheme does not cover. */
object JarvisPalette {
    val success: Color @Composable get() = GreenOk
    val warning: Color @Composable get() = AmberWarn
    val danger: Color @Composable get() = RedCritical
    val glow: Color @Composable get() = BlueGlow
    val hairline: Color @Composable get() = MaterialTheme.colorScheme.outline
}
