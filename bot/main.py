from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO

import certifi
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.coc_client import CocClient
from bot.config import Settings, load_settings
from bot.db import Database, legend_day_key, player_log_meta_key
from bot.embeds import (
    battle_log_embed,
    board_embed,
    day_digest_embed,
    hit_embed,
    player_snapshot_embed,
    ranked_hub_embed,
)
from bot.graphics import board_banner_png
from bot.tracker import Tracker

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")

LEGEND_CHANNEL_NAME = "legend-league"
ELECTRO_CHANNEL_NAME = "electro-feed"
REFRESH_PREFIX = "nl:refresh:"


def _norm_tag(tag: str) -> str:
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = f"#{tag}"
    return tag


class RefreshLogView(discord.ui.View):
    def __init__(self, player_tag: str) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Refresh",
                emoji="🔄",
                custom_id=f"{REFRESH_PREFIX}{player_tag.lstrip('#')}",
            )
        )


class LegendBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.db = Database()
        self.coc = CocClient(settings.coc_api_base, settings.coc_api_key)
        self.tracker = Tracker(settings, self.coc, self.db)
        self._channel_cache: dict[str, discord.TextChannel] = {}
        self._boards_ready = False
        self._hub_ready = False
        self._last_day_key = legend_day_key()
        self._ready_for_poll = False

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.coc.start()
        self._register_commands()
        try:
            synced = await self.tree.sync(guild=discord.Object(id=self.settings.guild_id))
            log.info("Synced %s slash commands", len(synced))
        except Exception:
            log.exception("Slash sync failed")
        self.poll_loop.change_interval(seconds=self.settings.poll_interval)
        self.poll_loop.start()

    def _register_commands(self) -> None:
        guild = discord.Object(id=self.settings.guild_id)

        @self.tree.command(name="player", description="Look up a Clash player", guild=guild)
        @app_commands.describe(tag="Player tag like #ABC123")
        async def player_cmd(interaction: discord.Interaction, tag: str) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                m = await self.coc.player(_norm_tag(tag))
                stored = await self.db.get_player(m.tag)
                snap = None
                rank = None
                if m.group_tag and m.season_id:
                    snap = await self.coc.leaguegroup_snapshot(
                        m.group_tag, m.season_id, m.tag
                    )
                    rank = snap.get("rank")
                embed = player_snapshot_embed(
                    name=m.name,
                    tag=m.tag,
                    th=m.town_hall,
                    trophies=m.trophies,
                    tier=m.tier_name,
                    league=m.league_name,
                    rank=rank,
                    day_net=stored.day_net if stored else None,
                    badge_url=m.badge_url,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Lookup failed: {exc}", ephemeral=True)

        @self.tree.command(name="clan", description="Clan snapshot", guild=guild)
        async def clan_cmd(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                data = await self.coc.clan(self.settings.clan_tag)
                badge = (data.get("badgeUrls") or {}).get("medium")
                embed = discord.Embed(
                    title=f"🏰 {data.get('name')}",
                    description=(data.get("description") or "")[:400] or "_No description_",
                    color=0xC9A227,
                )
                embed.add_field(name="Tag", value=f"`{data.get('tag')}`", inline=True)
                embed.add_field(
                    name="Members",
                    value=str(data.get("members") or data.get("memberList") and len(data["memberList"]) or "?"),
                    inline=True,
                )
                embed.add_field(
                    name="War wins",
                    value=str(data.get("warWins") or 0),
                    inline=True,
                )
                embed.add_field(
                    name="Level",
                    value=str(data.get("clanLevel") or "?"),
                    inline=True,
                )
                if badge:
                    embed.set_thumbnail(url=badge)
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Clan lookup failed: {exc}", ephemeral=True)

        @self.tree.command(name="day", description="Today's ranked digest", guild=guild)
        @app_commands.describe(bracket="legend or electro")
        @app_commands.choices(
            bracket=[
                app_commands.Choice(name="Legend", value="legend"),
                app_commands.Choice(name="Electro", value="electro"),
            ]
        )
        async def day_cmd(
            interaction: discord.Interaction,
            bracket: app_commands.Choice[str] | None = None,
        ) -> None:
            await interaction.response.defer(ephemeral=True)
            day = legend_day_key()
            bucket = bracket.value if bracket else "legend"
            players = await self.db.list_bucket(bucket, day)
            await interaction.followup.send(
                embed=day_digest_embed(bucket=bucket, players=players, day_key=day),
                ephemeral=True,
            )

        @self.tree.command(name="link", description="Link your Discord to a CoC tag", guild=guild)
        @app_commands.describe(tag="Your player tag")
        async def link_cmd(interaction: discord.Interaction, tag: str) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                m = await self.coc.player(_norm_tag(tag))
                await self.db.set_discord_link(interaction.user.id, m.tag)
                await interaction.followup.send(
                    f"Linked to **{m.name}** `{m.tag}`. Use `/me` anytime.",
                    ephemeral=True,
                )
            except Exception as exc:
                await interaction.followup.send(f"Link failed: {exc}", ephemeral=True)

        @self.tree.command(name="me", description="Your linked player snapshot", guild=guild)
        async def me_cmd(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)
            tag = await self.db.get_discord_link(interaction.user.id)
            if not tag:
                await interaction.followup.send(
                    "No link yet — use `/link #YOURTAG`.", ephemeral=True
                )
                return
            try:
                m = await self.coc.player(tag)
                stored = await self.db.get_player(m.tag)
                rank = None
                if m.group_tag and m.season_id:
                    snap = await self.coc.leaguegroup_snapshot(
                        m.group_tag, m.season_id, m.tag
                    )
                    rank = snap.get("rank")
                embed = player_snapshot_embed(
                    name=m.name,
                    tag=m.tag,
                    th=m.town_hall,
                    trophies=m.trophies,
                    tier=m.tier_name,
                    league=m.league_name,
                    rank=rank,
                    day_net=stored.day_net if stored else None,
                    badge_url=m.badge_url,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Failed: {exc}", ephemeral=True)

        @self.tree.command(name="war", description="Current clan war snapshot", guild=guild)
        async def war_cmd(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                war = await self.coc.current_war(self.settings.clan_tag)
                if not war:
                    await interaction.followup.send(
                        "Clan is not in an active war (or war log is private).",
                        ephemeral=True,
                    )
                    return
                clan = war.get("clan") or {}
                opp = war.get("opponent") or {}
                embed = discord.Embed(
                    title="⚔️ Current War",
                    description=f"**{clan.get('name')}** vs **{opp.get('name')}**",
                    color=0xE74C3C,
                )
                embed.add_field(name="State", value=war.get("state") or "—", inline=True)
                embed.add_field(
                    name="Team size",
                    value=str(war.get("teamSize") or "?"),
                    inline=True,
                )
                embed.add_field(
                    name="Stars",
                    value=f"{clan.get('stars', 0)} – {opp.get('stars', 0)}",
                    inline=True,
                )
                embed.add_field(
                    name="Destruction",
                    value=(
                        f"{clan.get('destructionPercentage', 0):.1f}% – "
                        f"{opp.get('destructionPercentage', 0):.1f}%"
                    ),
                    inline=False,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"War lookup failed: {exc}", ephemeral=True)

        @self.tree.command(name="refresh", description="Refresh a Battle Log card", guild=guild)
        @app_commands.describe(tag="Player tag (optional if /link'd)")
        async def refresh_cmd(
            interaction: discord.Interaction, tag: str | None = None
        ) -> None:
            await interaction.response.defer(ephemeral=True)
            if not tag:
                tag = await self.db.get_discord_link(interaction.user.id)
            if not tag:
                await interaction.followup.send(
                    "Provide a tag or `/link` first.", ephemeral=True
                )
                return
            try:
                await self.refresh_player_card(_norm_tag(tag))
                await interaction.followup.send("Card refreshed.", ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Refresh failed: {exc}", ephemeral=True)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if not custom_id.startswith(REFRESH_PREFIX):
            return
        if interaction.response.is_done():
            return
        tag = "#" + custom_id.removeprefix(REFRESH_PREFIX)
        await interaction.response.defer(ephemeral=True)
        try:
            await self.refresh_player_card(tag)
            await interaction.followup.send("Card refreshed.", ephemeral=True)
        except Exception as exc:
            log.exception("Refresh failed for %s", tag)
            await interaction.followup.send(f"Refresh failed: {exc}", ephemeral=True)

    async def close(self) -> None:
        self.poll_loop.cancel()
        await self.coc.close()
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user and self.user.id)
        log.info("CoC API base: %s", self.settings.coc_api_base)
        guild = self.get_guild(self.settings.guild_id)
        if not guild:
            log.error("Guild %s not found — is the bot invited?", self.settings.guild_id)
            return
        await self._ensure_channels(guild)
        await self._purge_spam_once()
        # Hub → board → one card per player (trophy order)
        if not self._hub_ready:
            await self._ensure_ranked_hub()
            self._hub_ready = True
        if not self._boards_ready:
            await self._refresh_boards({"legend", "electro"})
            self._boards_ready = True
        day = legend_day_key()
        for bucket in ("legend", "electro"):
            players = await self.db.list_bucket(bucket, day)
            players = sorted(
                players,
                key=lambda p: (p.trophies or 0, p.day_net or 0),
                reverse=True,
            )
            for player in players:
                await self._publish_player_log(player)
                await asyncio.sleep(1.0)
        await self._cleanup_pin_notices()
        self._ready_for_poll = True
        log.info("Rebuild finished — polls enabled")

    async def _pin_quiet(self, message: discord.Message, *, reason: str) -> None:
        try:
            await message.pin(reason=reason)
        except discord.HTTPException:
            return
        await asyncio.sleep(0.4)
        try:
            async for msg in message.channel.history(limit=8):
                if msg.type == discord.MessageType.pins_add:
                    try:
                        await msg.delete()
                    except discord.HTTPException:
                        pass
        except discord.HTTPException:
            pass

    async def _cleanup_pin_notices(self) -> None:
        for bucket in ("legend", "electro"):
            channel = self.channel_for(bucket)
            if not channel:
                continue
            try:
                async for msg in channel.history(limit=40):
                    empty = not msg.content and not msg.embeds and not msg.attachments
                    if msg.type == discord.MessageType.pins_add or empty:
                        try:
                            await msg.delete()
                            await asyncio.sleep(0.25)
                        except discord.HTTPException:
                            pass
            except discord.HTTPException:
                pass

    async def _purge_spam_once(self) -> None:
        """Wipe ranked channels once, then rebuild hub + board + one card/player."""
        flag = await self.db.get_meta("single_card_mode_v3")
        if flag == "done":
            return
        log.info("Purging ranked channels for single-card mode…")
        for bucket in ("legend", "electro"):
            channel = self.channel_for(bucket)
            if not channel:
                continue
            try:
                async for pinned in channel.pins():
                    try:
                        await pinned.unpin(reason="Single-card rebuild")
                    except discord.HTTPException:
                        pass
            except discord.HTTPException:
                pass

            deleted = 0
            while True:
                batch: list[discord.Message] = []
                async for msg in channel.history(limit=100):
                    batch.append(msg)
                if not batch:
                    break
                young = [
                    m
                    for m in batch
                    if (discord.utils.utcnow() - m.created_at).days < 14
                ]
                old = [m for m in batch if m not in young]
                try:
                    if len(young) >= 2:
                        await channel.delete_messages(young)
                        deleted += len(young)
                    else:
                        for m in young:
                            await m.delete()
                            deleted += 1
                            await asyncio.sleep(0.35)
                except discord.HTTPException:
                    for m in young:
                        try:
                            await m.delete()
                            deleted += 1
                        except discord.HTTPException:
                            pass
                        await asyncio.sleep(0.35)
                for m in old:
                    try:
                        await m.delete()
                        deleted += 1
                    except discord.HTTPException:
                        pass
                    await asyncio.sleep(0.4)
                if len(batch) < 100:
                    break
            log.info("Purged %s messages from #%s", deleted, channel.name)

        await self.db.delete_meta_prefix("player_log_")
        await self.db.delete_meta_prefix("board_message_")
        await self.db.delete_meta_prefix("ranked_hub_")
        await self.db.set_meta("single_card_mode_v3", "done")
        self._boards_ready = False
        self._hub_ready = False
        log.info("Single-card purge complete — rebuilding…")
    async def _ensure_channels(self, guild: discord.Guild) -> None:
        legend = None
        electro = None

        if self.settings.legend_channel_id:
            ch = guild.get_channel(self.settings.legend_channel_id)
            if isinstance(ch, discord.TextChannel):
                legend = ch

        if self.settings.electro_channel_id:
            ch = guild.get_channel(self.settings.electro_channel_id)
            if isinstance(ch, discord.TextChannel):
                electro = ch

        if legend is None:
            legend = discord.utils.get(guild.text_channels, name=LEGEND_CHANNEL_NAME)
        if electro is None:
            electro = discord.utils.get(guild.text_channels, name=ELECTRO_CHANNEL_NAME)

        if electro is None:
            category = legend.category if legend else discord.utils.get(
                guild.categories, name="Ranked Leaderboard"
            )
            try:
                electro = await guild.create_text_channel(
                    ELECTRO_CHANNEL_NAME,
                    category=category,
                    topic="Auto feed for Electro League ranked attacks & defenses",
                    reason="Nepali Legend Tracker setup",
                )
                log.info("Created #%s (%s)", ELECTRO_CHANNEL_NAME, electro.id)
            except discord.Forbidden:
                log.error("Missing permission to create #%s", ELECTRO_CHANNEL_NAME)

        if legend:
            self._channel_cache["legend"] = legend
            log.info("Legend channel: #%s (%s)", legend.name, legend.id)
        else:
            log.error("Could not find #%s", LEGEND_CHANNEL_NAME)

        if electro:
            self._channel_cache["electro"] = electro
            log.info("Electro channel: #%s (%s)", electro.name, electro.id)

    def channel_for(self, bucket: str) -> discord.TextChannel | None:
        return self._channel_cache.get(bucket)

    def log_view(self, player_tag: str) -> RefreshLogView:
        return RefreshLogView(player_tag)

    async def _ensure_ranked_hub(self) -> None:
        for bucket in ("legend", "electro"):
            channel = self.channel_for(bucket)
            if not channel:
                continue
            meta_key = f"ranked_hub_{bucket}"
            msg_id = await self.db.get_meta(meta_key)
            if msg_id:
                try:
                    await channel.fetch_message(int(msg_id))
                    continue
                except (discord.NotFound, discord.HTTPException):
                    pass
            try:
                msg = await channel.send(embed=ranked_hub_embed())
                await self.db.set_meta(meta_key, str(msg.id))
                await self._pin_quiet(msg, reason="Ranked Hub")
            except discord.HTTPException as exc:
                log.warning("Hub post failed in %s: %s", bucket, exc)

    async def _post_hit(self, event) -> None:
        # Intentionally no channel spam — hits only update the player's live card.
        return

    async def _maybe_day_reset(self, players) -> None:
        day = legend_day_key()
        if day == self._last_day_key:
            return
        prev = self._last_day_key
        self._last_day_key = day
        await self.db.set_meta("last_legend_day", day)
        log.info("Legend day rolled %s → %s", prev, day)
        # Refresh boards only (no extra announcement posts)
        await self._refresh_boards({"legend", "electro"})

    async def _refresh_boards(self, buckets: set[str]) -> None:
        day = legend_day_key()
        for bucket in buckets:
            channel = self.channel_for(bucket)
            if not channel:
                continue
            players = await self.db.list_bucket(bucket, day)
            embed = board_embed(
                bucket=bucket,
                players=players,
                clan_tag=self.settings.clan_tag,
                day_key=day,
            )

            active = [p for p in players if p.season_active]
            podium = [
                (p.name, p.day_net)
                for p in sorted(active, key=lambda x: x.day_net, reverse=True)[:3]
            ]
            title = "Legend Day" if bucket == "legend" else "Electro Day"
            accent = (201, 162, 39) if bucket == "legend" else (142, 68, 173)
            banner = board_banner_png(
                title=title,
                clan_tag=self.settings.clan_tag,
                day_key=day,
                podium=podium,
                accent=accent,
            )
            file = discord.File(BytesIO(banner), filename=f"{bucket}_day.png")
            embed.set_image(url=f"attachment://{bucket}_day.png")

            meta_key = f"board_message_{bucket}"
            msg_id = await self.db.get_meta(meta_key)
            message = None
            if msg_id:
                try:
                    message = await channel.fetch_message(int(msg_id))
                except (discord.NotFound, discord.HTTPException):
                    message = None

            try:
                if message:
                    await message.edit(embed=embed, attachments=[file])
                else:
                    message = await channel.send(embed=embed, file=file)
                    await self.db.set_meta(meta_key, str(message.id))
                    await self._pin_quiet(message, reason="Live ranked day board")
            except discord.HTTPException as exc:
                log.warning("Failed to update %s board: %s", bucket, exc)

            # Channel topic
            try:
                await channel.edit(
                    topic=f"{title} {day} · {len(players)} tracked · /day for digest"
                )
            except discord.HTTPException:
                pass

    async def _publish_player_log(self, player) -> None:
        channel = self.channel_for(player.track_bucket)
        if not channel:
            return

        day = legend_day_key()
        if player.season_active:
            # Full log on one card — not split by legend day
            all_battles = await self.db.list_player_battles(player.tag, limit=80)
            attacks = [b for b in all_battles if b.is_attack]
            defenses = [b for b in all_battles if not b.is_attack]
        else:
            attacks = []
            defenses = []

        embed = battle_log_embed(
            player=player,
            attacks=attacks,
            defenses=defenses,
            day_key=day,
            offense_net=player.day_offense_net,
            defense_net=player.day_defense_net,
            badge_url=player.badge_url,
        )
        view = self.log_view(player.tag)

        meta_key = player_log_meta_key(player.tag)
        msg_id = await self.db.get_meta(meta_key)
        message = None
        if msg_id:
            try:
                message = await channel.fetch_message(int(msg_id))
            except (discord.NotFound, discord.HTTPException):
                message = None

        try:
            if message:
                await message.edit(embed=embed, view=view)
            else:
                message = await channel.send(embed=embed, view=view)
                await self.db.set_meta(meta_key, str(message.id))
        except discord.HTTPException as exc:
            log.warning("Failed player log for %s: %s", player.tag, exc)

    async def _refresh_player_logs(self, players) -> None:
        for player in players:
            await self._publish_player_log(player)
            await asyncio.sleep(1.2)

    async def refresh_player_card(self, player_tag: str) -> None:
        result = await self.tracker.poll()
        want = _norm_tag(player_tag)
        player = next((p for p in result.players if p.tag == want), None)
        if player is None:
            stored = await self.db.get_player(want)
            if not stored:
                raise RuntimeError("Player is not currently tracked in Legend/Electro.")
            player = stored
        await self._publish_player_log(player)

    @tasks.loop(seconds=60)
    async def poll_loop(self) -> None:
        await self.wait_until_ready()
        if not self._ready_for_poll:
            return
        if not self._channel_cache:
            guild = self.get_guild(self.settings.guild_id)
            if guild:
                await self._ensure_channels(guild)
            if not self._channel_cache:
                return

        try:
            result = await self.tracker.poll()
        except Exception:
            log.exception("Poll failed")
            return

        await self._maybe_day_reset(result.players)

        # Hits only update the live player card (no new messages)
        if result.buckets_changed:
            await self._refresh_boards(result.buckets_changed)

        if result.players:
            await self._refresh_player_logs(result.players)

        log.info(
            "Poll ok — tracked=%s hits=%s logs=%s",
            result.tracked_count,
            len(result.hits),
            len(result.players),
        )

    @poll_loop.before_loop
    async def before_poll(self) -> None:
        await self.wait_until_ready()
        stored = await self.db.get_meta("last_legend_day")
        if stored:
            self._last_day_key = stored


def main() -> None:
    settings = load_settings()
    bot = LegendBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
