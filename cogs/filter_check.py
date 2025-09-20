import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime, timezone
import aiohttp
import logging
import sqlite3
import os
import matplotlib.pyplot as plt
import io

# --- Configuration ---
REQUEST_TIMEOUT = 1  # seconds
BADGE_FETCH_DELAY = 0.1  # seconds
MAX_CONCURRENT_REQUESTS = 5
FILTER_CHANNEL_ID = {
    1322753191749615626: 1383949901091700808,  # [TGR] PEACEKEEPER ACADEMY
    1309981030790463529: 1417970716636086312  # Test server

}
MAIN_GROUP = 34755744
MAIN_DIVISIONS = [35678586, 35536880, 34815619, 34815613, 34899357]
SUB_DIVISIONS = [35335293, 35586073, 35250103]
INTELLIGENCE_GROUPS = []

# --- Trello Configuration ---
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD_ID = "5bbOw9f8"
MAJOR_BLACKLIST_CATEGORIES = [
    "Universal Blacklists",
    "Cuff Division Blacklist",
    "Command Blacklists"
]
SKIP_CATEGORIES = ["Appealed/Expired"]


# --- Error helpers & setup ---
logger = logging.getLogger(__name__)

ERROR_WEBHOOK_URL = os.getenv("ERROR_WEBHOOK_URL")


async def report_error(interaction: discord.Interaction | None, message: str, level: str = "error", user_message: str | None = None):
    """
    Unified error/warning reporter.
    Sends to logger, webhook, and optionally Discord interaction.
    level: "warning" | "error"
    """
    if level.lower() == "warning":
        logger.warning(message)
    elif level.lower() == "info":
        logger.info(message)
    else:
        logger.error(message)

    if ERROR_WEBHOOK_URL:
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(
                    ERROR_WEBHOOK_URL,
                    json={"content": f"⚠️ {level.upper()}: {message}"},
                )
            except Exception as e:
                logger.error(f"Failed to send error webhook: {e}")

    if interaction:
        try:
            msg = user_message or "⚠️ An error has occurred, please try again."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.edit_original_response(content=msg)
        except Exception as e:
            logger.error(f"Failed to send ephemeral error message: {e}")

# --- Roblox & Discord helpers ---


