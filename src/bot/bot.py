import discord
import mariadb
import os
import time

class AllTheBots(discord.Bot):

    async def on_ready(self):
        print(f"{self.user} is ready and online!")

    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        print("Connecting to database...", end=" ")
        while True:
            try:
                self.con = mariadb.connect(
                    user = os.environ['DB_USER'],
                    password = os.environ['DB_PASSWORD'],
                    host = os.environ['DB_HOST'],
                    port = int(os.environ['DB_PORT']),
                    database= os.environ['DB_DATABASE']
                )
                break
            except mariadb.Error as e:
                print(f"Error connecting to MariaDB Platform: {e}")
                print("Retrying in 5 seconds...")
                time.sleep(5)
        self.cur = self.con.cursor(buffered=True)
        print("Done!")
        for extention in os.environ['EXTENTIONS'].replace(' ', '').split(','):
            print("Loading extention: ", extention, end=" ")
            self.load_extension(f"modules.{extention}")
            print(f"Done!")

print("Starting bot...")
bot = AllTheBots()
bot.run(os.environ['BOT_TOKEN'])
