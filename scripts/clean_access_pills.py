#!/usr/bin/env python3
"""Remove private-channel role pills.

Discord only shows that role strip on private channels (@everyone cannot view).
Gate the server with an Unverified role deny instead, so @everyone can view and
channels stay public in the UI — no role pills.
"""
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
# Existing unused role — rename to Unverified
UNVERIFIED = "1554041899457974323"

VERIFIED = [MEMBER, RECRUIT, ELDER, CO, WARRIOR, LEADER]
STAFF = [LEADER, CO, ELDER]
BOTS = [OSCAR, CLASHPERK]

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

RW_CHANNELS = {
    "1553269090305572864",  # create-remainders
    "1553269089810784322",  # war-strategy
    "1553269090305572866",  # attack-planning
    "1553313243202723860",
    "1553313247019401306",
    "1553313250592956556",
    "1553313254112100392",
}

ok = fail = 0


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


def put_ow(channel: str, target: str, allow: int, deny: int, typ: int = 0) -> bool:
    global ok, fail
    for _ in range(6):
        code, body = curl(
            "PUT",
            f"/channels/{channel}/permissions/{target}",
            {"type": typ, "allow": str(allow), "deny": str(deny)},
        )
        if code in ("204", "200"):
            ok += 1
            time.sleep(0.3)
            return True
        if code == "429":
            wait = float(body.get("retry_after", 3)) + 0.5 if isinstance(body, dict) else 3.0
            time.sleep(wait)
            continue
        print(f"  FAIL put {channel} {target} {code} {body}", flush=True)
        fail += 1
        time.sleep(0.3)
        return False
    fail += 1
    return False


def del_ow(channel: str, target: str) -> bool:
    global ok, fail
    for _ in range(6):
        code, body = curl("DELETE", f"/channels/{channel}/permissions/{target}")
        if code in ("204", "200", "404"):
            if code != "404":
                ok += 1
            time.sleep(0.25)
            return True
        if code == "429":
            wait = float(body.get("retry_after", 3)) + 0.5 if isinstance(body, dict) else 3.0
            time.sleep(wait)
            continue
        print(f"  FAIL del {channel} {target} {code} {body}", flush=True)
        fail += 1
        time.sleep(0.25)
        return False
    fail += 1
    return False


def clear_all(channel: dict) -> None:
    for ow in list(channel.get("permission_overwrites") or []):
        del_ow(channel["id"], ow["id"])


def bots(channel: str) -> None:
    allow = VIEW + HIST + APP + MANAGE_MSG + EMBED + SEND + ATTACH + REACT + SEND_TH
    for role in [LEADER, *BOTS]:
        put_ow(channel, role, allow, 0)


def main() -> None:
    global ok, fail

    # Rename existing role → Unverified
    print("Ensure Unverified role…", flush=True)
    code, body = curl(
        "PATCH",
        f"/guilds/{GUILD}/roles/{UNVERIFIED}",
        {"name": "Unverified", "mentionable": False, "hoist": False},
    )
    print(f"  rename {code}", flush=True)

    _, channels = curl("GET", f"/guilds/{GUILD}/channels")

    print("\nClear all overwrites…", flush=True)
    for c in channels:
        if c["type"] not in (0, 2, 4):
            continue
        if c.get("permission_overwrites"):
            print(f"  {c['name']}", flush=True)
            clear_all(c)

    print("\nCategory baselines (public + Unverified deny)…", flush=True)

    # Welcome: public read-only
    print("  WELCOME", flush=True)
    put_ow(CAT_WELCOME, EVERYONE, VIEW + HIST + APP, SEND + SEND_TH)
    bots(CAT_WELCOME)

    # Staff: still private (only staff) — few roles = few pills
    print("  STAFF", flush=True)
    put_ow(CAT_STAFF, EVERYONE, 0, VIEW)
    put_ow(CAT_STAFF, UNVERIFIED, 0, VIEW)
    for role in STAFF:
        put_ow(CAT_STAFF, role, VIEW + HIST + APP + SEND + REACT + EMBED + ATTACH, 0)
    bots(CAT_STAFF)

    # Chat categories: public to @everyone, hide Unverified, allow send
    for label, cid in [("COMMUNITY", CAT_COMMUNITY)]:
        print(f"  {label}", flush=True)
        put_ow(cid, EVERYONE, VIEW + HIST + APP + SEND + REACT + EMBED + ATTACH, 0)
        put_ow(cid, UNVERIFIED, 0, VIEW)
        bots(cid)

    # Read-only gated categories
    for label, cid in [
        ("CLAN", CAT_CLAN),
        ("WAR", CAT_WAR),
        ("BOTLOGS", CAT_BOTLOGS),
        ("BASES", CAT_BASES),
        ("RANKED", CAT_RANKED),
        ("VOICE", CAT_VOICE),
    ]:
        print(f"  {label}", flush=True)
        put_ow(cid, EVERYONE, VIEW + HIST + APP, SEND + SEND_TH)
        put_ow(cid, UNVERIFIED, 0, VIEW)
        bots(cid)

    print("\nChannel exceptions…", flush=True)

    # #verify: Unverified + everyone can see; verified hide it
    print("  #verify", flush=True)
    put_ow(VERIFY, EVERYONE, VIEW + HIST + APP, 0)
    put_ow(VERIFY, UNVERIFIED, VIEW + HIST + APP, 0)
    for role in VERIFIED:
        put_ow(VERIFY, role, 0, VIEW)
    bots(VERIFY)

    # RW channels in RO categories
    _, channels = curl("GET", f"/guilds/{GUILD}/channels")
    by_id = {c["id"]: c for c in channels}
    for cid in RW_CHANNELS:
        ch = by_id.get(cid)
        if not ch:
            continue
        print(f"  RW #{ch['name']}", flush=True)
        # Public chat override; still hide Unverified
        put_ow(cid, EVERYONE, VIEW + HIST + APP + SEND + REACT + EMBED + ATTACH, 0)
        put_ow(cid, UNVERIFIED, 0, VIEW)
        bots(cid)

    # Assign Unverified to anyone without a clan/staff role
    print("\nAssign Unverified to unranked members…", flush=True)
    code, members = curl("GET", f"/guilds/{GUILD}/members?limit=1000")
    if not isinstance(members, list):
        print(f"  members fetch {code} {members}", flush=True)
        members = []
    verified_set = set(VERIFIED)
    assigned = 0
    for m in members:
        roles = set(m.get("roles") or [])
        if roles & verified_set:
            continue
        if UNVERIFIED in roles:
            continue
        uid = m["user"]["id"]
        if m["user"].get("bot"):
            continue
        c, b = curl("PUT", f"/guilds/{GUILD}/members/{uid}/roles/{UNVERIFIED}")
        if c in ("204", "200"):
            assigned += 1
        else:
            print(f"  FAIL assign {uid} {c} {b}", flush=True)
        time.sleep(0.35)
    print(f"  assigned={assigned}", flush=True)

    print(f"\nDONE ok={ok} fail={fail}", flush=True)
    print(
        "Set ClashPerk / onboarding to: give Unverified on join, remove Unverified on verify.",
        flush=True,
    )


if __name__ == "__main__":
    main()