async def fetch_roblox_user_data(session: aiohttp.ClientSession, username: str, interaction: discord.Interaction | None = None):
    """Fetch comprehensive Roblox user data with improved error handling and rate limiting."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    user_id = None

    try:
        async with session.post(f"https://users.roblox.com/v1/usernames/users", json={"usernames": [username]}, timeout=timeout) as res:
            if res.status != 200:
                await report_error(interaction, f"Failed to fetch user ID for Roblox username {username}: status {res.status}", level="error")
                return None

            data = await res.json()
            if not data.get("data"):
                await report_error(interaction, f"Roblox user **{username}** not found.", user_message=f"❌ Roblox user **{username}** not found.", level="error")
                return None

            user_id = data["data"][0]["id"]

        # Fetch basic user info
        async with session.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=timeout) as res:
            if res.status == 404:
                await report_error(interaction, f"Roblox user with ID {user_id} not found. (404)", user_message=f"❌ Roblox user with ID **{user_id}** was not found.", level="error")
                return None
            if res.status != 200:
                await report_error(interaction, f"Failed to fetch user info for Roblox ID {user_id}: status {res.status}", level="error")
                return None
            data = await res.json()
            username = data.get("name")
            created_str = data.get("created")

            if not username or not created_str:
                await report_error(interaction, f"Invalid user data for Roblox ID {user_id}", level="error")
                return None

            created_date = datetime.fromisoformat(
                created_str.replace("Z", "+00:00"))
            account_age_days = (datetime.now(timezone.utc) - created_date).days

        # Fetch social stats
        followers = await fetch_social_count(session, user_id, "followers", timeout, interaction)
        following = await fetch_social_count(session, user_id, "followings", timeout, interaction)
        friends = await fetch_social_count(session, user_id, "friends", timeout, interaction)

        # Fetch badges
        badges, badge_count = await fetch_user_badges_with_count(session, user_id)
        badge_pages = (badge_count + 29) // 30

        return {
            "username": username,
            "user_id": user_id,
            "account_age_days": account_age_days,
            "account_created__date": created_date,
            "followers": followers,
            "following": following,
            "friends": friends,
            "badge_count": badge_count,
            "badge_pages": badge_pages
        }
    except asyncio.TimeoutError:
        await report_error(interaction, f"Timeout fetching data for Roblox user **{username} ({user_id})**", level="error")
        return None
    except Exception as e:
        await report_error(interaction, f"Error fetching data for Roblox ID {user_id}: {e}", level="error")
        return None


async def fetch_social_count(session: aiohttp.ClientSession, user_id: int, endpoint: str, timeout: aiohttp.ClientTimeout, interaction: discord.Interaction | None = None) -> int:
    """Fetch social count (followers/following/friends) with error handling."""
    try:
        async with session.get(f"https://friends.roblox.com/v1/users/{user_id}/{endpoint}/count", timeout=timeout) as res:
            if res.status == 200:
                data = await res.json()
                return data.get("count", 0)
            else:
                await report_error(interaction, f"Error fetching {endpoint} for user {user_id}: status {res.status}", level="error")
                return 0
    except Exception as e:
        await report_error(interaction, f"Error fetching {endpoint} for user {user_id}: {e}", level="error")
        return 0


async def fetch_user_badges_with_count(session: aiohttp.ClientSession, user_id: int, interaction: discord.Interaction | None = None):
    """
    Fetch all badges for a user with their creation dates,
    and also return the total badge count.
    """
    badges = []
    badge_count = 0
    cursor = None
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    try:
        while True:
            url = f"https://badges.roblox.com/v1/users/{user_id}/badges?limit=100"
            if cursor:
                url += f"&cursor={cursor}"

            async with session.get(url, timeout=timeout) as res:
                if res.status != 200:
                    await report_error(interaction, f"Failed to fetch badges for user {user_id}: {res.status}", level="error")
                    break

                data = await res.json()
                badges_data = data.get("data", [])
                badge_count += len(badges_data)

                # Collect badge names and creation dates
                for badge in badges_data:
                    if "created" in badge:
                        badges.append({
                            "name": badge["name"],
                            "creation_date": datetime.fromisoformat(badge["created"].replace("Z", "+00:00"))
                        })

                cursor = data.get("nextPageCursor")
                if not cursor:
                    break

                await asyncio.sleep(BADGE_FETCH_DELAY)

    except Exception as e:
        await report_error(interaction, f"Error fetching badges for user {user_id}: {e}", level="error")

    return badges, badge_count


async def generate_badge_growth_graph(badges, account_created_date, username, user_id, interaction: discord.Interaction | None = None):
    """Create a step graph of cumulative badge growth and return a BytesIO object."""
    if not badges:
        await report_error(interaction, f"No badges to generate graph for {username} ({user_id}).", level="warning")
        return None

    valid_badges = [b for b in badges if b["creation_date"]
                    > account_created_date]
    # for badge in badges:
    #     if badge["creation_date"] > account_created_date:
    #         valid_badges.append(badge)

    if not valid_badges:
        await report_error(interaction, f"No valid badges after filtering by account creation for {username} ({user_id}).", level="warning")
        return None

    valid_badges.sort(key=lambda x: x["creation_date"])
    dates = [account_created_date] + [b["creation_date"] for b in valid_badges]
    cumulative = [0] + list(range(1, len(valid_badges) + 1))

    try:
        plt.figure(figsize=(10, 5))
        plt.step(dates, cumulative, where='post', color='green')
        plt.xlabel("Date")
        plt.ylabel("Cumulative Badges")
        plt.title(f"{username} ({user_id}) Badge Growth")
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        return buf

    except Exception as e:
        await report_error(interaction, f"Error generating badge graph for {username} ({user_id}): {e}", level="error")
        return None


async def get_user_divisions(session: aiohttp.ClientSession, roblox_id: int, interaction: discord.Interaction | None = None) -> tuple[
        list[tuple[str, str]], list[tuple[str, str]], tuple[str, str] | None, list[tuple[str, str]]]:
    """Check if the user is in any of the main or sub divisions."""
    url = f"https://groups.roblox.com/v1/users/{roblox_id}/groups/roles"
    try:
        async with session.get(url) as res:
            if res.status != 200:
                await report_error(interaction, f"Failed to fetch Trello board: status {res.status}", level="warning")
                return [], [], None, []

            data = await res.json()
            groups = data.get("data", [])

        main_divisions = []
        sub_divisions = []
        main_group = None
        intelligence_groups = []

        for group_info in groups:
            group_id = group_info["group"]["id"]
            group_name = group_info["group"]["name"]
            role_name = group_info["role"]["name"]

            if group_id in MAIN_DIVISIONS:
                main_divisions.append((group_name, role_name))

            if group_id in SUB_DIVISIONS:
                sub_divisions.append((group_name, role_name))

            if group_id == MAIN_GROUP:
                main_group = (group_name, role_name)

            if "intelligence" in group_name.lower() or "intelligence" in role_name.lower():
                intelligence_groups.append((group_name, role_name))

        return main_divisions, sub_divisions, main_group, intelligence_groups

    except Exception as e:
        await report_error(interaction, f"Exception fetching groups for user {roblox_id}: {e}", level="error")
        return [], [], None, []


async def fetch_discord_user_info(bot: discord.Client, discord_id: int, interaction: discord.Interaction | None = None) -> dict | None:
    try:
        user: discord.User = await bot.fetch_user(discord_id)
        account_age_days = (discord.utils.utcnow() - user.created_at).days

        return {
            "id": user.id,
            "username": f"{user.name}#{user.discriminator}",
            "account_age_days": account_age_days,
            "bot": user.bot,
            "avatar_url": str(user.avatar.url) if user.avatar else None
        }

    except discord.NotFound:
        await report_error(interaction, f"Discord user with ID {discord_id} not found.", user_message=f"❌ Discord user with ID **{discord_id}** was not found.", level="error")
        return None

    except discord.HTTPException as e:
        await report_error(interaction, f"HTTP error fetching Discord user {discord_id}: {e}", level="error")
        return None


# --- Trello helper ---


async def check_trello_blacklist(identifiers: list[str], interaction: discord.Interaction | None = None):
    """
    Check a Trello board for blacklists for given identifiers (Roblox username, Discord ID, etc.).
    Returns a dict with major_blacklists and blacklists.
    """
    url = (
        f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists"
        f"?cards=all&card_fields=name,due&fields=name"
        f"&key={TRELLO_API_KEY}&token={TRELLO_TOKEN}"
    )

    major_blacklists = []
    blacklists = []
    now = datetime.now(timezone.utc)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as res:
                if res.status != 200:
                    await report_error(interaction, f"Failed to fetch Trello board: status {res.status}", level="warning")
                    return None
                lists = await res.json()

        for trello_list in lists:
            list_name = trello_list["name"]

            if list_name in SKIP_CATEGORIES:
                continue

            for card in trello_list.get("cards", []):
                card_name = card["name"]
                due_str = card.get("due")

                if due_str:
                    due_date = datetime.fromisoformat(
                        due_str.replace("Z", "+00:00"))
                    if due_date < now:
                        continue

                if any(identifier.lower() in card_name.lower() for identifier in identifiers):
                    if list_name in MAJOR_BLACKLIST_CATEGORIES:
                        if list_name not in major_blacklists:
                            major_blacklists.append(list_name)
                    else:
                        if list_name not in blacklists:
                            blacklists.append(list_name)

        return {
            "major_blacklists": major_blacklists,
            "blacklists": blacklists
        }

    except Exception as e:
        await report_error(interaction, f"Exception checking Trello blacklists: {e}", level="error")
        return None


class FilterCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.session_lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"{self.__class__.__name__} cog has been loaded")

    async def send_check_result(self, user_data: dict, reason: str, interaction: discord.Interaction | None = None):
        """Send only the failure reason to the configured channel."""
        guild_id = interaction.guild.id if interaction and interaction.guild else None
        channel = self.bot.get_channel(FILTER_CHANNEL_ID.get(guild_id))
        if not channel:
            await report_error(interaction, f"Filter channel not found.", level="error")
            return

        message = f"```yaml\n{user_data.get('username', 'Unknown')} is ❌ DENIED ❌ [{reason}]\n```"
        await channel.send(content=message)

    @app_commands.command(name="check", description="Check a user's Roblox & Discord account information.")
    @app_commands.describe(roblox_username="The Roblox username to check.", discord_id="The Discord user ID to check.")
    async def check(self, interaction: discord.Interaction, roblox_username: str, discord_id: str):
        await interaction.response.defer(ephemeral=True)
        await interaction.edit_original_response(content="⏳ Processing the check...")

        try:
            discord_id_int = int(discord_id)
        except ValueError:
            await report_error(interaction, "Invalid Discord ID provided.", level="error")
            return

        async with aiohttp.ClientSession() as session:
            # Fetch discord info and validate account age
            user_info = await fetch_discord_user_info(self.bot, discord_id_int, interaction)
            if not user_info:
                # await report_error(interaction, f"Could not fetch Discord user with ID {discord_id}.", level="error")
                return

            if user_info['account_age_days'] < 90:
                # await self.send_check_result(user_data, reason="DISCORD ACCOUNT TOO YOUNG", interaction=interaction)
                await self.send_check_result({"username": user_info['username']}, reason="DISCORD ACCOUNT TOO YOUNG", interaction=interaction)

                await interaction.edit_original_response(content="✅ Check completed and logged.")
                return

            # Fetch basic roblox info
            user_data = await fetch_roblox_user_data(session, roblox_username, interaction)
            if not user_data:
                # await report_error(interaction, f"Failed to fetch Roblox data for ID {roblox_id}.")
                return

            # Check for any blacklists
            identifiers = [user_data['username'], str(discord_id_int)]
            blacklist_info = await check_trello_blacklist(identifiers)
            major_blacklists = blacklist_info['major_blacklists'] if blacklist_info else [
            ]
            blacklists = blacklist_info['blacklists'] if blacklist_info else []

            if major_blacklists:
                await self.send_check_result(user_data, reason=f"MAJOR BLACKLIST DETECTED: {', '.join(major_blacklists)}", interaction=interaction)
                await interaction.edit_original_response(content="✅ Check completed and logged.")
                return

            if blacklists:
                await self.send_check_result(user_data, reason=f"BLACKLIST DETECTED: {', '.join(blacklists)}", interaction=interaction)
                await interaction.edit_original_response(content="✅ Check completed and logged.")
                return

            # Fetch user's divisions and check for any main divisions
            main_divisions, sub_divisions, main_group, intelligence_groups = await get_user_divisions(session, user_data['user_id'])

            # Fetch user's badges, check count, create the graph
            badges, badge_count = await fetch_user_badges_with_count(session, user_data['user_id'])

            if badge_count < 480:
                await self.send_check_result(user_data, reason=f"NOT ENOUGH BADGES DETECTED ({badge_count}/480)", interaction=interaction)
                await interaction.edit_original_response(content="✅ Check completed and logged.")
                return

            badge_graph = await generate_badge_growth_graph(
                badges, user_data['account_created__date'], user_data['username'], user_data['user_id'])

            # (All criteria met) Generate report + badge graph
            major_str = ", ".join(
                major_blacklists) if major_blacklists else "Clear"
            blacklist_str = ", ".join(blacklists) if blacklists else "Clear"

            message = (
                f"```yaml\n"
                f"-------------ROBLOX INFO-------------\n"
                f"Roblox Username: {user_data['username']}\n"
                f"Roblox ID: {user_data['user_id']}\n"
                f"Roblox Account Age: {user_data['account_age_days']} days old\n"
                f"Total Badges: {user_data['badge_pages']} pages, {user_data['badge_count']} badges\n"
                f"Followers: {user_data['followers']}, Followings: {user_data['following']}, Friends: {user_data['friends']}\n"
                f"Major Blacklists: {major_str}\n"
                f"Blacklists: {blacklist_str}\n"
                f"Followers: {user_data['followers']}, Followings: {user_data['following']}, Friends: {user_data['friends']}\n"
                f"Main Group: {main_group}\n"
                f"Main Divisions: {main_divisions}\n"
                f"Sub Divisions: {sub_divisions}\n"
                f"Intelligence Groups: {intelligence_groups}\n"
                f"```"

                f"```yaml\n"
                f"-------------DISCORD INFO-------------\n"
                f"Account Age: {user_info['account_age_days']} days old\n"
                f"User_ID: {user_info['id']}\n"
                f"Username: {user_info['username']}\n"
                f"Bot account: {user_info['bot']}\n"
                f"Avatar URL: {user_info['avatar_url']}\n"
                f"```"
                f"\n{interaction.user.mention}"
            )

            guild_id = interaction.guild.id if interaction and interaction.guild else None
            channel = self.bot.get_channel(FILTER_CHANNEL_ID.get(guild_id))
            if channel:
                await channel.send(content=message)
                if badge_graph:
                    file = discord.File(
                        badge_graph, filename="badge_growth.png")
                    await channel.send(file=file)

            await interaction.edit_original_response(content="✅ Check completed and logged.")


async def setup(bot):
    await bot.add_cog(FilterCheck(bot))
