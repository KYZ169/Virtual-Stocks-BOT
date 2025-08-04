import discord
from discord import app_commands
from dotenv import load_dotenv
import os
import asyncio
from commands import stock_graph
from commands import user_manager
from commands import stock_manager
from commands import stock_trading
from datetime import datetime
from commands.stock_trading import auto_sell_loop

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("コマンド同期完了")

client = MyClient()
tree = client.tree  # ショートカット参照

@client.event
async def on_ready():
    stock_manager.init_db()
    stock_manager.auto_update_prices.start()
    asyncio.create_task(auto_sell_loop(client))

    print(f"ログイン成功: {client.user}")
    
#株価
@tree.command(name="株価", description="銘柄の株価グラフを表示します")
@app_commands.describe(symbol="銘柄コード（例: VELT）")
async def 株価(interaction: discord.Interaction, symbol: str):
    symbol = symbol.upper()
    filename = f"{symbol}_graph.png"
    full_path = os.path.join("graphs", filename)
    success = stock_graph.generate_stock_graph(symbol, filename)

    if not success:
        await interaction.response.send_message("❌ 履歴が見つかりません。", ephemeral=True)
        return

    await interaction.response.send_message(file=discord.File(full_path))

#残高
@tree.command(name="残高", description="あなたの残高を表示します")
async def 残高(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_manager.init_user(user_id)
    balance = user_manager.get_balance(user_id)
    await interaction.response.send_message(f"💰 {interaction.user.display_name} の残高: {balance} Vety", ephemeral=True)

#発行
@tree.command(name="発行", description="他ユーザーにVetyを発行します（管理者のみ）")
@app_commands.describe(member="発行先ユーザー", amount="発行額")
async def 発行(interaction: discord.Interaction, member: discord.Member, amount: float):
    allowed_roles = ['終界主', '宰律士']
    user_roles = [role.name for role in interaction.user.roles]

    if not any(role in allowed_roles for role in user_roles):
        await interaction.response.send_message("❌ このコマンドを使う権限がありません。", ephemeral=True)
        return

    user_manager.init_user(str(member.id))
    user_manager.add_balance(str(member.id), amount)
    await interaction.response.send_message(f"✅ {member.display_name} に {amount} Vety を発行しました。")

#保有銘柄表示
@tree.command(name="保有", description="現在の保有銘柄を表示します")
async def show_holdings(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    holdings = stock_trading.get_user_holdings(user_id)

    if not holdings:
        await interaction.response.send_message("📭 現在、保有している銘柄はありません。")
        return

    msg = "📦 **現在の保有銘柄**\n"
    for symbol, amount in holdings:
        msg += f"・{symbol}: {amount}口\n"

    await interaction.response.send_message(msg)


#現在価格表示    
@tree.command(name="現在価格表示", description="指定した銘柄の現在価格を表示します")
@app_commands.describe(symbol="銘柄名（例: VELT）")
async def get_price_command(interaction: discord.Interaction, symbol: str):
    price = stock_manager.get_price(symbol.upper())
    if price is not None:
        await interaction.response.send_message(f"💹 `{symbol.upper()}` の現在値は `{price}` 円です。")
    else:
        await interaction.response.send_message(f"❓ 銘柄 `{symbol.upper()}` は存在しません。")

#銘柄追加
@tree.command(name="銘柄追加", description="新しい銘柄を追加します（管理者のみ）")
@app_commands.describe(
    symbol="銘柄名（例: VELT）",
    price="初期価格",
    speed="何秒ごとに価格を更新するか",
    min_fluct="最小振れ幅",
    max_fluct="最大振れ幅"
)
async def add_stock_command(
    interaction: discord.Interaction,
    symbol: str,
    price: float,
    speed: float,
    min_fluct: float,
    max_fluct: float
):
    allowed_roles = ['終界主', '宰律士']
    user_roles = [role.name for role in interaction.user.roles]

    if not any(role in allowed_roles for role in user_roles):
        await interaction.response.send_message("❌ このコマンドを使う権限がありません。", ephemeral=True)
        return

    stock_manager.add_stock(symbol.upper(), price, speed, min_fluct, max_fluct)
    await interaction.response.send_message(f"✅ 銘柄 `{symbol.upper()}` を追加しました。初期価格: {price}")

#銘柄削除
@tree.command(name="銘柄削除", description="銘柄を削除します（管理者のみ）")
@app_commands.describe(symbol="削除したい銘柄名（例: VELT）")
async def delete_stock_command(interaction: discord.Interaction, symbol: str):
    allowed_roles = ['終界主', '宰律士']
    user_roles = [role.name for role in interaction.user.roles]

    if not any(role in allowed_roles for role in user_roles):
        await interaction.response.send_message("❌ このコマンドを使う権限がありません。", ephemeral=True)
        return

    stock_manager.delete_stock(symbol.upper())
    await interaction.response.send_message(f"🗑 銘柄 `{symbol.upper()}` を削除しました。")

#銘柄を買う
@tree.command(name="銘柄を買う", description="指定した銘柄を購入します")
@app_commands.describe(symbol="銘柄名（例: VELT）", amount="購入口数", auto_sell_minutes="何分後に自動売却（0で手動）")
async def 買う(interaction: discord.Interaction, symbol: str, amount: int, auto_sell_minutes: int):
    user_id = str(interaction.user.id)
    stock_trading.init_user(user_id)
    message = stock_trading.buy_stock(user_id, symbol.upper(), amount, auto_sell_minutes)
    await interaction.response.send_message(message)

#銘柄を売る
@tree.command(name="銘柄を売る", description="保有している銘柄を売却します")
@app_commands.describe(symbol="銘柄名（例: VELT）", amount="売却する口数（空欄なら全数）")
async def 売る(interaction: discord.Interaction, symbol: str, amount: int):
    user_id = str(interaction.user.id)
    message = await stock_trading.sell_stock(user_id, symbol.upper(), amount)
    await interaction.response.send_message(message)

client.run(TOKEN)