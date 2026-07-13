"""Smart Reminder custom integration for Home Assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import DOMAIN, PLATFORMS, STORAGE_KEY, STORAGE_VERSION

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .manager import ReminderManager


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Register integration-wide actions, WebSocket API and static assets."""
    from .frontend import async_register_static_files
    from .services import async_register_services
    from .websocket import async_register_websocket_commands

    hass.data.setdefault(DOMAIN, {})
    await async_register_static_files(hass)
    await async_register_services(hass)
    async_register_websocket_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Reminder from a config entry."""
    from .frontend import async_register_panel, async_remove_panel
    from .manager import ReminderManager

    manager = ReminderManager(hass, entry)
    await manager.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    entry.runtime_data = manager
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await async_register_panel(hass)
        await manager.async_start()
    except Exception:
        await manager.async_stop()
        async_remove_panel(hass)
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed DnD options without reloading entities."""
    manager: ReminderManager = entry.runtime_data
    options: dict[str, Any] = {**entry.data, **entry.options}
    await manager.async_options_updated(options)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .frontend import async_remove_panel

    manager: ReminderManager = entry.runtime_data
    await manager.async_stop()
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await manager.async_start()
        return False
    async_remove_panel(hass)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove persistent reminders when the integration is deleted."""
    from homeassistant.helpers.storage import Store

    store = Store[dict[str, Any]](
        hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"
    )
    await store.async_remove()
