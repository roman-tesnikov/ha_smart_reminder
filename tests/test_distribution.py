"""Validate files required by distribution channels."""

import struct
from pathlib import Path


def test_hacs_brand_icon_is_valid_rgba_png() -> None:
    """HACS requires a local brand icon for custom integrations."""
    icon = Path("custom_components/smart_reminder/brand/icon.png")
    data = icon.read_bytes()

    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"

    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (512, 512)
    assert data[24] == 8  # Bit depth.
    assert data[25] == 6  # RGBA colour type.
