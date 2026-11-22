"""JARVIS PRIME — the visual system of the desktop experience.

WHAT THIS IS
    The application had two dark stylesheets in the repository, and neither
    of them ever reached the owner's screen: `desktop/app.py` defined
    `STYLE = PERSONAL_STYLE` but never applied it to the application, so the
    shipping JARVIS rendered in the default light Qt theme. Only the tests
    set the stylesheet, which is why the premium look existed in the test
    screenshots and nowhere else.

    This module is the visual system of the application: one stylesheet for
    the dark experience, one for the light one, and the code that applies the
    chosen one to the running application.

THE VISUAL LANGUAGE
    * Deep midnight and graphite grounds.
    * Surfaces that read as translucent glass: a soft translucent fill with a
      one-pixel luminous edge.
    * Rounded corners and a low, wide shadow — depth, not decoration.
    * An electric blue and icy cyan accent for the assistant and for
      anything that is live.
    * Refined typography: Segoe UI Variable where Windows has it, Segoe UI
      everywhere else.
    * The same hover, focus, disabled and pressed state for every control.

WHAT IT IS NOT
    This is styling only. It adds no permission, no listener, no background
    process and no new capability. Every control it styles already existed.
"""
from __future__ import annotations

#: The themes the owner can choose in Settings.
THEME_NAMES = ('Dark', 'Light')

#: The theme used when the owner has not chosen one.
DEFAULT_THEME = 'Dark'

#: The key the chosen theme is remembered under.
THEME_KEY = 'appearance_theme'

#: The interface font stack. Segoe UI Variable ships with Windows 11.
#:
#: A font that carries no Tamil glyphs is not enough on its own: the Latin
#: characters are then measured with a font that has no Tamil, the Tamil
#: characters are drawn from another font, and the two are laid out on top
#: of each other. A font that carries Tamil has to be named here, so the
#: Tamil the owner types and the Tamil the owner reads are laid out with
#: the same measurement. Nirmala UI is the Tamil font of Windows.
FONT_STACK = ("'Segoe UI Variable Display', 'Segoe UI Variable', 'Segoe UI', "
              "'Nirmala UI', 'Noto Sans Tamil', 'Latha', system-ui, sans-serif")
MONO_STACK = "'Cascadia Mono', 'Consolas', 'SF Mono', monospace"


def _lighten(color: str, amount: float) -> str:
    """A colour mixed towards white."""
    value = color.lstrip('#')
    if len(value) != 6:
        return color
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda part: int(round(part + (255 - part) * amount))
    return '#%02x%02x%02x' % (mix(red), mix(green), mix(blue))


def _darken(color: str, amount: float) -> str:
    """A colour mixed towards black."""
    value = color.lstrip('#')
    if len(value) != 6:
        return color
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda part: int(round(part * (1 - amount)))
    return '#%02x%02x%02x' % (mix(red), mix(green), mix(blue))


def _alpha(color: str, alpha: int) -> str:
    """The same colour with an alpha, in the form Qt's stylesheets honour.

    Qt ignores the alpha of `rgba()` when it paints a widget background, so
    the eight digit alpha-first form is used instead.
    """
    value = color.lstrip('#')
    if len(value) != 6:
        return color
    return '#%02x%s' % (max(0, min(255, int(alpha))), value)


