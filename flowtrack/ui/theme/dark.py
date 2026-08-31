"""The built-in FlowTrack Dark theme."""

from flowtrack.ui.theme.tokens import ColorTokens, Theme

DARK_THEME = Theme(
    identifier="dark",
    display_name="Dark",
    colors=ColorTokens(
        application_background="#111218", sidebar_background="#171820",
        surface_primary="#1b1d26", surface_secondary="#20222d",
        surface_elevated="#272a36", surface_hover="#292b38",
        surface_selected="#302b4a", border_subtle="#30323e", divider="#292b35",
        text_primary="#f3f1f7", text_secondary="#b9b6c3", text_muted="#7f7c89",
        accent="#8b72e8", accent_hover="#9b84ee", accent_pressed="#765dce",
        success="#56b890", warning="#dda950", danger="#df6d7a", info="#65a9d8",
        focus="#aa96f5", disabled="#5e5c67",
        status_not_started="#8f8b99", status_in_progress="#78add2",
        status_blocked="#d97884", status_waiting="#d1a65e",
        status_complete="#68aa8d", status_cancelled="#716e79",
    ),
)
