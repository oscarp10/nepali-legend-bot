#!/usr/bin/env python3
"""Fix verification: create #verify, update welcome, attempt thread cleanup."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

TOKEN = json.loads(Path.home().joinpath(".cursor/mcp.json").read_text())[
    "mcpServers"
]["discord"]["env"]["DISCORD_TOKEN"]
API = "https://discord.com/api/v10"
GUILD = "1553269087864356884"
WELCOME_CAT = "1553269089315725373"
WID = "1553269089315725374"
OSCAR_USER = "1553274441944010802"
OSCAR_ROLE = "1553275610351013941"
CLASHPERK = "1553270202312163382"
LEADER = "1553269087864356885"
EVERYONE = GUILD

ALLOW_USER = str(1024 + 2048 + 65536 + 2147483648 + 64)
DENY_USER = str(34359738368 + 68719476736 + 274877906944)
ALLOW_BOT = str(
    1024
    + 2048
    + 8192
    + 16384
    + 32768
    + 65536
    + 64
    + 2147483648
    + 274877906944
    + 17179869184
)


def curl(method: str, path: str, data: Optional[dict] = None) -> tuple[str, Any]:
    cmd = [
        "curl",
        "-s",
        "-X",
        method,
        "-H",
        f"Authorization: Bot {TOKEN}",
        "-w",
        "\nHTTP:%{http_code}",
    ]
    if data is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    cmd.append(API + path)
    out = subprocess.check_output(cmd, text=True)
    body, _, code = out.rpartition("\nHTTP:")
    try:
        parsed: Any = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = body
    return code.strip(), parsed


def main() -> None:
    # Find existing #verify or create
    code, chs = curl("GET", f"/guilds/{GUILD}/channels")
    assert isinstance(chs, list), chs
    verify = next((c for c in chs if c.get("name") == "verify" and c.get("type") == 0), None)
    if verify:
        vid = verify["id"]
        print("using existing #verify", vid)
    else:
        code, created = curl(
            "POST",
            f"/guilds/{GUILD}/channels",
            {
                "name": "verify",
                "type": 0,
                "parent_id": WELCOME_CAT,
                "topic": "ClashPerk /verify only — do not create threads",
                "rate_limit_per_user": 10,
            },
        )
        print("create #verify", code, created if not isinstance(created, dict) else created.get("id"))
        assert isinstance(created, dict) and created.get("id"), created
        vid = created["id"]

    for role, allow, deny in (
        (EVERYONE, ALLOW_USER, DENY_USER),
        (CLASHPERK, ALLOW_BOT, "0"),
        (OSCAR_ROLE, ALLOW_BOT, "0"),
        (LEADER, ALLOW_BOT, "0"),
    ):
        code, _ = curl(
            "PUT",
            f"/channels/{vid}/permissions/{role}",
            {"type": 0, "allow": allow, "deny": deny},
        )
        print("overwrite", role, code)

    # Clear old Oscar messages in #verify then post guide
    code, msgs = curl("GET", f"/channels/{vid}/messages?limit=20")
    if isinstance(msgs, list):
        for m in msgs:
            if m.get("author", {}).get("id") == OSCAR_USER:
                curl("DELETE", f"/channels/{vid}/messages/{m['id']}")

    code, _ = curl(
        "POST",
        f"/channels/{vid}/messages",
        {
            "embeds": [
                {
                    "title": "✅ Verify with ClashPerk",
                    "color": 5763719,
                    "description": (
                        "**Use this channel only to verify.**\n\n"
                        "1. Type `/` in this channel\n"
                        "2. Select **`/verify`** from **ClashPerk**\n"
                        "3. **player** → your CoC tag (example `#ABC123XYZ`)\n"
                        "4. **token** → in-game API token\n\n"
                        "**Get token:** Clash of Clans → Settings → More Settings → **API Token** → Show\n\n"
                        "❌ Do **not** create threads\n"
                        "❌ Do **not** paste your token as normal chat\n\n"
                        "Clan tag: `#R2J28R8Q`"
                    ),
                }
            ]
        },
    )
    print("verify guide post", code)

    # Keep welcome readable but send-light: point everyone to #verify
    # Allow view/hist/app; deny send+threads on welcome to stop thread spam
    welcome_allow = str(1024 + 65536 + 2147483648)
    welcome_deny = str(2048 + 34359738368 + 68719476736 + 274877906944)
    for role in (EVERYONE, "1553269087864356888", "1553269087864356889", "1553269087864356887", "1553269087864356886"):
        code, _ = curl(
            "PUT",
            f"/channels/{WID}/permissions/{role}",
            {"type": 0, "allow": welcome_allow, "deny": welcome_deny},
        )
        print("welcome overwrite", role, code)

    # ClashPerk/Oscar/Leader can still send in welcome
    for role in (CLASHPERK, OSCAR_ROLE, LEADER):
        code, _ = curl(
            "PUT",
            f"/channels/{WID}/permissions/{role}",
            {"type": 0, "allow": ALLOW_BOT, "deny": "0"},
        )

    code, msgs = curl("GET", f"/channels/{WID}/messages?limit=30")
    if isinstance(msgs, list):
        for m in msgs:
            if m.get("author", {}).get("id") == OSCAR_USER:
                curl("DELETE", f"/channels/{WID}/messages/{m['id']}")
                print("deleted welcome msg", m["id"])

    code, _ = curl(
        "POST",
        f"/channels/{WID}/messages",
        {
            "embeds": [
                {
                    "title": "🏆 Welcome to Nepali Legend's",
                    "color": 15105570,
                    "description": (
                        "Namaste! Official Discord for **Nepali Legend's**\n"
                        "🏷️ Clan tag: `#R2J28R8Q`\n\n"
                        "### ✅ Verify first\n"
                        f"Go to <#{vid}> and run **`/verify`** (ClashPerk).\n\n"
                        f"**Steps**\n"
                        f"1. Open <#{vid}>\n"
                        "2. Type `/verify` → choose ClashPerk\n"
                        "3. player = your tag · token = in-game API token\n\n"
                        "Get token: CoC → Settings → More Settings → **API Token**\n\n"
                        "⚠️ Ignore old **Verify** threads under welcome — they are broken. "
                        "Only use the `#verify` channel."
                    ),
                }
            ]
        },
    )
    print("welcome post", code)

    # Try delete stuck threads again
    code, active = curl("GET", f"/guilds/{GUILD}/threads/active")
    if isinstance(active, dict):
        for t in active.get("threads", []):
            if t.get("parent_id") == WID:
                code, body = curl("DELETE", f"/channels/{t['id']}")
                print("delete thread", t.get("name"), t["id"], code, body)

    perms = (
        16
        | 8192
        | 268435456
        | 17179869184
        | 1024
        | 2048
        | 16384
        | 32768
        | 65536
        | 64
        | 2147483648
        | 274877906944
    )
    url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={OSCAR_USER}&permissions={perms}&scope=bot%20applications.commands"
    )
    print("REINVITE_URL", url)
    print("VERIFY_CHANNEL_ID", vid)


if __name__ == "__main__":
    main()
