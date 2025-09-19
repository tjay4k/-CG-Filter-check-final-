import discord
from discord.ext import commands
import os
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CGBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None  # You can create a custom help command
        )

    async def setup_hook(self):
        """This is called when the bot starts up"""
        # Load all cogs first
        await self.load_cogs()

        # Wait a brief moment to ensure cogs are loaded
        await asyncio.sleep(1)

        try:
            logger.info("Syncing commands...")
            # Sync to your specific guild first (faster for testing)
            guild = discord.Object(id=1309981030790463529)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to guild {guild.id}")

            # Then sync globally
            await self.tree.sync()
            logger.info("Synced commands globally")
        except Exception as e:
            logger.error(f"Failed to sync commands: {str(e)}")

    async def load_cogs(self):
        """Load all cogs from the cogs folder"""
        cog_files = [
            'cogs.filter_check',
            'cogs.bot_management',
            # Add more cogs as needed
        ]

        for cog in cog_files:
            try:
                await self.load_extension(cog)
                logger.info(f'Loaded {cog}')
            except Exception as e:
                logger.error(f'Failed to load {cog}: {e}')

    async def on_ready(self):
        logger.info(f'{self.user} has logged in!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')


async def main():
    bot = CGBot()
    token = os.getenv('DISCORD_TOKEN')

    if not token:
        logger.error('DISCORD_TOKEN not found in environment variables!')
        return

    async with bot:
        await bot.start(token)

if __name__ == '__main__':
    asyncio.run(main())
