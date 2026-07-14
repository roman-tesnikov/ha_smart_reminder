"""Tests for global Smart Reminder settings."""

from custom_components.smart_reminder.config_flow import (
    _normalize_settings,
    _settings_schema,
)
from custom_components.smart_reminder.const import (
    CONF_ALREADY_COMPLETED_ERROR_TEXT,
    CONF_ALREADY_SNOOZED_ERROR_TEXT,
    CONF_DND_END,
    CONF_DND_START,
    DEFAULT_ALREADY_COMPLETED_ERROR_TEXT,
    DEFAULT_ALREADY_SNOOZED_ERROR_TEXT,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
)


def test_settings_schema_contains_error_text_defaults() -> None:
    settings = _settings_schema({})({})

    assert settings == {
        CONF_DND_START: DEFAULT_DND_START,
        CONF_DND_END: DEFAULT_DND_END,
        CONF_ALREADY_SNOOZED_ERROR_TEXT: DEFAULT_ALREADY_SNOOZED_ERROR_TEXT,
        CONF_ALREADY_COMPLETED_ERROR_TEXT: DEFAULT_ALREADY_COMPLETED_ERROR_TEXT,
    }


def test_blank_error_texts_are_replaced_with_defaults() -> None:
    settings = _normalize_settings(
        {
            CONF_ALREADY_SNOOZED_ERROR_TEXT: "  ",
            CONF_ALREADY_COMPLETED_ERROR_TEXT: None,
        }
    )

    assert (
        settings[CONF_ALREADY_SNOOZED_ERROR_TEXT] == DEFAULT_ALREADY_SNOOZED_ERROR_TEXT
    )
    assert (
        settings[CONF_ALREADY_COMPLETED_ERROR_TEXT]
        == DEFAULT_ALREADY_COMPLETED_ERROR_TEXT
    )


def test_custom_error_texts_are_trimmed() -> None:
    settings = _normalize_settings(
        {
            CONF_ALREADY_SNOOZED_ERROR_TEXT: "  Already snoozed  ",
            CONF_ALREADY_COMPLETED_ERROR_TEXT: "  Already completed  ",
        }
    )

    assert settings[CONF_ALREADY_SNOOZED_ERROR_TEXT] == "Already snoozed"
    assert settings[CONF_ALREADY_COMPLETED_ERROR_TEXT] == "Already completed"
