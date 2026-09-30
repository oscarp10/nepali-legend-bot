#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

TOKEN = json.loads(Path.home().joinpath(".cursor/mcp.json").read_text())[
    "mcpServers"
]["discord"]["env"]["DISCORD_TOKEN"]
API = "https://discord.com/api/v10"
VID = "1554035272063131758"
WID = "1553269089315725374"
OSCAR = "1553274441944010802"
CLASH = "1553270202312163382"
BOT_ALLOW = str(1024 + 2048 + 16384 + 32768 + 65536 + 64 + 2147483648 + 274877906944)


def curl(method, path, data=None):
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


def main():
    code, body = curl(
        "PUT",
        f"/channels/{VID}/permissions/{CLASH}",
        {"type": 0, "allow": BOT_ALLOW, "deny": "0"},
    )
    print("clashperk overwrite", code, body)

    code, msgs = curl("GET", f"/channels/{WID}/messages?limit=20")
    if isinstance(msgs, list):
        for m in msgs:
            author = m.get("author") or {}
            if author.get("id") == OSCAR:
                mid = m.get("id")
                c, _ = curl("DELETE", f"/channels/{WID}/messages/{mid}")
                print("del welcome", mid, c)

    code, body = curl(
        "POST",
        f"/channels/{WID}/messages",
        {
            "embeds": [
                {
                    "title": "Welcome to Nepali Legend's",
                    "color": 15105570,
                    "description": (
                        "Namaste! Official Discord for **Nepali Legend's**\n"
                        "Clan tag: `#R2J28R8Q`\n\n"
                        "### Verify first\n"
                        f"1. Open <#{VID}>\n"
                        "2. Type `/verify` and choose **ClashPerk**\n"
                        "3. Enter your **player** tag and **API token**\n\n"
                        "Token: CoC → Settings → More Settings → API Token\n\n"
                        "Do **not** use Verify threads — only the `#verify` channel."
                    ),
                }
            ]
        },
    )
    print("welcome post", code)

    code, ch = curl("GET", f"/channels/{VID}")
    print("verify", ch.get("name") if isinstance(ch, dict) else ch)
    if isinstance(ch, dict):
        print("overwrites", ch.get("permission_overwrites"))

    subprocess.run(
        ["open", f"discord://-/channels/1553269087864356884/{VID}"],
        check=False,
    )


if __name__ == "__main__":
    main()
