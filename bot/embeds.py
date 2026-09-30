from __future__ import annotations

from datetime import datetime, timezone

import discord

from bot.coc_client import RankedBattle
from bot.db import BattleRow, PlayerRow


ATTACK_COLOR = 0x2ECC71
DEFENSE_COLOR = 0xE74C3C
BOARD_COLOR = 0xF1C40F
ELECTRO_BOARD_COLOR = 0x9B59B6
# CoC stone / gold panel
BATTLE_LOG_COLOR = 0xB8894A


def slots_for_tier(tier_name: str | None) -> int:
    """Daily attack/defense allotment by ranked tier (internal cap only)."""
    name = (tier_name or "").strip().lower()
    if name == "legend i":
        return 36
    if name == "legend ii":
        return 30
    if name == "legend iii":
        return 24
    if name.startswith("electro"):
        return 18
    if "legend" in name:
        return 24
    return 8


def _fmt_net(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)


def _stars(n: int) -> str:
    filled = max(0, min(3, n))
    return "★" * filled + "☆" * (3 - filled)


def hit_embed(*, player: PlayerRow, battle: RankedBattle) -> discord.Embed:
    if battle.is_attack:
        title = f"⚔️ Ranked Attack  {_stars(battle.stars)}"
        color = ATTACK_COLOR
        kind = "Attack"
    else:
        title = f"🛡️ Ranked Defense  {_stars(battle.stars)}"
        color = DEFENSE_COLOR
        kind = "Defense"

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Player",
        value=f"**{player.name}**\n`{player.tag}`\n{player.tier_name or '—'}",
        inline=True,
    )
    embed.add_field(
        name="Opponent",
        value=(
            f"**{battle.opponent_name}**\n"
            f"`{battle.opponent_tag or '—'}`\n"
            f"TH{battle.opponent_th or '?'}"
        ),
        inline=True,
    )
    embed.add_field(
        name="Result",
        value=f"**{battle.stars}★** · **{battle.destruction}%**",
        inline=True,
    )
    embed.set_footer(text=f"Nepali Legend's · Ranked {kind} · {battle.battle_timestamp}")
    return embed


def _battle_line(battle: BattleRow) -> str:
    """One CoC-style slot row."""
    name = battle.opponent_name
    if len(name) > 14:
        name = name[:13] + "…"
    return f"`{_stars(battle.stars)}` **{battle.destruction}%** · {name}"


def _side_column(
    battles: list[BattleRow],
    *,
    empty: str,
    cap: int,
) -> str:
    """Growing list — one empty placeholder when none, then fills as hits land."""
    if not battles:
        return empty
    shown = battles[-cap:] if len(battles) > cap else battles
    lines = [_battle_line(b) for b in shown]
    text = "\n".join(lines)
    if len(text) > 1024:
        text = text[:1020] + "…"
    return text


def battle_log_embed(
    *,
    player: PlayerRow,
    attacks: list[BattleRow],
    defenses: list[BattleRow],
    day_key: str,
    offense_net: int = 0,
    defense_net: int = 0,
) -> discord.Embed:
    """CoC-style Battle Log: header + Attack | Defense side by side."""
    cap = slots_for_tier(player.tier_name)
    tier = player.tier_name or "Ranked"
    rank = f"#{player.group_rank}" if player.group_rank else "—"
    cups = f"{player.trophies:,}" if player.trophies else "0"
    now = datetime.now(timezone.utc)

    if not player.season_active:
        description = (
            f"**{player.name}**\n"
            f"{tier} · Rank {rank}\n"
            f"`{player.tag}`\n\n"
            f"🏆 **—**\n"
            f"_Season not started yet_"
        )
        atk_body = "No attack performed.\n`+0` 🏆"
        def_body = "No defense received."
        atk_title = "⚔️ Attacks"
        def_title = "🛡️ Defenses"
    else:
        description = (
            f"**{player.name}**\n"
            f"{tier} · Rank {rank}\n"
            f"`{player.tag}`\n\n"
            f"🏆 **{cups}**\n"
            f"Day **{_fmt_net(player.day_net)}**"
        )
        atk_body = _side_column(
            attacks,
            empty="No attack performed.\n`+0` 🏆",
            cap=cap,
        )
        def_body = _side_column(
            defenses,
            empty="No defense received.",
            cap=cap,
        )
        atk_title = f"⚔️ Attacks · `{_fmt_net(offense_net)}` 🏆"
        def_title = f"🛡️ Defenses · `{_fmt_net(defense_net)}` 🏆"

    embed = discord.Embed(
        title="🏆  Battle Log",
        description=description,
        color=BATTLE_LOG_COLOR,
        timestamp=now,
    )
    # Side-by-side like in-game Attack | Defense columns
    embed.add_field(name=atk_title, value=atk_body, inline=True)
    embed.add_field(name=def_title, value=def_body, inline=True)
    embed.set_footer(text=f"Last refreshed · {day_key}")
    return embed


def board_embed(
    *,
    bucket: str,
    players: list[PlayerRow],
    clan_tag: str,
    day_key: str,
) -> discord.Embed:
    is_legend = bucket == "legend"
    title = (
        "🏆 Legend I / II / III — Live Day Board"
        if is_legend
        else "⚡ Electro League — Live Day Board"
    )
    color = BOARD_COLOR if is_legend else ELECTRO_BOARD_COLOR

    if not players:
        body = "_No clan members in this bracket right now._"
    else:
        lines: list[str] = []
        for i, p in enumerate(players, start=1):
            tier = p.tier_name or "—"
            if not p.season_active:
                status = "⏳ season not started"
            else:
                cups = f"{p.trophies:,}" if p.trophies else "0"
                status = (
                    f"🏆 **{cups}** · ⚔{p.day_attacks} 🛡{p.day_defenses}"
                    f" · day {_fmt_net(p.day_net)}"
                )
            lines.append(
                f"`{i:>2}.` **{p.name}** · _{tier}_\n"
                f"　　`{p.tag}` · {status}"
            )
        body = "\n".join(lines)
        if len(body) > 3900:
            body = body[:3900] + "\n…"

    embed = discord.Embed(
        title=title,
        description=body,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Clan", value=f"`{clan_tag}`", inline=True)
    embed.add_field(name="Legend day", value=f"`{day_key}` (05:00 UTC)", inline=True)
    embed.add_field(name="Tracked", value=str(len(players)), inline=True)
    embed.set_footer(text="Read-only feed · personal Battle Logs update below")
    return embed
