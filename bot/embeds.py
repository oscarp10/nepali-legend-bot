from __future__ import annotations

from datetime import datetime, timezone

import discord

from bot.coc_client import RankedBattle
from bot.db import BattleRow, PlayerRow
from bot.graphics import destruction_bar, progress_bar


ATTACK_COLOR = 0x2ECC71
DEFENSE_COLOR = 0xE74C3C
BOARD_COLOR = 0xC9A227
ELECTRO_BOARD_COLOR = 0x8E44AD
BATTLE_LOG_LEGEND = 0xC9A227
BATTLE_LOG_ELECTRO = 0x7D3C98


def slots_for_tier(tier_name: str | None) -> int:
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


def _tier_color(tier_name: str | None, bucket: str | None = None) -> int:
    name = (tier_name or "").lower()
    if "electro" in name or bucket == "electro":
        return BATTLE_LOG_ELECTRO
    return BATTLE_LOG_LEGEND


def _hit_rate(attacks: list[BattleRow]) -> str:
    if not attacks:
        return "—"
    avg = sum(b.stars for b in attacks) / len(attacks)
    three = sum(1 for b in attacks if b.stars >= 3)
    return f"{avg:.2f}★ avg · {three}/{len(attacks)} three-star"


def hit_embed(*, player: PlayerRow, battle: RankedBattle) -> discord.Embed:
    if battle.is_attack:
        title = f"⚔️ Ranked Attack  {_stars(battle.stars)}"
        color = ATTACK_COLOR
        kind = "Attack"
    else:
        title = f"🛡️ Ranked Defense  {_stars(battle.stars)}"
        color = DEFENSE_COLOR
        kind = "Defense"

    bar = destruction_bar(battle.destruction)
    embed = discord.Embed(
        title=title,
        description=f"`{bar}` **{battle.destruction}%**",
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
    if getattr(player, "badge_url", None):
        embed.set_thumbnail(url=player.badge_url)  # type: ignore[attr-defined]
    embed.set_footer(text=f"Nepali Legend's · Ranked {kind}")
    return embed


def _battle_line(battle: BattleRow) -> str:
    name = battle.opponent_name
    if len(name) > 14:
        name = name[:13] + "…"
    return f"`{_stars(battle.stars)}` **{battle.destruction}%** · {name}"


def _side_column(battles: list[BattleRow], *, empty: str, cap: int) -> str:
    if not battles:
        return empty
    shown = battles[-cap:] if len(battles) > cap else battles
    text = "\n".join(_battle_line(b) for b in shown)
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
    badge_url: str | None = None,
) -> discord.Embed:
    cap = slots_for_tier(player.tier_name)
    tier = player.tier_name or "Ranked"
    rank = f"#{player.group_rank}" if player.group_rank else "—"
    cups = f"{player.trophies:,}" if player.trophies else "0"
    now = datetime.now(timezone.utc)
    color = _tier_color(player.tier_name, player.track_bucket)

    atk_bar = progress_bar(len(attacks), cap)
    def_bar = progress_bar(len(defenses), cap)

    if not player.season_active:
        description = (
            f"**{player.name}**\n"
            f"◇ {tier} · Rank {rank}\n"
            f"`{player.tag}`\n\n"
            f"🏆 **—**\n"
            f"_Season not started yet_"
        )
        atk_body = "No attack performed.\n`+0` 🏆"
        def_body = "No defense received."
        atk_title = f"⚔️ Attacks\n`{atk_bar}`"
        def_title = f"🛡️ Defenses\n`{def_bar}`"
    else:
        description = (
            f"**{player.name}**\n"
            f"◇ {tier} · Rank {rank}\n"
            f"`{player.tag}`\n\n"
            f"🏆 **{cups}**\n"
            f"Day **{_fmt_net(player.day_net)}** · Hit rate {_hit_rate(attacks)}"
        )
        atk_body = _side_column(
            attacks, empty="No attack performed.\n`+0` 🏆", cap=cap
        )
        def_body = _side_column(defenses, empty="No defense received.", cap=cap)
        atk_title = f"⚔️ Attacks · `{_fmt_net(offense_net)}` 🏆\n`{atk_bar}` {len(attacks)}"
        def_title = f"🛡️ Defenses · `{_fmt_net(defense_net)}` 🏆\n`{def_bar}` {len(defenses)}"

    embed = discord.Embed(
        title="🏆  Battle Log",
        description=description,
        color=color,
        timestamp=now,
    )
    embed.add_field(name=atk_title, value=atk_body, inline=True)
    embed.add_field(name=def_title, value=def_body, inline=True)
    if badge_url:
        embed.set_thumbnail(url=badge_url)
    embed.set_footer(text=f"Last refreshed · {day_key} · Nepali Legend's")
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

    active = [p for p in players if p.season_active]
    podium = sorted(active, key=lambda p: p.day_net, reverse=True)[:3]
    podium_lines = []
    medals = ("🥇", "🥈", "🥉")
    for i, p in enumerate(podium):
        podium_lines.append(
            f"{medals[i]} **{p.name}** · day {_fmt_net(p.day_net)} · 🏆 {p.trophies:,}"
        )
    podium_block = "\n".join(podium_lines) if podium_lines else "_No podium yet today._"

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
                bar = progress_bar(p.day_attacks, slots_for_tier(p.tier_name), width=6)
                status = (
                    f"🏆 **{cups}** · day {_fmt_net(p.day_net)}\n"
                    f"　　⚔`{bar}` {p.day_attacks}  🛡{p.day_defenses}"
                )
            lines.append(
                f"`{i:>2}.` **{p.name}** · _{tier}_\n"
                f"　　`{p.tag}` · {status}"
            )
        body = "\n".join(lines)
        if len(body) > 3500:
            body = body[:3500] + "\n…"

    embed = discord.Embed(
        title=title,
        description=f"**Podium**\n{podium_block}\n\n**Roster**\n{body}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Clan", value=f"`{clan_tag}`", inline=True)
    embed.add_field(name="Legend day", value=f"`{day_key}` (05:00 UTC)", inline=True)
    embed.add_field(name="Tracked", value=str(len(players)), inline=True)
    embed.set_footer(text="Read-only feed · /day for digest · Battle Logs below")
    return embed


