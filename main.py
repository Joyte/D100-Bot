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
    embed = discord.Embed(
        title=f"Rolling a d{dice}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Result:", value=result)
    await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())



@client.tree.command(name="history", description="Shows your last 10 rolls")
@app_commands.describe(person="The person to show the history of")
async def history(interaction: discord.Interaction, person: discord.Member | discord.User | None = None):
    if person is None:
        person = interaction.user

    with contextlib.closing(SessionLocal()) as db:
        rolls = (
            db.query(RollHistories)
            .filter(RollHistories.userid == person.id) # type: ignore
            .order_by(RollHistories.time.desc())
            .limit(10)
            .all()
        )

    afterstring = "" if person == interaction.user else f" for {person.mention}"

    embed = discord.Embed(title=f"Last {len(rolls)} roll{'' if len(rolls) == 1 else 's'}{afterstring}:", color=discord.Color.gold())
    for roll in rolls:
        embed.add_field(name=f"d{roll.dice}: {roll.result}", value="", inline=False)

    await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())



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

    class Data:
        content: str = ""
        won: Optional[bool] = False

    class RollGame(discord.ui.View):
        def __init__(self, players: int, dice: int, data):
            super().__init__(timeout=60)
            self.players = players
            self.dice = dice
            self.data = data
            self.rolls: dict = {}

        async def interaction_check(self, interaction: discord.Interaction):
            return interaction.user.id not in self.rolls

        async def on_timeout(self):
            if not self.data.won:
                embed = discord.Embed(
                    title="Roll Game",
                    description="The game has timed out. No winner will be announced.",
                    color=discord.Color.red(),
                )
                
                # Disable the buttons
                for child in self.children:
                    child.disabled = True # type: ignore

                await (await cmdinteraction.original_response()).edit(embed=embed, view=self)

        @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
        async def join(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if interaction.user.id in self.rolls:
                await interaction.response.send_message(
                    "You have already joined the game!", ephemeral=True
                )
                return

            self.rolls[interaction.user.id] = random.randint(1, self.dice)
            self.data.content += f"{interaction.user.mention}\n"
            if len(self.rolls) == self.players:
                rolls = sorted(self.rolls.items(), key=lambda x: x[1], reverse=True)
                embed = discord.Embed(
                    title="Roll Game",
                    description=f"Rolling a `d{self.dice}` to see who wins!\n\n**Leaderboard:**\n" + "\n".join(
                        [f"<@{player}>: {roll}" for player, roll in rolls]
                    ),
                    color=discord.Color.green(),
                )


                embed.add_field(
                    name="Winner:",
                    value=f"<@{rolls[0][0]}>"
                )
                embed.add_field(
                    name="Loser:",
                    value=f"<@{rolls[-1][0]}>"
                )

                button.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)

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

                self.data.won = True

            else:
                embed = discord.Embed(
                    title="Roll Game",
                    description=f"Rolling a `d{self.dice}` to see who wins!\n\n**Players:**\n{self.data.content}",
                    color=discord.Color.green(),
                )
                await interaction.response.edit_message(embed=embed)

            await interaction.followup.send("You joined the game!", ephemeral=True)

            if len(self.rolls) == self.players:
                self.stop()

    await cmdinteraction.response.send_message(embed=discord.Embed(
        title="Roll Game",
        description=f"Rolling a `d{dice}` to see who wins!\n\n**Players:**\n",
        color=discord.Color.green(),
    ), view=RollGame(players, dice, Data()))

def calculate_averages(userid) -> dict[int, float]:
    averages = {}
    with contextlib.closing(SessionLocal()) as db:
        rolls = (
            db.query(RollHistories)
            .filter(RollHistories.userid == userid) # type: ignore
            .all()
        )

    for roll in rolls:
        if roll.dice not in averages:
            averages[roll.dice] = roll.result
        else:
            # Calculate the average, and round to 2 decimal places.
            # Make it an int if it's a whole number.
            averages[roll.dice] = round(
                (averages[roll.dice] + roll.result) / 2, 2
            )
            if averages[roll.dice] % 1 == 0:
                averages[roll.dice] = int(averages[roll.dice])

    return averages


@client.tree.command(name="average", description="Shows the average of all your rolls")
async def average(interaction: discord.Interaction):
    averages = calculate_averages(interaction.user.id)

    if not averages:
        embed = discord.Embed(
            title="No Rolls Found",
            description="You haven't rolled any dice yet! Try `/roll`.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        return

    embed = discord.Embed(
        title="Roll Averages",
        description="\n".join(
            [
                f"d{dice}: {result}"
                for dice, result in averages.items()
            ]
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="leaderboard", description="Shows the people with the highest average")
@app_commands.describe(die="The die to show the leaderboard for")
async def leaderboard(interaction: discord.Interaction, die: int):
    with contextlib.closing(SessionLocal()) as db:
        averages = (
            db.query(RollHistories)
            .filter(RollHistories.dice == die) # type: ignore
            .all()
        )

    if not averages:
        embed = discord.Embed(
            title="No Rolls Found",
            description="No rolls have been made with that die yet! Try `/roll`.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # Make a set of all the userids
    userids = set()
    for average in averages:
        userids.add(average.userid)

    averages = {}
    for userid in userids:
        averages[userid] = calculate_averages(userid)[die]

    embed = discord.Embed(
        title=f"Roll Leaderboard for d{die}",
        description="\n".join(
            [
                f"{i+1}) <@{userid}>: {result}"
                for i, (userid, result) in enumerate(sorted(averages.items(), key=lambda x: x[1], reverse=True)[:10])
            ]
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


client.run(ENV.get("TOKEN", ""))
