"""Semantic design tokens used by every FlowTrack UI surface."""

from dataclasses import dataclass, fields
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ColorTokens:
    application_background: str
    sidebar_background: str
    surface_primary: str
    surface_secondary: str
    surface_elevated: str
    surface_hover: str
    surface_selected: str
    border_subtle: str
    divider: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    success: str
    warning: str
    danger: str
    info: str
    focus: str
    disabled: str
    status_not_started: str
    status_in_progress: str
    status_blocked: str
    status_waiting: str
    status_complete: str
    status_cancelled: str


@dataclass(frozen=True, slots=True)
class SpacingTokens:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True, slots=True)
class RadiusTokens:
    sm: int = 5
    md: int = 8
    lg: int = 12


@dataclass(frozen=True, slots=True)
class TypographyTokens:
    body: int = 13
    small: int = 11
    heading: int = 22
    title: int = 28
    weight_regular: int = 400
    weight_medium: int = 500
    weight_semibold: int = 600


@dataclass(frozen=True, slots=True)
class Theme:
    """A complete theme definition, suitable for validated external loading."""

    identifier: str
    display_name: str
    colors: ColorTokens
    spacing: SpacingTokens = SpacingTokens()
    radii: RadiusTokens = RadiusTokens()
    typography: TypographyTokens = TypographyTokens()

    @classmethod
    def from_mapping(cls, definition: Mapping[str, Any]) -> "Theme":
        """Build a theme from a mapping, rejecting missing or unknown tokens."""
        allowed = {field.name for field in fields(ColorTokens)}
        colors = definition.get("colors")
        if not isinstance(colors, Mapping) or set(colors) != allowed:
            raise ValueError("theme colors must contain every semantic color token")
        identifier = definition.get("identifier")
        display_name = definition.get("display_name")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("theme identifier must be a non-empty string")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("theme display_name must be a non-empty string")
        return cls(identifier, display_name, ColorTokens(**dict(colors)))
