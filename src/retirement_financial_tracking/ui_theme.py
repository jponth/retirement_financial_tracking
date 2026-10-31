"""Warm Ivory + Forest Sage light theme for the retirement planning Gradio UIs.

Backward-compatible exports: mojave_sage_theme() and MOJAVE_SAGE_CSS.
Use both in gr.Blocks(theme=mojave_sage_theme(), css=MOJAVE_SAGE_CSS).
"""
from __future__ import annotations

import gradio as gr

# Accessible, green-based primary scale: light -> dark.
FOREST_SAGE = gr.themes.Color(
    name="forest_sage",
    c50="#F3F7F3",
    c100="#E4EBDF",
    c200="#D0DFD2",
    c300="#B1C8B8",
    c400="#8DAE99",
    c500="#638D74",
    c600="#416C5A",  # Primary action
    c700="#365B49",  # Hover / selected
    c800="#2C493B",
    c900="#263B30",
    c950="#17281F",
)

# Warm, near-neutral surfaces with a gentle green cast.
WARM_NEUTRAL = gr.themes.Color(
    name="warm_neutral",
    c50="#FAFBF8",
    c100="#F7F8F3",  # Page background
    c200="#EDF0E9",
    c300="#DCE3D9",  # Borders
    c400="#BAC5B9",
    c500="#89998D",
    c600="#68766D",  # Secondary text
    c700="#526057",
    c800="#3B4A40",
    c900="#26352D",  # Primary text
    c950="#19251F",
)

MOJAVE_SAGE = FOREST_SAGE  # Backward compatibility
SAGE_SAND = WARM_NEUTRAL  # Backward compatibility
MOJAVE_SAGE_ACCENT = "#A7AD94"
WARNING_AMBER = "#A66A1F"
SAGE_BACKGROUND = "#F7F8F3"
SAGE_PANEL_BACKGROUND = "#FFFFFF"
SAGE_PANEL_BORDER = "#DCE3D9"
SAGE_PANEL_SHADOW = "rgba(38, 53, 45, 0.06)"
SAGE_RAIL_BACKGROUND = "#F0F4EE"
SAGE_RAIL_BORDER = "#DCE3D9"
SAGE_INPUT_BACKGROUND = "#FFFFFF"
SAGE_TABLE_HEADER_BACKGROUND = "#E9EFE8"
SAGE_TABLE_ROW_ALT = "#F7F9F5"
SAGE_TEXT = "#26352D"


def mojave_sage_theme() -> gr.themes.Base:
    """Return the shared Warm Ivory / Forest Sage Gradio theme."""
    return gr.themes.Soft(
        primary_hue=FOREST_SAGE,
        secondary_hue=FOREST_SAGE,
        neutral_hue=WARM_NEUTRAL,
    ).set(
        body_background_fill=SAGE_BACKGROUND,
        block_background_fill=SAGE_PANEL_BACKGROUND,
        block_border_color=SAGE_PANEL_BORDER,
        block_label_text_color=WARM_NEUTRAL.c800,
        block_title_text_color=SAGE_TEXT,
        panel_background_fill=SAGE_RAIL_BACKGROUND,
        panel_border_color=SAGE_PANEL_BORDER,
        border_color_primary=WARM_NEUTRAL.c300,
        background_fill_primary=SAGE_PANEL_BACKGROUND,
        background_fill_secondary=SAGE_BACKGROUND,
        input_background_fill=SAGE_INPUT_BACKGROUND,
        input_border_color=WARM_NEUTRAL.c300,
        input_border_color_focus=FOREST_SAGE.c600,
        input_placeholder_color=WARM_NEUTRAL.c600,
        checkbox_border_color_selected=FOREST_SAGE.c600,
        checkbox_background_color_selected=FOREST_SAGE.c600,
        button_primary_background_fill=FOREST_SAGE.c600,
        button_primary_background_fill_hover=FOREST_SAGE.c700,
        button_primary_text_color="#FFFFFF",
        button_primary_border_color=FOREST_SAGE.c700,
        button_secondary_background_fill=FOREST_SAGE.c100,
        button_secondary_background_fill_hover=FOREST_SAGE.c200,
        button_secondary_text_color=FOREST_SAGE.c800,
        button_secondary_border_color=FOREST_SAGE.c300,
        table_border_color=SAGE_PANEL_BORDER,
        table_even_background_fill=SAGE_PANEL_BACKGROUND,
        table_odd_background_fill=SAGE_TABLE_ROW_ALT,
        error_background_fill="#FFF2E9",
        error_border_color=WARNING_AMBER,
    )