def _luminance(color: str) -> float:
    """How bright a colour is, so a dark palette is told from a light one."""
    value = color.lstrip('#')
    if len(value) != 6:
        return 0.0
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def _tokens(palette) -> dict:
    """The tokens of one palette.

    The palette is the Omega's own: (background, panel, edge, ink, muted,
    cyan, gold). The premium sheet is built from it, so the palette the owner
    chose still decides the colours of the whole application.
    """
    ground, panel, edge, ink, muted, cyan, gold = palette
    dark = _luminance(ground) < 0.5
    if dark:
        return {
            'ground': ground,
            'ground_alt': _darken(ground, 0.35),
            'surface': panel,
            'glass': _alpha(_lighten(panel, 0.10), 165),
            'glass_solid': _alpha(_lighten(panel, 0.06), 205),
            'edge': _alpha(edge, 105),
            'edge_strong': _alpha(cyan, 150),
            'accent': cyan,
            'accent_deep': _darken(cyan, 0.22),
            'accent_ink': ground,
            'text': ink,
            'muted': muted,
            'dim': _darken(muted, 0.28) if dark else _lighten(muted, 0.18),
            'danger': '#ff7286' if dark else '#c2334a',
            'danger_ink': '#2a0a12' if dark else '#ffffff',
            'danger_surface': '#3a1620' if dark else '#fde8ec',
            'danger_edge': '#8c4553' if dark else '#e08c9a',
            'danger_hover': '#4d1c28' if dark else '#fbdde2',
            'selection': _alpha(cyan, 95),
        }
    return {
        'ground': ground,
        'ground_alt': _darken(ground, 0.06),
        'surface': panel,
        'glass': _alpha('#ffffff', 190),
        'glass_solid': _alpha(panel, 235),
        'edge': _alpha(edge, 95),
        'edge_strong': _alpha(cyan, 145),
        'accent': cyan,
        'accent_deep': _darken(cyan, 0.18),
        'accent_ink': '#ffffff',
        'text': ink,
        'muted': muted,
        'dim': _lighten(muted, 0.18),
        'danger': '#c2334a',
        'danger_ink': '#ffffff',
        'danger_surface': '#fde8ec',
        'danger_edge': '#e08c9a',
        'danger_hover': '#fbdde2',
        'selection': _alpha(cyan, 70),
    }


