"""Nepali Legend's visual brand — purple / gold CoC battle-log tune."""

from __future__ import annotations

# Discord embed accent (matches card header purple)
PURPLE = 0x5C3082
PURPLE_DEEP = 0x30203A
PURPLE_SOFT = 0x7B5EA7
GOLD = 0xC9A227
GOLD_BRIGHT = 0xFFC832
TAN = 0xC6B8A8
BORDER_GOLD = 0x785537

# Role colors (hierarchy: gold leadership → purple members)
ROLE_COLORS: dict[str, int] = {
    "👑 Clan Leader": 0xC9A227,
    "⭐ Co-Leader": 0xE8B84A,
    "🔰 Elder": 0xB8956A,
    "🛡️ Member": 0x9B7EBD,
    "🌟 Warrior": 0x7B5EA7,
    "🆕 Recruit": 0x6B5B7A,
    "🤖 Bot": 0x5C3082,
    "Nepali Legend Bot": 0x5C3082,
    "ClashPerk": 0x6B4C8A,
    "🏰 Raid Ping": 0xC9A227,
    "🎮 Clan Games Ping": 0x8E6BB8,
    "🏛️ TH15": 0x6B5B7A,
    "🏛️ TH16": 0x7B5EA7,
    "🏛️ TH17": 0x9B7EBD,
    "🏛️ TH18": 0xC9A227,
    "Unverified": 0x3D2A4A,
}

# Pillow RGB for battle-log cards (keep in sync with graphics)
PNG = {
    "bg": (48, 32, 58),
    "header": (92, 48, 130),
    "col_header": (70, 40, 95),
    "row": (198, 186, 176),
    "border": (120, 85, 55),
    "border_inner": (90, 60, 40),
    "gold": (255, 200, 50),
    "subtitle": (210, 185, 230),
}
