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
BATTLE_LOG_LEGEND = 0xD4A017
BATTLE_LOG_ELECTRO = 0x9B59B6


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
    return f"{avg:.2f}★ · {three}× 3★"


def hit_embed(*, player: PlayerRow, battle: RankedBattle) -> discord.Embed:
    """Unused for channel spam — kept for optional future use."""
    color = ATTACK_COLOR if battle.is_attack else DEFENSE_COLOR
    kind = "Attack" if battle.is_attack else "Defense"
    embed = discord.Embed(
        title=f"{'⚔️' if battle.is_attack else '🛡️'} {kind}  {_stars(battle.stars)}",
        description=f"`{destruction_bar(battle.destruction)}` **{battle.destruction}%**",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Player", value=f"**{player.name}**", inline=True)
    embed.add_field(name="Opponent", value=f"**{battle.opponent_name}**", inline=True)
    return embed


def _battle_line(battle: BattleRow, *, latest: bool = False) -> str:
    name = battle.opponent_name
    if len(name) > 16:
        name = name[:15] + "…"
    prefix = "▸ " if latest else "· "
    return (
        f"{prefix}`{_stars(battle.stars)}` **{battle.destruction}%** · **{name}**"
        + (f" · TH{battle.opponent_th}" if battle.opponent_th else "")
    )


def _side_column(battles: list[BattleRow], *, empty: str, cap: int) -> str:
    if not battles:
        return empty
    shown = battles[-cap:] if len(battles) > cap else battles
    lines = []
    for i, b in enumerate(shown):
        lines.append(_battle_line(b, latest=(i == len(shown) - 1)))
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
    badge_url: str | None = None,
) -> discord.Embed:
    """Single live card per player — full attack/defense log, edited in place."""
    # How many lines fit in a Discord field (~1024 chars)
    show_cap = 14
    tier = player.tier_name or "Ranked"
    rank = f"#{player.group_rank}" if player.group_rank else "—"
    cups = f"{player.trophies:,}" if player.trophies else "0"
    now = datetime.now(timezone.utc)
    color = _tier_color(player.tier_name, player.track_bucket)

    atk_n, def_n = len(attacks), len(defenses)

    if attacks or defenses:
        pool = list(attacks) + list(defenses)
        latest = max(pool, key=lambda b: b.battle_timestamp)
        latest_txt = (
            f"{'⚔️' if latest.is_attack else '🛡️'} {_stars(latest.stars)} "
            f"**{latest.destruction}%** vs **{latest.opponent_name}**"
        )
    else:
        latest_txt = "_No ranked hits yet_"

    if not player.season_active:
        description = (
            f"**{tier}** · Rank {rank}\n"
            f"`{player.tag}`\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⏳ **Season not started** — card stays ready"
        )
        atk_body = "▫ waiting…"
        def_body = "▫ waiting…"
    else:
        description = (
            f"**{tier}** · Rank {rank}\n"
            f"`{player.tag}`\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"### 🏆 {cups}\n"
            f"**Avg** {_hit_rate(attacks)} · **Today** {_fmt_net(player.day_net)}\n"
            f"**Last** · {latest_txt}"
        )
        atk_body = _side_column(attacks, empty="▫ No attacks yet", cap=show_cap)
        def_body = _side_column(defenses, empty="▫ No defenses yet", cap=show_cap)

    embed = discord.Embed(
        title=player.name,
        description=description,
        color=color,
        timestamp=now,
    )
    embed.add_field(
        name=f"⚔️ Attacks · {atk_n}",
        value=atk_body,
        inline=True,
    )
    embed.add_field(
        name=f"🛡️ Defenses · {def_n}",
        value=def_body,
        inline=True,
    )
    if badge_url:
        embed.set_thumbnail(url=badge_url)
        embed.set_author(name="Nepali Legend's · Live Battle Log", icon_url=badge_url)
    else:
        embed.set_author(name="Nepali Legend's · Live Battle Log")
    embed.set_footer(text="All hits on one card · updates in place")
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
    medals = ("🥇", "🥈", "🥉")
    podium_lines = [
        f"{medals[i]} **{p.name}** · day {_fmt_net(p.day_net)} · 🏆 {p.trophies:,}"
        for i, p in enumerate(podium)
    ]
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
    embed.set_footer(text="One live card per player below · no spam posts")
    return embed


def ranked_hub_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏆 Ranked Hub — Nepali Legend's",
        description=(
            "Each player has **one live Battle Log card** that updates in place "
            "(attacks & defenses appear on the card — no spam).\n\n"
            "Use **Refresh** on a card or `/refresh`.\n"
            "`/link #TAG` → `/me` for your snapshot.\n\n"
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
            value="\n".join(f"**{p.name}** `{_fmt_net(p.day_net)}`" for p in by_net),
            inline=True,
        )
    if by_atk:
        embed.add_field(
            name="Most attacks",
            value="\n".join(f"**{p.name}** `{p.day_attacks}`" for p in by_atk),
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
    embed.add_field(name="Group rank", value=f"#{rank}" if rank else "—", inline=True)
    if day_net is not None:
        embed.add_field(name="Day net", value=_fmt_net(day_net), inline=True)
    if badge_url:
        embed.set_thumbnail(url=badge_url)
    embed.set_footer(text="Nepali Legend's · /player")
    return embed