def stylesheet(palette) -> str:
    """The premium stylesheet for one palette."""
    t = _tokens(palette)
    return f"""
/* ── ground ─────────────────────────────────────────────────────────────── */
/* The generic widget rule comes first. A rule that matches the window as
   well has to follow it, because the later rule is the one that wins, and
   a transparent window would show the desktop through the whole interface. */
QWidget {{
    background: transparent;
    color: {t['text']};
    font-family: {FONT_STACK};
    font-size: 14px;
}}
QMainWindow, QDialog {{
    background: qlineargradient(x1:0, y1:0, x2:0.4, y2:1,
                stop:0 {t['ground']}, stop:1 {t['ground_alt']});
}}
QWidget#pageRoot {{
    background: qlineargradient(x1:0, y1:0, x2:0.35, y2:1,
                stop:0 {t['ground']}, stop:1 {t['ground_alt']});
}}

/* ── type ───────────────────────────────────────────────────────────────── */
QLabel#brandTitle {{
    font-family: {FONT_STACK};
    font-size: 21px;
    font-weight: 700;
    letter-spacing: 3px;
    color: {t['text']};
}}
QLabel#brandSub {{
    font-size: 11px;
    letter-spacing: 1.6px;
    color: {t['dim']};
}}
QLabel#pageTitle {{
    font-size: 27px;
    font-weight: 700;
    color: {t['text']};
}}
QLabel#pageSubtitle {{ color: {t['muted']}; font-size: 13px; }}
QLabel#systemMetrics {{
    color: {t['muted']};
    font-family: {MONO_STACK};
    font-size: 12px;
    padding: 8px 12px;
    background: {t['glass']};
    border: 1px solid {t['edge']};
    border-radius: 12px;
}}
QLabel#statusChip {{
    color: {t['accent']};
    background: {t['glass']};
    border: 1px solid {t['edge']};
    border-radius: 11px;
    padding: 5px 13px;
    font-size: 12px;
    letter-spacing: 0.6px;
}}
QLabel#hudClock {{ color: {t['muted']}; font-size: 19px; font-weight: 600; }}
QLabel#hudValue {{ color: {t['accent']}; font-size: 24px; font-weight: 700; }}

/* ── glass surfaces ─────────────────────────────────────────────────────── */
QFrame#glassPanel, QWidget#glassPanel {{
    background: {t['glass']};
    border: 1px solid {t['edge']};
    border-radius: 18px;
}}
QPlainTextEdit#transcriptCard, QTextEdit#transcriptCard {{
    background: {t['glass']};
    border: 1px solid {t['edge']};
    border-radius: 18px;
    padding: 14px 16px;
    selection-background-color: {t['selection']};
}}
QPlainTextEdit#composerCard, QTextEdit#composerCard {{
    background: {t['glass_solid']};
    border: 1px solid {t['edge']};
    border-radius: 16px;
    padding: 11px 13px;
    selection-background-color: {t['selection']};
}}
QWidget#taskCard {{
    background: {t['glass']};
    border: 1px solid {t['edge_strong']};
    border-radius: 16px;
}}
QWidget#approvalCard {{
    background: {t['danger_surface']};
    border: 1px solid {t['danger_edge']};
    border-radius: 14px;
}}

QLabel#approvalTitle {{
    color: {t['text']};
    font-weight: 700;
}}

/* ── controls ───────────────────────────────────────────────────────────── */
QPushButton {{
    background: {t['glass']};
    color: {t['text']};
    border: 1px solid {t['edge']};
    border-radius: 11px;
    padding: 8px 15px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {t['edge_strong']}; background: {t['surface']}; }}
QPushButton:pressed {{ background: {t['ground_alt']}; }}
QPushButton:focus {{ border-color: {t['accent']}; }}
QPushButton:disabled {{ color: {t['dim']}; background: {t['glass']}; border-color: {t['edge']}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {t['accent']}, stop:1 {t['accent_deep']});
    color: {t['accent_ink']};
    border: 1px solid {t['accent_deep']};
    font-weight: 700;
}}
QPushButton#primary:hover {{ border-color: {t['accent']}; }}
QPushButton#primary:disabled {{
    background: {t['glass']};
    color: {t['dim']};
    border-color: {t['edge']};
}}
QPushButton#stop {{
    background: {t['danger_surface']};
    color: {t['danger']};
    border: 1px solid {t['danger_edge']};
    font-weight: 700;
}}
QPushButton#stop:hover {{ background: {t['danger_hover']}; }}
QPushButton#quiet {{
    background: transparent;
    border: 1px solid {t['edge']};
    color: {t['muted']};
    font-weight: 500;
}}
QPushButton#quiet:hover {{ color: {t['text']}; border-color: {t['edge_strong']}; }}

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget {{
    background: {t['glass_solid']};
    color: {t['text']};
    border: 1px solid {t['edge']};
    border-radius: 11px;
    padding: 7px 10px;
    selection-background-color: {t['selection']};
    selection-color: {t['text']};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {t['accent']};
}}
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {t['dim']};
    background: {t['glass']};
}}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['edge_strong']};
    border-radius: 10px;
    padding: 4px;
    selection-background-color: {t['selection']};
}}
QCheckBox {{ color: {t['muted']}; spacing: 9px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {t['edge_strong']};
    border-radius: 5px;
    background: {t['glass_solid']};
}}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
QCheckBox:disabled {{ color: {t['dim']}; }}

QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {t['edge_strong']};
    border-radius: 5px;
    min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {t['edge_strong']};
    border-radius: 5px;
    min-width: 34px;
}}

/* ── containers ─────────────────────────────────────────────────────────── */
QListWidget {{
    background: {t['glass']};
    border: 1px solid {t['edge']};
    border-radius: 16px;
    padding: 7px;
}}
QListWidget::item {{
    padding: 11px 10px;
    margin: 2px 0;
    border-radius: 10px;
    color: {t['muted']};
}}
QListWidget::item:hover {{ background: {t['surface']}; color: {t['text']}; }}
QListWidget::item:selected {{
    background: {t['selection']};
    color: {t['text']};
}}
QGroupBox {{
    border: 1px solid {t['edge']};
    border-radius: 14px;
    margin-top: 15px;
    padding: 14px 10px 10px 10px;
    background: {t['glass']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 13px;
    padding: 0 7px;
    color: {t['muted']};
    font-weight: 600;
}}
QTabWidget::pane {{
    border: 1px solid {t['edge']};
    border-radius: 14px;
    background: {t['glass']};
}}
QTabBar::tab {{
    background: transparent;
    padding: 9px 15px;
    color: {t['muted']};
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {t['text']}; }}
QTabBar::tab:selected {{
    color: {t['accent']};
    border-bottom: 2px solid {t['accent']};
}}
QHeaderView::section {{
    background: {t['surface']};
    color: {t['muted']};
    padding: 8px;
    border: 0;
    border-bottom: 1px solid {t['edge']};
}}
QTableWidget {{ gridline-color: {t['edge']}; }}
QProgressBar {{
    background: {t['glass_solid']};
    border: 0;
    border-radius: 4px;
    max-height: 7px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {t['accent_deep']}, stop:1 {t['accent']});
    border-radius: 4px;
}}
QStatusBar {{
    background: transparent;
    color: {t['dim']};
    border-top: 1px solid {t['edge']};
}}
QToolTip {{
    background: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['edge_strong']};
    border-radius: 8px;
    padding: 6px 9px;
}}
QMenu {{
    background: {t['surface']};
    border: 1px solid {t['edge_strong']};
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{ padding: 8px 22px 8px 14px; border-radius: 8px; }}
QMenu::item:selected {{ background: {t['selection']}; }}

/* ── the painted core keeps its own rules ───────────────────────────────── */
/* The Omega core, the Island and the dock paint themselves. These rules
   keep their labels transparent and their values in the accent colour, so
   the premium chrome does not fight with the artwork. */
QWidget#omegaFloat, QLabel {{ background: transparent; }}
QWidget#omegaFloatPanel {{ color: {t['text']}; }}
QLabel#omegaMuted, QLabel#omegaEyebrow, QLabel#omegaTitle,
QLabel#omegaValue, QLabel#omegaState {{ background: transparent; }}
QLabel#omegaMuted {{ color: {t['muted']}; font-size: 12px; }}
QLabel#omegaEyebrow {{ color: {t['accent']}; font-weight: 700; letter-spacing: 2px; font-size: 11px; }}
QLabel#omegaTitle {{ color: {t['text']}; font-size: 29px; font-weight: 700; }}
QLabel#omegaValue {{ color: {t['accent']}; font-size: 25px; font-weight: 650; }}
QLabel#omegaState {{ color: {t['accent']}; font-weight: 650; }}
QFrame#omegaCard, QFrame#omegaDock, QFrame#omegaComposer {{
    background: {t['glass']};
    border: 1px solid {t['edge']};
    border-radius: 18px;
}}
QFrame#omegaDock {{ border-radius: 22px; }}
QFrame#omegaDock QToolButton {{ border-radius: 12px; padding: 2px 3px; font-size: 12px; }}
QScrollArea#omegaScroll, QScrollArea#omegaScroll > QWidget > QWidget {{ background: transparent; border: 0; }}
QToolButton[active="true"], QPushButton#omegaPrimary {{
    color: {t['accent_ink']};
    background: {t['accent']};
    border-color: {t['accent']};
    font-weight: 700;
}}
"""


