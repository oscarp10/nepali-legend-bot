from __future__ import annotations

import logging
import os

import certifi
import discord
from discord.ext import commands, tasks

from bot.coc_client import CocClient
from bot.config import Settings, load_settings
from bot.db import Database, legend_day_key, player_log_meta_key
from bot.embeds import battle_log_embed, board_embed, hit_embed
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


class RefreshLogView(discord.ui.View):
    """Attach a Refresh button; clicks are handled in on_interaction."""

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

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.coc.start()
        self.poll_loop.change_interval(seconds=self.settings.poll_interval)
        self.poll_loop.start()

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
        if not self._boards_ready:
            await self._refresh_boards({"legend", "electro"})
            self._boards_ready = True

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

    async def _post_hit(self, event) -> None:
        channel = self.channel_for(event.bucket)
        if not channel:
            return
        embed = hit_embed(player=event.player, battle=event.battle)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("Failed to post hit: %s", exc)

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
                    await message.edit(embed=embed)
                else:
                    message = await channel.send(embed=embed)
                    await self.db.set_meta(meta_key, str(message.id))
                    try:
                        await message.pin(reason="Live ranked day board")
                    except discord.HTTPException:
                        pass
            except discord.HTTPException as exc:
                log.warning("Failed to update %s board: %s", bucket, exc)

    async def _publish_player_log(self, player) -> None:
        channel = self.channel_for(player.track_bucket)
        if not channel:
            return

        day = legend_day_key()
        if player.season_active:
            day_battles = await self.db.list_day_battles(player.tag, day)
            attacks = [b for b in day_battles if b.is_attack]
            defenses = [b for b in day_battles if not b.is_attack]
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
        import asyncio

        for player in players:
            await self._publish_player_log(player)
            # Stay under Discord channel edit rate limits
            await asyncio.sleep(1.2)

    async def refresh_player_card(self, player_tag: str) -> None:
        """Force a poll cycle then republish one player's card."""
        result = await self.tracker.poll()
        player = next((p for p in result.players if p.tag == player_tag), None)
        if player is None:
            # Normalize tag
            want = player_tag if player_tag.startswith("#") else f"#{player_tag}"
            player = next((p for p in result.players if p.tag == want), None)
        if player is None:
            stored = await self.db.get_player(
                player_tag if player_tag.startswith("#") else f"#{player_tag}"
            )
            if not stored:
                raise RuntimeError("Player is not currently tracked in Legend/Electro.")
            player = stored
        await self._publish_player_log(player)

    @tasks.loop(seconds=60)
    async def poll_loop(self) -> None:
        await self.wait_until_ready()
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

        for hit in result.hits:
            await self._post_hit(hit)

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


def main() -> None:
    settings = load_settings()
    bot = LegendBot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
