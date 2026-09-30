from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote
import ssl

import aiohttp
import certifi


@dataclass
class ClanMember:
    tag: str
    name: str
    trophies: int
    league_id: int | None
    league_name: str | None
    tier_id: int | None = None
    tier_name: str | None = None
    group_tag: str | None = None
    season_id: int | None = None
    town_hall: int | None = None
    badge_url: str | None = None


@dataclass
class RankedBattle:
    battle_id: str
    battle_timestamp: str
    is_attack: bool
    stars: int
    destruction: int
    opponent_name: str
    opponent_tag: str | None
    opponent_th: int | None
    battle_type: str


class CocClient:
    def __init__(self, api_base: str, api_key: str | None = None) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=45),
            connector=aiohttp.TCPConnector(ssl=ssl_ctx),
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError("CocClient not started")
        return self._session

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        import asyncio

        url = f"{self.api_base}{path}"
        last_err: Exception | None = None
        for attempt in range(3):
            async with self.session.get(url, params=params) as resp:
                body = await resp.json(content_type=None)
                if resp.status == 200:
                    return body
                reason = (
                    body.get("message")
                    if isinstance(body, dict)
                    else None
                ) or (body.get("reason") if isinstance(body, dict) else None) or body
                last_err = RuntimeError(f"CoC API {resp.status} for {path}: {reason}")
                # ClashKing proxy occasionally 502s — brief backoff then retry
                if resp.status in (429, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(2 + attempt * 3)
                    continue
                raise last_err
        raise last_err or RuntimeError(f"CoC API failed for {path}")

    @staticmethod
    def encode_tag(tag: str) -> str:
        tag = tag.strip().upper()
        if not tag.startswith("#"):
            tag = f"#{tag}"
        return quote(tag, safe="")

    async def clan_members(self, clan_tag: str) -> list[ClanMember]:
        data = await self._get(f"/clans/{self.encode_tag(clan_tag)}/members")
        assert isinstance(data, dict)
        members: list[ClanMember] = []
        for item in data.get("items", []):
            league = item.get("league") or {}
            tier = item.get("leagueTier") or {}
            members.append(
                ClanMember(
                    tag=item["tag"],
                    name=item["name"],
                    trophies=int(item.get("trophies") or 0),
                    league_id=league.get("id"),
                    league_name=league.get("name"),
                    tier_id=tier.get("id"),
                    tier_name=tier.get("name"),
                )
            )
        return members

    async def player(self, player_tag: str) -> ClanMember:
        data = await self._get(f"/players/{self.encode_tag(player_tag)}")
        assert isinstance(data, dict)
        league = data.get("league") or {}
        tier = data.get("leagueTier") or {}
        season = data.get("currentLeagueSeasonId") or 0
        icons = league.get("iconUrls") or {}
        badge = icons.get("medium") or icons.get("small") or icons.get("tiny")
        return ClanMember(
            tag=data["tag"],
            name=data["name"],
            trophies=int(data.get("trophies") or 0),
            league_id=league.get("id"),
            league_name=league.get("name"),
            tier_id=tier.get("id"),
            tier_name=tier.get("name"),
            group_tag=data.get("currentLeagueGroupTag"),
            season_id=int(season) if season else None,
            town_hall=data.get("townHallLevel"),
            badge_url=badge,
        )

    async def clan(self, clan_tag: str) -> dict:
        data = await self._get(f"/clans/{self.encode_tag(clan_tag)}")
        assert isinstance(data, dict)
        return data

    async def current_war(self, clan_tag: str) -> dict | None:
        try:
            data = await self._get(f"/clans/{self.encode_tag(clan_tag)}/currentwar")
        except RuntimeError as exc:
            if "403" in str(exc) or "404" in str(exc):
                return None
            raise
        assert isinstance(data, dict)
        if (data.get("state") or "").lower() in ("notinhwar", "not_in_war"):
            return None
        return data

    async def battlelog(self, player_tag: str) -> list[RankedBattle]:
        data = await self._get(f"/players/{self.encode_tag(player_tag)}/battlelog")
        assert isinstance(data, dict)
        battles: list[RankedBattle] = []
        for item in data.get("items", []):
            if (item.get("battleType") or "").lower() != "ranked":
                continue
            ts = item.get("battleTimestamp") or ""
            is_attack = bool(item.get("attack"))
            opp = item.get("opponentPlayerTag") or ""
            battle_id = f"{player_tag}|{ts}|{'A' if is_attack else 'D'}|{opp}"
            battles.append(
                RankedBattle(
                    battle_id=battle_id,
                    battle_timestamp=ts,
                    is_attack=is_attack,
                    stars=int(item.get("stars") or 0),
                    destruction=int(item.get("destructionPercentage") or 0),
                    opponent_name=item.get("opponentName") or "Unknown",
                    opponent_tag=item.get("opponentPlayerTag"),
                    opponent_th=item.get("opponentTownHallLevel"),
                    battle_type=item.get("battleType") or "ranked",
                )
            )
        return battles

    async def leaguegroup_snapshot(
        self, group_tag: str, season_id: int, player_tag: str
    ) -> dict:
        """Return trophies/rank plus whether the ranked season has real activity."""
        empty = {
            "trophies": None,
            "rank": None,
            "season_active": False,
            "attack_logs": [],
            "defense_logs": [],
        }
        try:
            data = await self._get(
                f"/leaguegroup/{self.encode_tag(group_tag)}/{season_id}",
                params={"playerTag": player_tag},
            )
        except RuntimeError:
            return empty
        assert isinstance(data, dict)
        members = list(data.get("members") or [])
        attack_logs = list(data.get("attackLogs") or [])
        defense_logs = list(data.get("defenseLogs") or [])
        if not members:
            return empty

        members_sorted = sorted(
            members,
            key=lambda m: (
                -(int(m.get("leagueTrophies") or 0)),
                m.get("playerName") or "",
            ),
        )
        trophies = None
        rank = None
        for i, member in enumerate(members_sorted, start=1):
            if member.get("playerTag") == player_tag:
                trophies = int(member.get("leagueTrophies") or 0)
                rank = i
                break

        any_cups = any(int(m.get("leagueTrophies") or 0) > 0 for m in members)
        any_hits = any(
            int(m.get("attackWinCount") or 0)
            + int(m.get("attackLoseCount") or 0)
            + int(m.get("defenseWinCount") or 0)
            + int(m.get("defenseLoseCount") or 0)
            > 0
            for m in members
        )
        season_active = bool(any_cups or any_hits or attack_logs or defense_logs)

        return {
            "trophies": trophies,
            "rank": rank,
            "season_active": season_active,
            "attack_logs": attack_logs,
            "defense_logs": defense_logs,
        }

    async def leaguegroup_member_trophies(
        self, group_tag: str, season_id: int, player_tag: str
    ) -> int | None:
        snap = await self.leaguegroup_snapshot(group_tag, season_id, player_tag)
        return snap["trophies"]