#: The two palettes the owner can choose between by name.
DARK_PALETTE = ('#05080e', '#111a26', '#7ec4ec', '#e9f3fc', '#8ba3bd', '#63dcff', '#efae67')
LIGHT_PALETTE = ('#eef2f7', '#ffffff', '#1c4a74', '#0f1c29', '#4a5f75', '#0d7fb8', '#b06a2c')

PRIME_DARK = stylesheet(DARK_PALETTE)
PRIME_LIGHT = stylesheet(LIGHT_PALETTE)

#: Every theme, by the name the owner sees in Settings.
THEMES = {'Dark': PRIME_DARK, 'Light': PRIME_LIGHT}


def theme_name(store) -> str:
    """The theme the owner chose, or the default."""
    chosen = str(store.get(THEME_KEY) or '').strip()
    return chosen if chosen in THEMES else DEFAULT_THEME


def build(palette) -> str:
    """The premium stylesheet for one palette.

    The palette is the Omega's own: (background, panel, edge, ink, muted,
    cyan, gold).
    """
    return stylesheet(palette)


def apply_theme(app, store=None, name: str = '') -> str:
    """Apply the chosen theme to the running application.

    Returns the name of the theme that is now in place. Calling this with no
    store applies the default theme, which is what the application does at
    startup.
    """
    chosen = name or (theme_name(store) if store is not None else DEFAULT_THEME)
    app.setStyleSheet(THEMES.get(chosen, PRIME_DARK))
    return chosen


def card_shadow(widget, blur: int = 34, alpha: int = 120, dy: int = 6):
    """Give a panel a soft, low shadow.

    A stylesheet cannot draw a shadow, so the depth is real: a graphics
    effect on the widget itself.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect
