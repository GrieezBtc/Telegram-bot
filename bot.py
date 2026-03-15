import sqlite3
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------------- CONFIG ---------------- #
TOKEN = '8659397259:AAFHka2puHwFoepZLeor_duJVWpgxBBGV8Y'
ADMINS = [123456789, 987654321]  # replace with your Telegram IDs
DB_FILE = 'sms_bot.db'
COOLDOWN_SEC = 5  # seconds

# ---------------- DATABASE ---------------- #
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    number TEXT,
    country TEXT
)
''')
conn.commit()

# ---------------- COOLDOWNS ---------------- #
cooldowns = {}  # user_id: last_timestamp

async def check_cooldown(update: Update, cooldown_sec=COOLDOWN_SEC):
    user_id = update.effective_user.id
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < cooldown_sec:
        await update.message.reply_text(f"⏳ Cooldown: wait {cooldown_sec} seconds.")
        return False
    cooldowns[user_id] = now
    return True

# ---------------- COMMANDS ---------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update): return
    await update.message.reply_text(
        "👋 Hi! Use /join <phone_number> <country> to register.\n"
        "Example: /join +2348012345678 Nigeria"
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update): return

    user_id = update.effective_user.id

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please provide your phone number and country.\n"
            "Usage: /join <phone_number> <country>\n"
            "Example: /join +2348012345678 Nigeria"
        )
        return

    number = context.args[0]
    country = ' '.join(context.args[1:])

    # Insert or update user
    c.execute(
        "INSERT INTO users (id, number, country) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET number=excluded.number, country=excluded.country",
        (user_id, number, country)
    )
    conn.commit()

    await update.message.reply_text(f"✅ Registered!\nNumber: {number}\nCountry: {country}")

# ---------------- ADMIN COMMANDS ---------------- #
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    if not await check_cooldown(update): return

    if not context.args:
        await update.message.reply_text("❌ Please provide a message to broadcast.\nUsage: /broadcast Your message here")
        return

    msg = ' '.join(context.args)

    c.execute("SELECT id FROM users")
    users = c.fetchall()

    sent = 0
    for (user_id,) in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
            sent += 1
        except Exception as e:
            print(f"Failed to send to {user_id}: {e}")

    await update.message.reply_text(f"✅ Broadcast sent to {sent} users.")

async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    if not await check_cooldown(update): return

    c.execute("SELECT id, number, country FROM users")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("No users registered yet.")
        return

    msg = "📋 Registered Users:\n"
    for uid, number, country in users:
        msg += f"- ID: {uid}, Number: {number}, Country: {country}\n"

    await update.message.reply_text(msg)

# ---------------- MAIN ---------------- #
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("listusers", listusers))

print("🤖 Bot is running...")
app.run_polling()
