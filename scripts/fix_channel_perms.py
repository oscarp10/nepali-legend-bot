#!/usr/bin/env python3
"""Fix Discord perms: hide #verify after verify, read-only ranked feeds."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

TOKEN = json.loads(Path.home().joinpath(".cursor/mcp.json").read_text())[
    "mcpServers"
]["discord"]["env"]["DISCORD_TOKEN"]
API = "https://discord.com/api/v10"
GUILD = "1553269087864356884"

VERIFY = "1554035272063131758"
LEGEND = "1553983640537665606"
ELECTRO = "1554024392491532361"
RANKED_CAT = "1553973491299254302"

EVERYONE = GUILD
MEMBER = "1553269087864356888"
RECRUIT = "1553269087864356889"
ELDER = "1553269087864356887"
CO = "1553269087864356886"
LEADER = "1553269087864356885"
WARRIOR = "1553269087864356891"
OSCAR = "1553275610351013941"
CLASHPERK = "1553270202312163382"

VIEW = 1024
SEND = 2048
MANAGE_MSG = 8192
EMBED = 16384
ATTACH = 32768
HIST = 65536
REACT = 64
APP = 2147483648
PUB_TH = 34359738368
PRIV_TH = 68719476736
SEND_TH = 274877906944

# Unverified (@everyone): can see channel; keep Send from guild defaults (don't grant Send
# in the overwrite — bot role lacks Send at guild level so Discord rejects it).
VERIFY_EVERYONE_ALLOW = str(VIEW + HIST + APP)
VERIFY_EVERYONE_DENY = str(PUB_TH + PRIV_TH + SEND_TH)
# Verified roles: hide channel completely
VERIFY_HIDDEN_ALLOW = "0"
VERIFY_HIDDEN_DENY = str(VIEW)

# Ranked feeds: read-only for members
READ_ALLOW = str(VIEW + HIST)
READ_DENY = str(SEND + PUB_TH + PRIV_TH + SEND_TH + REACT)
# Bots/staff can post
BOT_ALLOW = str(VIEW + SEND + MANAGE_MSG + EMBED + ATTACH + HIST + REACT + APP + SEND_TH)


def curl(method: str, path: str, data=None):
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
        parsed = json.loads(body) if body.strip() else None
    except Exception:
        parsed = body
    return code.strip(), parsed


def overwrite(channel: str, role: str, allow: str, deny: str) -> None:
    code, body = curl(
        "PUT",
        f"/channels/{channel}/permissions/{role}",
        {"type": 0, "allow": allow, "deny": deny},
    )
    print(f"  {channel} role={role} -> {code}", body if code != "204" else "")


def main() -> None:
    print("=== #verify: visible only to unverified ===")
    overwrite(VERIFY, EVERYONE, VERIFY_EVERYONE_ALLOW, VERIFY_EVERYONE_DENY)
    for role in (MEMBER, RECRUIT, ELDER, CO, WARRIOR):
        overwrite(VERIFY, role, VERIFY_HIDDEN_ALLOW, VERIFY_HIDDEN_DENY)
    for role in (LEADER, OSCAR, CLASHPERK):
        overwrite(VERIFY, role, BOT_ALLOW, "0")

    print("=== ranked feeds: view-only for members ===")
    for channel in (LEGEND, ELECTRO):
        overwrite(channel, EVERYONE, READ_ALLOW, READ_DENY)
        for role in (MEMBER, RECRUIT, ELDER, CO, WARRIOR):
            overwrite(channel, role, READ_ALLOW, READ_DENY)
        for role in (LEADER, OSCAR, CLASHPERK):
            overwrite(channel, role, BOT_ALLOW, "0")

    # Category: members can view ranked section
    print("=== Ranked Leaderboard category view ===")
    overwrite(RANKED_CAT, EVERYONE, str(VIEW + HIST), "0")
    for role in (LEADER, OSCAR, CLASHPERK):
        overwrite(RANKED_CAT, role, BOT_ALLOW, "0")

    print("done")


if __name__ == "__main__":
    main()
