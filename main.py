import contextlib
from typing import Optional
import discord
from discord import app_commands
from database import RollHistories, SessionLocal, get_db
from dotenv import load_dotenv
import random
from os import environ as ENV

load_dotenv()


class Client(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.synced = False
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        await self.wait_until_ready()
        if not self.synced:
            await self.tree.sync()
            self.synced = True

        print(f"Logged in as {self.user}")


client = Client()


@client.tree.command(name="roll", description="Rolls a dice")
@app_commands.describe(dice="The number of sides on the dice")
async def roll(
    interaction: discord.Interaction,
    dice: int = 100,
):
    result = random.randint(1, dice)
    with contextlib.closing(SessionLocal()) as db:
        db.add(RollHistories(userid=interaction.user.id, dice=dice, result=result))
        db.commit()
    await interaction.response.send_message(f"You rolled a {result}")


@client.tree.command(name="history", description="Shows your last 10 rolls")
async def history(interaction: discord.Interaction):
    with contextlib.closing(SessionLocal()) as db:
        rolls = (
            db.query(RollHistories)
            .filter(RollHistories.userid == interaction.user.id)
            .order_by(RollHistories.time.desc())
            .limit(10)
            .all()
        )
    await interaction.response.send_message(
        f"**Last {len(rolls)} roll(s):**\n```md\n"
        + "\n".join([f"d{roll.dice}: {roll.result}" for roll in rolls])
        + "```"
    )


@client.tree.command(name="rollgame", description="Makes a game out of rolling dice!")
@app_commands.describe(
    dice="The number of sides on the dice", players="The number of players"
)
async def rollgame(
    cmdinteraction: discord.Interaction,
    dice: int = 100,
    players: int = 2,
):
    """
    Displays a discord.py discord interaction with a button for the players to join.
    After a minute, or when all players have joined, the game begins.

    The dice is rolled for each player, and the winner and loser are announced.

    When players join, the initial message is edited to show the player list.
    """

    class Message:
        content: str = ""
        won: Optional[bool] = False

    class RollGame(discord.ui.View):
        def __init__(self, players: int, dice: int, message):
            super().__init__(timeout=60)
            self.players = players
            self.dice = dice
            self.message = message
            self.rolls: dict = {}

        async def interaction_check(self, interaction: discord.Interaction):
            return interaction.user.id not in self.rolls

        async def on_timeout(self):
            if not self.message.won:
                await cmdinteraction.followup.send(
                    "\n\n**The game has timed out. No winner will be announced.**"
                )

        @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
        async def join(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            self.rolls[interaction.user.id] = random.randint(1, self.dice)
            message.content += f"<@{interaction.user.id}>\n"
            if len(self.rolls) == self.players:
                await interaction.response.edit_message(
                    content=message.content, view=None
                )
            else:
                await interaction.response.edit_message(content=message.content)
            await interaction.followup.send("You joined the game!", ephemeral=True)

            if len(self.rolls) == self.players:
                self.stop()

    message = Message()
    game = RollGame(players, dice, message)

    message.content = (
        f"**Roll Game**\n\n"
        + f"Rolling a `d{dice}` to see who wins!\n\n"
        + f"**Players:**\n"
    )
    await cmdinteraction.response.send_message(
        message.content,
        view=game,
    )

    await game.wait()

    if len(game.rolls) != players:
        return

    rolls = sorted(game.rolls.items(), key=lambda x: x[1], reverse=True)

    await cmdinteraction.followup.send(
        (
            "**The game has ended!**\n\n"
            + f"**Scoreboard:**\n"
            + "\n".join([f"<@{player[0]}>: {player[1]}" for player in rolls])
            + f"\n\n**Winner:** <@{rolls[0][0]}>\n"
            + f"**Loser:** <@{rolls[-1][0]}>\n"
        )
    )

    # Add the game to the database
    with contextlib.closing(SessionLocal()) as db:
        for player in rolls:
            db.add(
                RollHistories(
                    userid=player[0],
                    dice=dice,
                    result=player[1],
                )
            )
        db.commit()

    message.won = True


client.run(ENV.get("TOKEN"))
