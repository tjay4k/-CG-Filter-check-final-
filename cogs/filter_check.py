import discord
from discord.ext import commands
from discord import app_commands

# Replace this with your server's ID
GUILD_ID = 1309981030790463529  # <-- your server ID here
GUILD = discord.Object(id=GUILD_ID)

class CogManager(commands.Cog):
    """Cog for managing other cogs (reload, load, unload)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reload", description="Reload a bot cog")
    @app_commands.describe(cog="The name of the cog to reload")
    @app_commands.guilds(GUILD)  # Command will only work in this guild
    async def reload(self, interaction: discord.Interaction, cog: str):
        try:
            self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"✅ Cog `{cog}` reloaded successfully!", ephemeral=True)
        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"⚠️ Cog `{cog}` is not loaded.", ephemeral=True)
        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"❌ Cog `{cog}` not found.", ephemeral=True)
        except commands.ExtensionFailed as e:
            await interaction.response.send_message(f"❌ Failed to reload `{cog}`: {e}", ephemeral=True)

    @app_commands.command(name="load", description="Load a bot cog")
    @app_commands.describe(cog="The name of the cog to load")
    @app_commands.guilds(GUILD)
    async def load(self, interaction: discord.Interaction, cog: str):
        try:
            self.bot.load_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"✅ Cog `{cog}` loaded successfully!", ephemeral=True)
        except commands.ExtensionAlreadyLoaded:
            await interaction.response.send_message(f"⚠️ Cog `{cog}` is already loaded.", ephemeral=True)
        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"❌ Cog `{cog}` not found.", ephemeral=True)
        except commands.ExtensionFailed as e:
            await interaction.response.send_message(f"❌ Failed to load `{cog}`: {e}", ephemeral=True)

    @app_commands.command(name="unload", description="Unload a bot cog")
    @app_commands.describe(cog="The name of the cog to unload")
    @app_commands.guilds(GUILD)
    async def unload(self, interaction: discord.Interaction, cog: str):
        try:
            self.bot.unload_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"✅ Cog `{cog}` unloaded successfully!", ephemeral=True)
        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f"⚠️ Cog `{cog}` is not loaded.", ephemeral=True)
        except commands.ExtensionNotFound:
            await interaction.response.send_message(f"❌ Cog `{cog}` not found.", ephemeral=True)
        except commands.ExtensionFailed as e:
            await interaction.response.send_message(f"❌ Failed to unload `{cog}`: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CogManager(bot))
