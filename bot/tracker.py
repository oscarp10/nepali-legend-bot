from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bot.coc_client import ClanMember, CocClient, RankedBattle
from bot.config import Settings, classify_tier
from bot.db import Database, PlayerRow, legend_day_key

log = logging.getLogger("tracker")


def battle_utc_date(ts: str) -> str:
    """Normalize CoC battleTimestamp to YYYY-MM-DD (UTC)."""
    if not ts:
        return ""
    if len(ts) >= 10 and ts[4] == "-":
        return ts[:10]
    if len(ts) >= 9 and ts[8] == "T":
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    return ts[:10]


@dataclass
class HitEvent:
    player: PlayerRow
    battle: RankedBattle
    bucket: str


@dataclass
class PollResult:
    hits: list[HitEvent]
    buckets_changed: set[str]
    tracked_count: int
    players: list[PlayerRow]


class Tracker:
    def __init__(self, settings: Settings, coc: CocClient, db: Database) -> None:
        self.settings = settings
        self.coc = coc
        self.db = db
        self._bootstrap_done = False

    async def poll(self) -> PollResult:
        day = legend_day_key()
        roster = await self.coc.clan_members(self.settings.clan_tag)

        enriched: list[ClanMember] = []
        sem = asyncio.Semaphore(5)

        async def fetch_one(member: ClanMember) -> ClanMember | None:
            async with sem:
                try:
                    return await self.coc.player(member.tag)
                except Exception:
                    log.exception("Failed player fetch %s", member.tag)
                    return None

        results = await asyncio.gather(*(fetch_one(m) for m in roster))
        for full in results:
            if not full:
                continue
            if classify_tier(full.tier_name, full.league_name):
                enriched.append(full)

        hits: list[HitEvent] = []
        buckets_changed: set[str] = set()
        active_tags: set[str] = set()
        tracked_players: list[PlayerRow] = []
        bootstrap = not self._bootstrap_done

        for member in enriched:
            bucket = classify_tier(member.tier_name, member.league_name)
            if not bucket:
                continue
            active_tags.add(member.tag)

            trophies = member.trophies
            group_rank = None
            season_active = False
            if member.group_tag and member.season_id:
                snap = await self.coc.leaguegroup_snapshot(
                    member.group_tag, member.season_id, member.tag
                )
                if snap["trophies"] is not None:
                    trophies = snap["trophies"]
                group_rank = snap["rank"]
                season_active = bool(snap["season_active"])
            elif not member.group_tag or not member.season_id:
                # No ranked group assigned yet → season/bracket not live for this account
                season_active = False

            prev = await self.db.get_player(member.tag)
            day_net = 0
            day_offense_net = 0
            day_defense_net = 0
            if prev and prev.day_key == day:
                day_net = prev.day_net
                day_offense_net = prev.day_offense_net
                day_defense_net = prev.day_defense_net
            elif prev and prev.day_key != day:
                log.info("Day reset for %s → %s", member.tag, day)

            trophy_delta = 0
            if (
                season_active
                and prev
                and prev.trophies != trophies
                and prev.day_key == day
            ):
                trophy_delta = trophies - prev.trophies
                day_net += trophy_delta

            # Only pull/show battlelog once the ranked group actually has activity.
            # Otherwise CoC still returns old ranked hits from prior days/seasons.
            battles: list[RankedBattle] = []
            new_day_battles: list[RankedBattle] = []
            if season_active:
                try:
                    battles = await self.coc.battlelog(member.tag)
                except Exception:
                    log.exception("Battlelog failed for %s", member.tag)
                    battles = []
            else:
                log.info(
                    "Season not active yet for %s (%s) — skipping battlelog display",
                    member.name,
                    member.tier_name,
                )

            for battle in sorted(battles, key=lambda b: b.battle_timestamp):
                battle_day = battle_utc_date(battle.battle_timestamp) or day
                is_new = not await self.db.has_battle(battle.battle_id)

                await self.db.add_battle(
                    battle_id=battle.battle_id,
                    player_tag=member.tag,
                    battle_timestamp=battle.battle_timestamp,
                    is_attack=battle.is_attack,
                    stars=battle.stars,
                    destruction=battle.destruction,
                    opponent_name=battle.opponent_name,
                    day_key=battle_day,
                    opponent_tag=battle.opponent_tag,
                    opponent_th=battle.opponent_th,
                )

                if bootstrap or not is_new:
                    continue

                if battle_day == day:
                    new_day_battles.append(battle)
                    hits.append(
                        HitEvent(
                            player=PlayerRow(
                                tag=member.tag,
                                name=member.name,
                                trophies=trophies,
                                league_id=member.league_id,
                                league_name=member.league_name,
                                tier_id=member.tier_id,
                                tier_name=member.tier_name,
                                track_bucket=bucket,
                                day_key=day,
                                day_net=day_net,
                                day_attacks=0,
                                day_defenses=0,
                                group_tag=member.group_tag,
                                season_id=member.season_id,
                                group_rank=group_rank,
                                season_active=season_active,
                            ),
                            battle=battle,
                            bucket=bucket,
                        )
                    )
                    buckets_changed.add(bucket)
                    log.info(
                        "%s %s vs %s (%s★ %s%%)",
                        "ATK" if battle.is_attack else "DEF",
                        member.name,
                        battle.opponent_name,
                        battle.stars,
                        battle.destruction,
                    )

            # Attribute trophy swing to offense/defense when a single hit explains it
            if trophy_delta and len(new_day_battles) == 1:
                if new_day_battles[0].is_attack:
                    day_offense_net += trophy_delta
                else:
                    day_defense_net += trophy_delta
            elif trophy_delta and len(new_day_battles) > 1:
                # Split unknown — prefer putting positive swings on attacks
                atk_n = sum(1 for b in new_day_battles if b.is_attack)
                def_n = len(new_day_battles) - atk_n
                if atk_n and not def_n:
                    day_offense_net += trophy_delta
                elif def_n and not atk_n:
                    day_defense_net += trophy_delta
                else:
                    # mixed: keep day_net only; leave split unchanged
                    pass

            if season_active:
                day_battles = await self.db.list_day_battles(member.tag, day)
                day_attacks = sum(1 for b in day_battles if b.is_attack)
                day_defenses = sum(1 for b in day_battles if not b.is_attack)
            else:
                day_attacks = 0
                day_defenses = 0
                day_net = 0
                day_offense_net = 0
                day_defense_net = 0

            row = PlayerRow(
                tag=member.tag,
                name=member.name,
                trophies=trophies,
                league_id=member.league_id,
                league_name=member.league_name,
                tier_id=member.tier_id,
                tier_name=member.tier_name,
                track_bucket=bucket,
                day_key=day,
                day_net=day_net,
                day_attacks=day_attacks,
                day_defenses=day_defenses,
                group_tag=member.group_tag,
                season_id=member.season_id,
                group_rank=group_rank,
                season_active=season_active,
                day_offense_net=day_offense_net,
                day_defense_net=day_defense_net,
            )
            await self.db.upsert_player(row)
            tracked_players.append(row)
            buckets_changed.add(bucket)

        await self.db.prune_missing(active_tags)
        self._bootstrap_done = True

        by_tag = {p.tag: p for p in tracked_players}
        for hit in hits:
            if hit.player.tag in by_tag:
                hit.player = by_tag[hit.player.tag]

        return PollResult(
            hits=hits,
            buckets_changed=buckets_changed,
            tracked_count=len(active_tags),
            players=tracked_players,
        )