# Scoped to light mode: avoid forcing white surfaces when dark mode is selected.
MOJAVE_SAGE_CSS = f"""
    .gradio-container:not(.dark) {{
        background: {SAGE_BACKGROUND} !important;
        color: {SAGE_TEXT};
    }}

    .gradio-container:not(.dark) .block,
    .gradio-container:not(.dark) .form,
    .gradio-container:not(.dark) .panel {{
        box-shadow: 0 6px 16px {SAGE_PANEL_SHADOW};
    }}

    .gradio-container:not(.dark) .tab-nav {{
        background: {SAGE_PANEL_BACKGROUND};
        border: 1px solid {SAGE_PANEL_BORDER};
        border-radius: 14px;
        padding: 0.35rem;
        gap: 0.35rem;
    }}

    .gradio-container:not(.dark) .tab-nav button {{
        border-radius: 10px !important;
        transition: background-color 120ms ease, color 120ms ease,
                    border-color 120ms ease;
    }}

    .gradio-container:not(.dark) .tab-nav button.selected {{
        background: {FOREST_SAGE.c100} !important;
        color: {FOREST_SAGE.c800} !important;
        border-color: {FOREST_SAGE.c600} !important;
        font-weight: 600;
    }}

    .gradio-container:not(.dark) .tab-nav button:hover {{
        background: {FOREST_SAGE.c100} !important;
        color: {FOREST_SAGE.c800} !important;
    }}

    .gradio-container:not(.dark) input,
    .gradio-container:not(.dark) textarea,
    .gradio-container:not(.dark) select {{
        background: {SAGE_INPUT_BACKGROUND} !important;
    }}

    .gradio-container:not(.dark) table {{
        background: {SAGE_PANEL_BACKGROUND};
    }}

    .gradio-container:not(.dark) th,
    .gradio-container:not(.dark) .header-cell {{
        background: {SAGE_TABLE_HEADER_BACKGROUND} !important;
        color: {SAGE_TEXT} !important;
        font-weight: 600;
    }}

    .gradio-container:not(.dark) td,
    .gradio-container:not(.dark) .body-cell {{
        background: {SAGE_PANEL_BACKGROUND};
        color: {SAGE_TEXT};
    }}

    .gradio-container:not(.dark) tr:nth-child(even) td {{
        background: {SAGE_TABLE_ROW_ALT};
    }}

    .gradio-container:not(.dark) .prose strong,
    .gradio-container:not(.dark) .prose b {{
        color: {SAGE_TEXT};
    }}

    .gradio-container:not(.dark) .prose code {{
        background: {WARM_NEUTRAL.c200};
        border: 1px solid {SAGE_PANEL_BORDER};
        border-radius: 6px;
        padding: 0.12rem 0.35rem;
    }}

    .gradio-container:not(.dark) .prose blockquote {{
        border-left: 4px solid {MOJAVE_SAGE_ACCENT};
        background: {FOREST_SAGE.c50};
        color: {FOREST_SAGE.c800};
    }}

    .gradio-container:not(.dark) h1,
    .gradio-container:not(.dark) h2,
    .gradio-container:not(.dark) h3 {{
        color: {SAGE_TEXT};
    }}
"""
