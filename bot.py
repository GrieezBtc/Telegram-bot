import sqlite3
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------------- CONFIG ---------------- #
TOKEN = '8659397259:AAFHka2puHwFoepZLeor_duJVWpgxBBGV8Y'
ADMINS = [6158540839]  
DB_FILE = 'sms_bot.db'
COOLDOWN_SEC = 5

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
cooldowns = {}

async def check_cooldown(update: Update, cooldown_sec=COOLDOWN_SEC):
    user_id = update.effective_user.id
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < cooldown_sec:
        await update.message.reply_text(f"⏳ Cooldown: wait {cooldown_sec} seconds.")
        return False
    cooldowns[user_id] = now
    return True

def is_admin(user_id: int):
    return user_id in ADMINS

# ---------------- USER COMMANDS ---------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update):
        return
    await update.message.reply_text(
        "👋 Hi! Use /join <phone_number> <country> to register.\n"
        "Example: /join +2348012345678 Nigeria\n\n"
        "Use /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update):
        return

    user_text = (
        "📖 Available commands:\n\n"
        "/start - Start the bot\n"
        "/join <number> <country> - Register or update your details\n"
        "/help - Show this help message\n"
    )

    if is_admin(update.effective_user.id):
        user_text += (
            "\n🔐 Admin commands:\n"
            "/broadcast <message> - Send message to all users\n"
            "/listusers - Show all registered users\n"
            "/stats - Show total registered users\n"
            "/finduser <telegram_id|number> - Search for a user\n"
            "/removeuser <telegram_id> - Remove a user\n"
        )

    await update.message.reply_text(user_text)

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update):
        return

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

    c.execute(
        "INSERT INTO users (id, number, country) VALUES (?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET number=excluded.number, country=excluded.country",
        (user_id, number, country)
    )
    conn.commit()

    await update.message.reply_text(
        f"✅ Registered successfully!\nNumber: {number}\nCountry: {country}"
    )

# ---------------- ADMIN COMMANDS ---------------- #
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not await check_cooldown(update):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a message.\nUsage: /broadcast Hello everyone"
        )
        return

    msg = ' '.join(context.args)

    c.execute("SELECT id FROM users")
    users = c.fetchall()

    sent = 0
    failed = 0

    for (user_id,) in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"Failed to send to {user_id}: {e}")

    await update.message.reply_text(
        f"✅ Broadcast complete.\nSent: {sent}\nFailed: {failed}"
    )

async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not await check_cooldown(update):
        return

    c.execute("SELECT id, number, country FROM users")
    users = c.fetchall()

    if not users:
        await update.message.reply_text("No users registered yet.")
        return

    msg = "📋 Registered Users:\n\n"
    for uid, number, country in users:
        msg += f"ID: {uid}\nNumber: {number}\nCountry: {country}\n\n"

    # Telegram messages have length limits, so split if too long
    for i in range(0, len(msg), 4000):
        await update.message.reply_text(msg[i:i+4000])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not await check_cooldown(update):
        return

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    await update.message.reply_text(f"📊 Total registered users: {total_users}")

async def finduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not await check_cooldown(update):
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Usage:\n/finduser <telegram_id>\nor\n/finduser <phone_number>"
        )
        return

    query = ' '.join(context.args).strip()

    if query.isdigit():
        c.execute("SELECT id, number, country FROM users WHERE id = ?", (int(query),))
    else:
        c.execute("SELECT id, number, country FROM users WHERE number = ?", (query,))

    user = c.fetchone()

    if not user:
        await update.message.reply_text("❌ User not found.")
        return

    uid, number, country = user
    await update.message.reply_text(
        f"✅ User found:\nID: {uid}\nNumber: {number}\nCountry: {country}"
    )

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not await check_cooldown(update):
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /removeuser <telegram_id>")
        return

    try:
        user_id_to_remove = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Telegram ID must be a number.")
        return

    c.execute("SELECT id FROM users WHERE id = ?", (user_id_to_remove,))
    user = c.fetchone()

    if not user:
        await update.message.reply_text("❌ User not found.")
        return

    c.execute("DELETE FROM users WHERE id = ?", (user_id_to_remove,))
    conn.commit()

    await update.message.reply_text(f"✅ User {user_id_to_remove} removed successfully.")

# ---------------- MAIN ---------------- #
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("join", join))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("listusers", listusers))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("finduser", finduser))
app.add_handler(CommandHandler("removeuser", removeuser))

print("🤖 Bot is running...")
app.run_polling()