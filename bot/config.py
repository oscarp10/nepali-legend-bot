from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Override with DATA_DIR=/data in Docker / Railway so the DB lives on a volume
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser()
DB_PATH = DATA_DIR / "tracker.db"

# Official API or ClashKing-compatible proxy (no key required for proxy)
DEFAULT_COC_BASE = "https://proxy.clashk.ing/v1"

LEGEND_DAY_HOUR_UTC = 5


@dataclass(frozen=True)
class Settings:
    discord_token: str
    coc_api_key: str | None
    coc_api_base: str
    guild_id: int
    clan_tag: str
    legend_channel_id: int | None
    electro_channel_id: int | None
    poll_interval: int


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return int(raw)


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    guild = os.getenv("GUILD_ID", "").strip()
    clan = os.getenv("CLAN_TAG", "#R2J28R8Q").strip()
    coc_key = os.getenv("COC_API_KEY", "").strip() or None
    coc_base = os.getenv("COC_API_BASE", DEFAULT_COC_BASE).strip().rstrip("/")

    if not token:
        raise SystemExit("DISCORD_TOKEN is missing in .env")
    if not guild:
        raise SystemExit("GUILD_ID is missing in .env")

    # Official API requires a key; proxy does not
    if "api.clashofclans.com" in coc_base and not coc_key:
        raise SystemExit(
            "COC_API_KEY is required for api.clashofclans.com — "
            "create one at https://developer.clashofclans.com/ "
            "or leave COC_API_BASE as the default proxy."
        )

    return Settings(
        discord_token=token,
        coc_api_key=coc_key,
        coc_api_base=coc_base,
        guild_id=int(guild),
        clan_tag=clan if clan.startswith("#") else f"#{clan}",
        legend_channel_id=_optional_int("LEGEND_CHANNEL_ID"),
        electro_channel_id=_optional_int("ELECTRO_CHANNEL_ID"),
        poll_interval=max(30, int(os.getenv("POLL_INTERVAL", "60"))),
    )


def classify_tier(tier_name: str | None, league_name: str | None = None) -> str | None:
    """Return 'legend', 'electro', or None.

    New ranked system uses leagueTier names like Legend I / II / III
    and Electro League 31–33.
    """
    name = (tier_name or "").strip().lower()
    legacy = (league_name or "").strip().lower()

    if name.startswith("legend"):
        return "legend"
    if "electro" in name:
        return "electro"
    # Legacy league badges (pre-ranked-tier)
    if "legend" in legacy:
        return "legend"
    if "electro" in legacy:
        return "electro"
    return None