def ranked_hub_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏆 Ranked Hub — Nepali Legend's",
        description=(
            "Custom tracker for **Legend I / II / III** and **Electro** clan mates "
            "(not the global leaderboard).\n\n"
            "**Battle Log cards** update live — Attack | Defense side by side.\n"
            "Use **Refresh** on a card or `/refresh`.\n"
            "Link your account with `/link #PLAYERTAG` then `/me`.\n\n"
            "ClashPerk still handles verify, donations, wars & CWL."
        ),
        color=BOARD_COLOR,
    )
    embed.add_field(
        name="Commands",
        value="`/player` `/clan` `/day` `/war` `/link` `/me` `/refresh`",
        inline=False,
    )
    embed.set_footer(text="Nepali Legend Tracker")
    return embed


def day_digest_embed(
    *,
    bucket: str,
    players: list[PlayerRow],
    day_key: str,
) -> discord.Embed:
    active = [p for p in players if p.season_active]
    by_net = sorted(active, key=lambda p: p.day_net, reverse=True)[:5]
    by_atk = sorted(active, key=lambda p: p.day_attacks, reverse=True)[:5]
    label = "Legend" if bucket == "legend" else "Electro"
    embed = discord.Embed(
        title=f"📜 {label} Day Digest",
        color=BOARD_COLOR if bucket == "legend" else ELECTRO_BOARD_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    if by_net:
        embed.add_field(
            name="Top day net",
            value="\n".join(
                f"**{p.name}** `{_fmt_net(p.day_net)}`" for p in by_net
            ),
            inline=True,
        )
    if by_atk:
        embed.add_field(
            name="Most attacks",
            value="\n".join(
                f"**{p.name}** `{p.day_attacks}`" for p in by_atk
            ),
            inline=True,
        )
    embed.add_field(
        name="Tracked",
        value=f"**{len(players)}** players · day `{day_key}`",
        inline=False,
    )
    return embed


def player_snapshot_embed(
    *,
    name: str,
    tag: str,
    th: int | None,
    trophies: int,
    tier: str | None,
    league: str | None,
    rank: int | None,
    day_net: int | None,
    badge_url: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔍 {name}",
        description=f"`{tag}` · TH{th or '?'}",
        color=_tier_color(tier),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Trophies", value=f"**{trophies:,}** 🏆", inline=True)
    embed.add_field(name="Tier", value=tier or league or "—", inline=True)
    embed.add_field(
        name="Group rank",
        value=f"#{rank}" if rank else "—",
        inline=True,
    )
    if day_net is not None:
        embed.add_field(name="Day net", value=_fmt_net(day_net), inline=True)
    if badge_url:
        embed.set_thumbnail(url=badge_url)
    embed.set_footer(text="Nepali Legend's · /player")
    return embed
