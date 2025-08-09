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
from discord import app_commands, Interaction

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

# 通貨候補用
async def autocomplete_symbols(interaction: discord.Interaction, current: str):
    syms = stock_manager.get_all_symbols(25, current or "")
    return [app_commands.Choice(name=s, value=s) for s in syms]

@client.event
async def on_ready():
    await tree.sync()
    stock_manager.init_db()
    asyncio.create_task(auto_sell_loop(client))
    asyncio.create_task(price_update_loop())
    print(f"ログイン成功: {client.user}")

async def price_update_loop():
    await client.wait_until_ready()

    while not client.is_closed():
        stock_manager.random_update_prices()  # 価格を更新
        updates = stock_manager.log_current_prices()  # 通知対象を取得

        for channel_id, message in updates:
            channel = client.get_channel(channel_id)
            if channel:
                await channel.send(message)

        stock_manager.cleanup_old_history()  # 古い履歴を削除

        await asyncio.sleep(1)

#株価
@tree.command(name="株価", description="銘柄の株価グラフを表示します")
@app_commands.describe(symbol="銘柄コード（例: VELT）")
@app_commands.autocomplete(symbol=autocomplete_symbols)
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
@tree.command(name="vety残高を確認する", description="あなたの残高を表示します")
async def 残高(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_manager.init_user(user_id)
    balance = user_manager.get_balance(user_id)
    await interaction.response.send_message(f"{interaction.user.display_name} の残高: {balance} Vety", ephemeral=True)

#発行
@tree.command(name="vetyを発行する", description="他ユーザーにVetyを発行します（管理者のみ）")
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
        await interaction.response.send_message("📭 現在、保有している銘柄はありません。", ephemeral=True)
        return

    msg = "📦 **現在の保有銘柄**\n"
    for symbol, amount in holdings:
        msg += f"・{symbol}: {amount}口\n"

    await interaction.response.send_message(msg)


#現在価格表示    
@tree.command(name="現在価格一覧", description="全銘柄の現在価格を表示します")
async def show_all_prices(interaction: discord.Interaction):
    message = stock_trading.get_all_current_prices_message()
    await interaction.response.send_message(message)

@tree.command(name="銘柄追加", description="新しい銘柄を追加します（管理者のみ）")
@app_commands.describe(
    symbol="銘柄名（例: VELT）",
    price="初期価格",
    speed="何秒ごとに価格を更新するか",
    min_fluct="最小振れ幅",
    max_fluct="最大振れ幅",
    channel="価格更新を通知するチャンネル",
    user="還元されるユーザー"
)
async def add_stock_command(
    interaction: discord.Interaction,
    symbol: str,
    price: float,
    speed: float,
    min_fluct: float,
    max_fluct: float,
    channel: discord.TextChannel,
    user: discord.User
):
    allowed_roles = ['終界主', '宰律士']
    user_roles = [role.name for role in interaction.user.roles]

    if not any(role in allowed_roles for role in user_roles):
        await interaction.response.send_message("❌ このコマンドを使う権限がありません。", ephemeral=True)
        return

    # user は還元対象
    user_id = str(user.id)

    stock_manager.add_stock(
        symbol.upper(), price, speed, min_fluct, max_fluct, channel.id, user_id
    )

    await interaction.response.send_message(
        f"✅ 銘柄 `{symbol.upper()}` を追加しました。初期価格: {price}（還元対象: <@{user_id}>）"
    )


#銘柄削除
@tree.command(name="銘柄削除", description="銘柄を削除します（管理者のみ）")
@app_commands.describe(symbol="削除したい銘柄名（例: VELT）")
@app_commands.autocomplete(symbol=autocomplete_symbols)
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
@app_commands.autocomplete(symbol=autocomplete_symbols)
async def 買う(interaction: discord.Interaction, symbol: str, amount: int, auto_sell_minutes: int):
    user_id = str(interaction.user.id)
    stock_trading.init_user(user_id)
    message = stock_trading.buy_stock(user_id, symbol.upper(), amount, auto_sell_minutes)
    await interaction.response.send_message(message, ephemeral=True)

#銘柄を売る
@tree.command(name="銘柄を売る", description="保有している銘柄を売却します")
@app_commands.describe(symbol="銘柄名（例: VELT）", amount="売却する口数（空欄なら全数）")
@app_commands.autocomplete(symbol=autocomplete_symbols)
async def 売る(interaction: discord.Interaction, symbol: str, amount: int):
    user_id = str(interaction.user.id)
    try:
        # ✅ 非同期ラッパーを使う（手動売却なので auto=False）
        message = await stock_trading.sell_stock_async(user_id, symbol.upper(), amount, auto=False)
        await interaction.response.send_message(message, ephemeral=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

# 自動売却ループ（変更不要）
async def auto_sell_loop(client):
    await client.wait_until_ready()

    while not client.is_closed():
        await asyncio.sleep(30)
        now = datetime.now().isoformat()

        with stock_trading.get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT user_id, symbol, amount FROM user_stocks
                WHERE auto_sell_time IS NOT NULL AND auto_sell_time <= ?
            """, (now,))
            rows = c.fetchall()

        for user_id, symbol, amount in rows:
            try:
                message = await stock_trading.sell_stock_async(user_id, symbol, amount, auto=True)
                user = await client.fetch_user(int(user_id))
                await user.send(f"💸 {message}")
            except Exception as e:
                print(f"❌ 自動売却エラー: {e}")

# 送金コマンド
@tree.command(name="vetyを送金する", description="他ユーザーにVetyを送金します")
@app_commands.describe(member="送金先ユーザー", amount="送金額")
async def 送金(interaction: discord.Interaction, member: discord.Member, amount: float):
    from_id = str(interaction.user.id)
    to_id = str(member.id)

    user_manager.init_user(from_id)
    user_manager.init_user(to_id)

    if from_id == to_id:
        await interaction.response.send_message("❌ 自分に送金することはできません。", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ 正の数を入力してください。", ephemeral=True)
        return

    success = user_manager.transfer_balance(from_id, to_id, amount)
    if success:
        await interaction.response.send_message(f"✅ {interaction.user.display_name} から {member.display_name} に {amount} Vety を送金しました。")
    else:
        await interaction.response.send_message("❌ 残高が不足しています。", ephemeral=True)

# 減額コマンド
@tree.command(name="vetyを減額する", description="指定ユーザーのVetyを減額します（管理者のみ）")
@app_commands.describe(member="対象ユーザー", amount="減額額")
async def 減額(interaction: discord.Interaction, member: discord.Member, amount: float):
    allowed_roles = ['終界主', '宰律士']
    user_roles = [role.name for role in interaction.user.roles]

    if not any(role in allowed_roles for role in user_roles):
        await interaction.response.send_message("❌ このコマンドを使う権限がありません。", ephemeral=True)
        return

    user_id = str(member.id)
    user_manager.init_user(user_id)

    if amount <= 0:
        await interaction.response.send_message("❌ 正の数を入力してください。", ephemeral=True)
        return

    success = user_manager.decrease_balance(user_id, amount)
    if success:
        await interaction.response.send_message(f"✅ {member.display_name} の残高を {amount} Vety 減額しました。")
    else:
        await interaction.response.send_message("❌ 減額に失敗しました（残高不足の可能性あり）。", ephemeral=True)

client.run(TOKEN)