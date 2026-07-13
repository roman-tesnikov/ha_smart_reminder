"""Registration of the bundled Smart Reminder frontend panel."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .const import (
    DOMAIN,
    PANEL_STATIC_URL,
    PANEL_URL_PATH,
    PANEL_WEB_COMPONENT,
    VERSION,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def async_register_static_files(hass: HomeAssistant) -> None:
    """Serve the panel JavaScript from the integration directory."""
    from homeassistant.components.http import StaticPathConfig

    panel_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, str(panel_dir), True)]
    )


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the management page in the Home Assistant sidebar."""
    from homeassistant.components import frontend
    from homeassistant.components.panel_custom import (
        async_register_panel as async_register_custom_panel,
    )

    if frontend.async_panel_exists(hass, PANEL_URL_PATH):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    await async_register_custom_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_WEB_COMPONENT,
        sidebar_title="Smart Reminders",
        sidebar_icon="mdi:bell-check-outline",
        module_url=(f"{PANEL_STATIC_URL}/smart-reminder-panel.js?v={VERSION}"),
        require_admin=True,
        config={"domain": DOMAIN},
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel."""
    from homeassistant.components import frontend

    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
