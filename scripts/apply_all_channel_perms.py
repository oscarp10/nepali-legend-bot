#!/usr/bin/env python3
"""Gate server behind verify + set read-only vs chat channels."""
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

VERIFIED = [MEMBER, RECRUIT, ELDER, CO, WARRIOR]
STAFF_BOTS = [LEADER, OSCAR, CLASHPERK]

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
THREADS = PUB_TH + PRIV_TH + SEND_TH

VERIFY = "1554035272063131758"
WELCOME = "1553269089315725374"

READONLY = [
    "1553269089315725375",  # rules
    "1553269089315725376",  # announcements
    "1553269089315725377",  # roles
    "1553269089810784317",  # clan-stats
    "1553318135614939226",  # war-feed
    "1553269090305572865",  # war-results
    "1553277382620618842",  # clan-feed
    "1553277384235679754",  # donations
    "1553277387565703228",  # raid-weekend
    "1553269090305572873",  # guides
    "1553269090746109993",  # useful-links
    "1553269090746109994",  # game-updates
    "1553313257647767612",  # base-sharing-info
    "1553983640537665606",  # legend-league
    "1554024392491532361",  # electro-feed
]

READWRITE = [
    "1553269090305572868",  # general-chat
    "1553269090305572869",  # memes
    "1553269090305572871",  # attack-strategies
    "1553269089810784322",  # war-strategy
    "1553269090305572866",  # attack-planning
    "1553269090305572864",  # create-remainders
    "1553313243202723860",  # th15
    "1553313247019401306",  # th16
    "1553313250592956556",  # th17
    "1553313254112100392",  # th18
]

STAFF_ONLY = [
    "1553277393169289257",
    "1553278089554038807",
    "1553277394943475872",
    "1553278092309430365",
]

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


def ow(channel: str, role: str, allow: int, deny: int, retries: int = 4) -> bool:
    global ok, fail
    for attempt in range(retries):
        code, body = curl(
            "PUT",
            f"/channels/{channel}/permissions/{role}",
            {"type": 0, "allow": str(allow), "deny": str(deny)},
        )
        if code in ("204", "200"):
            ok += 1
            time.sleep(0.4)
            return True
        if code == "429":
            wait = 3.0
            if isinstance(body, dict):
                wait = float(body.get("retry_after", 3)) + 0.5
            print(f"  rate-limit sleep {wait:.1f}s")
            time.sleep(wait)
            continue
        print(f"  FAIL ch={channel} role={role} {code} {body}")
        fail += 1
        time.sleep(0.4)
        return False
    fail += 1
    return False


def staff(channel: str, has_send: bool) -> None:
    allow = VIEW + HIST + APP + MANAGE_MSG + EMBED
    if has_send:
        allow |= SEND | ATTACH | REACT | SEND_TH
    for role in STAFF_BOTS:
        ow(channel, role, allow, 0)


def main() -> None:
    global ok, fail
    _, roles = curl("GET", f"/guilds/{GUILD}/roles")
    oscar = next(r for r in roles if r["id"] == OSCAR)
    has_send = bool(int(oscar["permissions"]) & SEND)
    bot_perms = int(oscar["permissions"])
    print(f"Oscar SEND={has_send} perms={bot_perms}", flush=True)

    # Only deny permission bits the bot itself currently has
    deny_extra = 0
    for bit in (SEND, PUB_TH, PRIV_TH, SEND_TH):
        if bot_perms & bit:
            deny_extra |= bit
    print(f"deny_extra bits={deny_extra}", flush=True)

    # VERIFY: unverified see it; verified hide
    print("\n#verify", flush=True)
    ow(VERIFY, EVERYONE, VIEW + HIST + APP, 0)
    for role in VERIFIED:
        ow(VERIFY, role, 0, VIEW)
    staff(VERIFY, has_send)

    # WELCOME: everyone can read, no chat if possible
    print("\n#welcome", flush=True)
    ow(WELCOME, EVERYONE, VIEW + HIST + APP, deny_extra)
    for role in VERIFIED:
        ow(WELCOME, role, VIEW + HIST, deny_extra)
    staff(WELCOME, has_send)

    # READ-ONLY after verify
    print("\nRead-only", flush=True)
    for ch in READONLY:
        print(" ", ch, flush=True)
        ow(ch, EVERYONE, 0, VIEW)  # hide from unverified
        for role in VERIFIED:
            ow(ch, role, VIEW + HIST, deny_extra)
        staff(ch, has_send)

    # READ-WRITE after verify
    print("\nRead-write", flush=True)
    for ch in READWRITE:
        print(" ", ch, flush=True)
        ow(ch, EVERYONE, 0, VIEW)  # hide from unverified
        for role in VERIFIED:
            # Grant view; include SEND in allow only if bot has SEND
            allow = VIEW + HIST + APP
            if has_send:
                allow |= SEND | REACT | EMBED | ATTACH
            ow(ch, role, allow, 0)
        staff(ch, has_send)

    # STAFF ONLY
    print("\nStaff-only", flush=True)
    for ch in STAFF_ONLY:
        print(" ", ch, flush=True)
        ow(ch, EVERYONE, 0, VIEW)
        for role in (MEMBER, RECRUIT, WARRIOR, ELDER):
            ow(ch, role, 0, VIEW)
        allow = VIEW + HIST + APP
        if has_send:
            allow |= SEND | REACT | EMBED | ATTACH
        ow(ch, CO, allow, 0)
        staff(ch, has_send)

    # Categories: hide server from unverified except Welcome
    print("\nCategories", flush=True)
    _, chs = curl("GET", f"/guilds/{GUILD}/channels")
    for c in chs:
        if c.get("type") != 4:
            continue
        cid, name = c["id"], c["name"]
        print(" ", name, flush=True)
        if "WELCOME" in name.upper():
            ow(cid, EVERYONE, VIEW + HIST, 0)
            staff(cid, has_send)
        elif "STAFF" in name.upper() or "🔒" in name:
            ow(cid, EVERYONE, 0, VIEW)
            for role in (MEMBER, RECRUIT, WARRIOR, ELDER):
                ow(cid, role, 0, VIEW)
            ow(cid, CO, VIEW + HIST, 0)
            staff(cid, has_send)
        else:
            ow(cid, EVERYONE, 0, VIEW)
            for role in VERIFIED:
                ow(cid, role, VIEW + HIST, 0)
            staff(cid, has_send)

    print(f"\nDONE ok={ok} fail={fail}", flush=True)
    if not has_send:
        print(
            "Bot still missing Send Messages — chat grant/deny incomplete.\n"
            "Authorize then re-run:\n"
            "https://discord.com/oauth2/authorize?client_id=1553274441944010802"
            "&permissions=294473821264&scope=bot%20applications.commands",
            flush=True,
        )


if __name__ == "__main__":
    main()
