import os

import discord


class DiploBot(discord.Bot):

    async def on_ready(self):
        print(f"{self.user.name} is ready and online!")

    def __init__(self):
        super().__init__(intents=discord.Intents.default() | discord.Intents.message_content)
        for extension in os.environ['EXTENSIONS'].replace(' ', '').split(','):
            print("Loading extension: ", extension, end=" ")
            self.load_extension(f"modules.{extension}")
        print(f"Done!")


print("Starting bot...")
bot = DiploBot()
bot.run(os.environ['BOT_TOKEN'])


"""
async db?
code not concurrency safe
logging: channel verbunden / getrennt
check that user is allowed to create the mirror. user should not be able to mirror stuff, he an not read or should not mirror (like admin channels)
"""
