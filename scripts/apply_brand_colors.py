#!/usr/bin/env python3
"""Apply Nepali Legend purple/gold brand colors to Discord roles + ranked category."""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.brand import ROLE_COLORS  # noqa: E402

GUILD_ID = os.environ.get("GUILD_ID", "1553269087864356884")
RANKED_CATEGORY_ID = "1553973491299254302"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _token() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DISCORD_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    mcp = Path.home() / ".cursor" / "mcp.json"
    data = json.loads(mcp.read_text())
    return data["mcpServers"]["discord"]["env"]["DISCORD_TOKEN"]


def api(method: str, path: str, body: dict | None = None) -> dict | list | None:
    token = _token()
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "NepaliLegendBrand/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CTX) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()
        raise RuntimeError(f"{method} {path} → {exc.code}: {err}") from exc


def main() -> None:
    roles = api("GET", f"/guilds/{GUILD_ID}/roles")
    assert isinstance(roles, list)
    by_name = {r["name"]: r for r in roles}

    updated = 0
    for name, color in ROLE_COLORS.items():
        role = by_name.get(name)
        if not role:
            print(f"skip missing role: {name}")
            continue
        if int(role.get("color") or 0) == color:
            print(f"ok   {name} already #{color:06x}")
            continue
        try:
            api(
                "PATCH",
                f"/guilds/{GUILD_ID}/roles/{role['id']}",
                {"color": color},
            )
            print(f"set  {name} → #{color:06x}")
            updated += 1
            time.sleep(0.6)
        except RuntimeError as exc:
            print(f"fail {name}: {exc}")

    try:
        api(
            "PATCH",
            f"/channels/{RANKED_CATEGORY_ID}",
            {"name": "🏆 Ranked · Legend & Electro"},
        )
        print("set  ranked category → 🏆 Ranked · Legend & Electro")
    except RuntimeError as exc:
        print(f"category rename failed: {exc}")

    for cid, topic in (
        (
            "1553983640537665606",
            "Legend II / III · live CoC Battle Log cards · purple & gold",
        ),
        (
            "1554024392491532361",
            "Electro League · live CoC Battle Log cards · purple & gold",
        ),
    ):
        try:
            api("PATCH", f"/channels/{cid}", {"topic": topic})
            print(f"set  topic on {cid}")
            time.sleep(0.4)
        except RuntimeError as exc:
            print(f"topic fail {cid}: {exc}")

    print(f"done — updated {updated} roles")


if __name__ == "__main__":
    main()
