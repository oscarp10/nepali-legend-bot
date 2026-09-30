from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from bot.config import DATA_DIR, DB_PATH, LEGEND_DAY_HOUR_UTC


@dataclass
class PlayerRow:
    tag: str
    name: str
    trophies: int
    league_id: int | None
    league_name: str | None
    tier_id: int | None
    tier_name: str | None
    track_bucket: str
    day_key: str
    day_net: int
    day_attacks: int
    day_defenses: int
    group_tag: str | None = None
    season_id: int | None = None
    group_rank: int | None = None
    season_active: bool = False
    day_offense_net: int = 0
    day_defense_net: int = 0
    badge_url: str | None = None


@dataclass
class BattleRow:
    battle_id: str
    player_tag: str
    battle_timestamp: str
    is_attack: bool
    stars: int
    destruction: int
    opponent_name: str
    day_key: str
    opponent_tag: str | None = None
    opponent_th: int | None = None


def legend_day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.hour < LEGEND_DAY_HOUR_UTC:
        day = now.date().fromordinal(now.date().toordinal() - 1)
    else:
        day = now.date()
    return day.isoformat()


def player_log_meta_key(tag: str) -> str:
    return f"player_log_{tag.lstrip('#')}"


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                tag TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                trophies INTEGER NOT NULL DEFAULT 0,
                league_id INTEGER,
                league_name TEXT,
                tier_id INTEGER,
                tier_name TEXT,
                track_bucket TEXT NOT NULL,
                day_key TEXT NOT NULL,
                day_net INTEGER NOT NULL DEFAULT 0,
                day_attacks INTEGER NOT NULL DEFAULT 0,
                day_defenses INTEGER NOT NULL DEFAULT 0,
                group_tag TEXT,
                season_id INTEGER,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seen_battles (
                battle_id TEXT PRIMARY KEY,
                player_tag TEXT NOT NULL,
                battle_timestamp TEXT NOT NULL,
                is_attack INTEGER NOT NULL,
                stars INTEGER,
                destruction INTEGER,
                opponent_name TEXT,
                day_key TEXT NOT NULL,
                opponent_tag TEXT,
                opponent_th INTEGER
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS discord_links (
                discord_id TEXT PRIMARY KEY,
                player_tag TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        await self._ensure_battle_columns()
        await self._ensure_player_columns()
        await self._db.commit()

    async def _ensure_battle_columns(self) -> None:
        cur = await self.db.execute("PRAGMA table_info(seen_battles)")
        cols = {row["name"] for row in await cur.fetchall()}
        if "opponent_tag" not in cols:
            await self.db.execute(
                "ALTER TABLE seen_battles ADD COLUMN opponent_tag TEXT"
            )
        if "opponent_th" not in cols:
            await self.db.execute(
                "ALTER TABLE seen_battles ADD COLUMN opponent_th INTEGER"
            )

    async def _ensure_player_columns(self) -> None:
        cur = await self.db.execute("PRAGMA table_info(players)")
        cols = {row["name"] for row in await cur.fetchall()}
        for col, decl in (
            ("group_rank", "INTEGER"),
            ("season_active", "INTEGER NOT NULL DEFAULT 0"),
            ("day_offense_net", "INTEGER NOT NULL DEFAULT 0"),
            ("day_defense_net", "INTEGER NOT NULL DEFAULT 0"),
            ("badge_url", "TEXT"),
        ):
            if col not in cols:
                await self.db.execute(f"ALTER TABLE players ADD COLUMN {col} {decl}")

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if not self._db:
            raise RuntimeError("Database not connected")
        return self._db

    def _row_to_player(self, row: aiosqlite.Row) -> PlayerRow:
        keys = set(row.keys())
        return PlayerRow(
            tag=row["tag"],
            name=row["name"],
            trophies=row["trophies"],
            league_id=row["league_id"],
            league_name=row["league_name"],
            tier_id=row["tier_id"],
            tier_name=row["tier_name"],
            track_bucket=row["track_bucket"],
            day_key=row["day_key"],
            day_net=row["day_net"],
            day_attacks=row["day_attacks"],
            day_defenses=row["day_defenses"],
            group_tag=row["group_tag"],
            season_id=row["season_id"],
            group_rank=row["group_rank"] if "group_rank" in keys else None,
            season_active=bool(row["season_active"]) if "season_active" in keys else False,
            day_offense_net=int(row["day_offense_net"] or 0)
            if "day_offense_net" in keys
            else 0,
            day_defense_net=int(row["day_defense_net"] or 0)
            if "day_defense_net" in keys
            else 0,
            badge_url=row["badge_url"] if "badge_url" in keys else None,
        )

    async def get_player(self, tag: str) -> PlayerRow | None:
        cur = await self.db.execute("SELECT * FROM players WHERE tag = ?", (tag,))
        row = await cur.fetchone()
        return self._row_to_player(row) if row else None

    async def upsert_player(self, player: PlayerRow) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO players (
                tag, name, trophies, league_id, league_name, tier_id, tier_name,
                track_bucket, day_key, day_net, day_attacks, day_defenses,
                group_tag, season_id, group_rank, season_active,
                day_offense_net, day_defense_net, badge_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tag) DO UPDATE SET
                name = excluded.name,
                trophies = excluded.trophies,
                league_id = excluded.league_id,
                league_name = excluded.league_name,
                tier_id = excluded.tier_id,
                tier_name = excluded.tier_name,
                track_bucket = excluded.track_bucket,
                day_key = excluded.day_key,
                day_net = excluded.day_net,
                day_attacks = excluded.day_attacks,
                day_defenses = excluded.day_defenses,
                group_tag = excluded.group_tag,
                season_id = excluded.season_id,
                group_rank = excluded.group_rank,
                season_active = excluded.season_active,
                day_offense_net = excluded.day_offense_net,
                day_defense_net = excluded.day_defense_net,
                badge_url = excluded.badge_url,
                updated_at = excluded.updated_at
            """,
            (
                player.tag,
                player.name,
                player.trophies,
                player.league_id,
                player.league_name,
                player.tier_id,
                player.tier_name,
                player.track_bucket,
                player.day_key,
                player.day_net,
                player.day_attacks,
                player.day_defenses,
                player.group_tag,
                player.season_id,
                player.group_rank,
                1 if player.season_active else 0,
                player.day_offense_net,
                player.day_defense_net,
                player.badge_url,
                now,
            ),
        )
        await self.db.commit()

    async def list_bucket(self, bucket: str, day_key: str) -> list[PlayerRow]:
        cur = await self.db.execute(
            """
            SELECT * FROM players
            WHERE track_bucket = ? AND day_key = ?
            ORDER BY
              CASE tier_name
                WHEN 'Legend I' THEN 1
                WHEN 'Legend II' THEN 2
                WHEN 'Legend III' THEN 3
                ELSE 9
              END,
              trophies DESC,
              name COLLATE NOCASE ASC
            """,
            (bucket, day_key),
        )
        rows = await cur.fetchall()
        return [self._row_to_player(r) for r in rows]

    async def has_battle(self, battle_id: str) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM seen_battles WHERE battle_id = ?", (battle_id,)
        )
        return await cur.fetchone() is not None

    async def add_battle(
        self,
        *,
        battle_id: str,
        player_tag: str,
        battle_timestamp: str,
        is_attack: bool,
        stars: int | None,
        destruction: int | None,
        opponent_name: str | None,
        day_key: str,
        opponent_tag: str | None = None,
        opponent_th: int | None = None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO seen_battles (
                battle_id, player_tag, battle_timestamp, is_attack,
                stars, destruction, opponent_name, day_key,
                opponent_tag, opponent_th
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(battle_id) DO UPDATE SET
                day_key = excluded.day_key,
                stars = excluded.stars,
                destruction = excluded.destruction,
                opponent_name = excluded.opponent_name,
                opponent_tag = excluded.opponent_tag,
                opponent_th = excluded.opponent_th
            """,
            (
                battle_id,
                player_tag,
                battle_timestamp,
                1 if is_attack else 0,
                stars,
                destruction,
                opponent_name,
                day_key,
                opponent_tag,
                opponent_th,
            ),
        )
        await self.db.commit()

    def _battle_from_row(self, r: aiosqlite.Row) -> BattleRow:
        keys = set(r.keys())
        return BattleRow(
            battle_id=r["battle_id"],
            player_tag=r["player_tag"],
            battle_timestamp=r["battle_timestamp"],
            is_attack=bool(r["is_attack"]),
            stars=int(r["stars"] or 0),
            destruction=int(r["destruction"] or 0),
            opponent_name=r["opponent_name"] or "Unknown",
            day_key=r["day_key"],
            opponent_tag=r["opponent_tag"] if "opponent_tag" in keys else None,
            opponent_th=r["opponent_th"] if "opponent_th" in keys else None,
        )

    async def list_day_battles(self, player_tag: str, day_key: str) -> list[BattleRow]:
        cur = await self.db.execute(
            """
            SELECT * FROM seen_battles
            WHERE player_tag = ? AND day_key = ?
            ORDER BY battle_timestamp ASC
            """,
            (player_tag, day_key),
        )
        rows = await cur.fetchall()
        return [self._battle_from_row(r) for r in rows]

    async def list_player_battles(
        self, player_tag: str, *, limit: int = 80
    ) -> list[BattleRow]:
        """All stored attacks/defenses for a player (newest last), not split by day."""
        cur = await self.db.execute(
            """
            SELECT * FROM seen_battles
            WHERE player_tag = ?
            ORDER BY battle_timestamp DESC
            LIMIT ?
            """,
            (player_tag, limit),
        )
        rows = await cur.fetchall()
        # Return chronological (oldest → newest) for display
        return [self._battle_from_row(r) for r in reversed(rows)]

    async def get_meta(self, key: str) -> str | None:
        cur = await self.db.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self.db.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.db.commit()

    async def delete_meta_prefix(self, prefix: str) -> None:
        await self.db.execute(
            "DELETE FROM meta WHERE key LIKE ?", (f"{prefix}%",)
        )
        await self.db.commit()

    async def set_discord_link(self, discord_id: int, player_tag: str) -> None:
        tag = player_tag.strip().upper()
        if not tag.startswith("#"):
            tag = f"#{tag}"
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO discord_links (discord_id, player_tag, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                player_tag = excluded.player_tag,
                updated_at = excluded.updated_at
            """,
            (str(discord_id), tag, now),
        )
        await self.db.commit()

    async def get_discord_link(self, discord_id: int) -> str | None:
        cur = await self.db.execute(
            "SELECT player_tag FROM discord_links WHERE discord_id = ?",
            (str(discord_id),),
        )
        row = await cur.fetchone()
        return row["player_tag"] if row else None

    async def prune_missing(self, active_tags: set[str]) -> None:
        if not active_tags:
            await self.db.execute("DELETE FROM players")
            await self.db.commit()
            return
        placeholders = ",".join("?" for _ in active_tags)
        await self.db.execute(
            f"DELETE FROM players WHERE tag NOT IN ({placeholders})",
            tuple(active_tags),
        )
        await self.db.commit()

        cur = await self.db.execute(
            "SELECT key FROM meta WHERE key LIKE 'player_log_%'"
        )
        for row in await cur.fetchall():
            key = row["key"]
            tag = f"#{key.removeprefix('player_log_')}"
            if tag not in active_tags:
                await self.db.execute("DELETE FROM meta WHERE key = ?", (key,))
        await self.db.commit()
