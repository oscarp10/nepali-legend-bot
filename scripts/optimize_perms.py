#!/usr/bin/env python3
"""Re-apply Unverified gate + feed perms (low pill clutter)."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

TOKEN = json.loads(Path.home().joinpath(".cursor/mcp.json").read_text())[
    "mcpServers"
]["discord"]["env"]["DISCORD_TOKEN"]
API = "https://discord.com/api/v10"
GUILD = "1553269087864356884"

EVERYONE = GUILD
MEMBER = "1553269087864356888"
RECRUIT = "1553269087864356889"
ELDER = "1553269087864356887"
CO = "1553269087864356886"
LEADER = "1553269087864356885"
WARRIOR = "1553269087864356891"
OSCAR = "1553275610351013941"
CLASHPERK = "1553270202312163382"
UNVERIFIED = "1554041899457974323"

STAFF = [LEADER, CO, ELDER]
BOTS = [OSCAR, CLASHPERK]
VERIFIED = [MEMBER, RECRUIT, ELDER, CO, WARRIOR, LEADER]

VIEW = 1024
SEND = 2048
MANAGE_MSG = 8192
EMBED = 16384
ATTACH = 32768
HIST = 65536
REACT = 64
APP = 2147483648
SEND_TH = 274877906944

CAT_WELCOME = "1553269089315725373"
CAT_CLAN = "1553269089315725378"
CAT_RANKED = "1553973491299254302"
CAT_BOTLOGS = "1553277378262999082"
CAT_WAR = "1553269089810784321"
CAT_COMMUNITY = "1553269090305572867"
CAT_BASES = "1553313238123290776"
CAT_VOICE = "1553269090746109995"
CAT_STAFF = "1553277391005032508"
VERIFY = "1554035272063131758"

ok = fail = 0


def curl(method: str, path: str, data=None):
    cmd = [
        "curl", "-s", "-X", method,
        "-H", f"Authorization: Bot {TOKEN}",
        "-w", "\nHTTP:%{http_code}",
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


def put_ow(channel: str, role: str, allow: int, deny: int) -> bool:
    global ok, fail
    for _ in range(5):
        code, body = curl(
            "PUT",
            f"/channels/{channel}/permissions/{role}",
            {"type": 0, "allow": str(allow), "deny": str(deny)},
        )
        if code in ("204", "200"):
            ok += 1
            time.sleep(0.25)
            return True
        if code == "429":
            wait = float(body.get("retry_after", 3)) + 0.5 if isinstance(body, dict) else 3
            time.sleep(wait)
            continue
        print(f"  FAIL {channel} {role} {code} {body}")
        fail += 1
        return False
    fail += 1
    return False


def bots(ch: str) -> None:
    allow = VIEW + HIST + APP + MANAGE_MSG + EMBED + SEND + ATTACH + REACT + SEND_TH
    for role in [LEADER, *BOTS]:
        put_ow(ch, role, allow, 0)


def main() -> None:
    print("Permissions pass…", flush=True)

    # Welcome public RO
    put_ow(CAT_WELCOME, EVERYONE, VIEW + HIST + APP, SEND + SEND_TH)
    bots(CAT_WELCOME)

    # Staff private
    put_ow(CAT_STAFF, EVERYONE, 0, VIEW)
    put_ow(CAT_STAFF, UNVERIFIED, 0, VIEW)
    for role in STAFF:
        put_ow(CAT_STAFF, role, VIEW + HIST + APP + SEND + REACT + EMBED + ATTACH, 0)
    bots(CAT_STAFF)

    # Community chat
    put_ow(CAT_COMMUNITY, EVERYONE, VIEW + HIST + APP + SEND + REACT + EMBED + ATTACH, 0)
    put_ow(CAT_COMMUNITY, UNVERIFIED, 0, VIEW)
    bots(CAT_COMMUNITY)

    # RO gated categories (incl ranked)
    for cid in (CAT_CLAN, CAT_WAR, CAT_BOTLOGS, CAT_BASES, CAT_RANKED, CAT_VOICE):
        put_ow(cid, EVERYONE, VIEW + HIST + APP, SEND + SEND_TH)
        put_ow(cid, UNVERIFIED, 0, VIEW)
        bots(cid)

    # Verify channel
    put_ow(VERIFY, EVERYONE, VIEW + HIST + APP, 0)
    put_ow(VERIFY, UNVERIFIED, VIEW + HIST + APP, 0)
    for role in VERIFIED:
        put_ow(VERIFY, role, 0, VIEW)
    bots(VERIFY)

    print(f"DONE ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
