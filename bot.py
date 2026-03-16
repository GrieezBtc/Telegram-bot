import sqlite3
import time
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ================= CONFIG ================= #
TOKEN = "8659397259:AAEwDPMd1V4eaDpQJelR-0585YwBzlHFHuI"
DB_FILE = "sms_bot.db"

# Owners/admins
OWNERS = [6158540839]

# Users who skip join verification
SKIP_JOIN = [6158540839] 

# Required join channels/groups
REQUIRED_CHANNEL = "@smschannel"
REQUIRED_GROUP = "@smsgc"
CHANNEL_LINK = "https://t.me/+PVmudYXtfoE1NmQ0"
GROUP_LINK = "https://t.me/+WWCrTT_d-tIwYjRk"

DEFAULT_COUNTRY = "Nigeria"
DEFAULT_COOLDOWN = 5

# ================= DATABASE ================= #
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Users table
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    number TEXT,
    country TEXT
)
""")

# Admins table
c.execute("""
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)
""")

# Blocked numbers table
c.execute("""
CREATE TABLE IF NOT EXISTS blocked_numbers (
    number TEXT PRIMARY KEY
)
""")

# SMS panel table
c.execute("""
CREATE TABLE IF NOT EXISTS sms_panels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    api_url TEXT
)
""")

# OTP table
c.execute("""
CREATE TABLE IF NOT EXISTS otp_data (
    user_id INTEGER PRIMARY KEY,
    otp_code TEXT
)
""")

# Settings table
c.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

conn.commit()

# Ensure owners are admins
for owner_id in OWNERS:
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (owner_id,))
conn.commit()

# ================= MEMORY ================= #
cooldowns = {}

# ================= HELPERS ================= #
def get_setting(key, default=None):
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    return row[0] if row else default

def set_setting_value(key, value):
    c.execute("""
        INSERT INTO settings (key,value) VALUES (?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, str(value)))
    conn.commit()

def is_owner(user_id: int):
    return user_id in OWNERS

def is_admin(user_id: int):
    if is_owner(user_id):
        return True
    c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
    return c.fetchone() is not None

def is_number_blocked(number: str):
    c.execute("SELECT number FROM blocked_numbers WHERE number=?", (number,))
    return c.fetchone() is not None

async def check_cooldown(update: Update):
    cooldown_sec = int(get_setting("cooldown", DEFAULT_COOLDOWN))
    user_id = update.effective_user.id
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < cooldown_sec:
        await update.message.reply_text(
            f"⏳ Please wait {cooldown_sec}s before using another command."
        )
        return False
    cooldowns[user_id] = now
    return True

def main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("/getnumber"), KeyboardButton("/getcountry")],
            [KeyboardButton("/viewotp"), KeyboardButton("/joinchannel")],
            [KeyboardButton("/help")]
        ],
        resize_keyboard=True
    )

def join_buttons():
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("👥 Join Group", url=GROUP_LINK)],
        [InlineKeyboardButton("✅ I Have Joined", callback_data="verify_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ================= FORCE JOIN ================= #
async def check_force_join(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if user_id in SKIP_JOIN:
        return True
    try:
        channel_member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        group_member = await context.bot.get_chat_member(REQUIRED_GROUP, user_id)
        allowed = ["member", "administrator", "creator"]
        return (
            channel_member.status in allowed and
            group_member.status in allowed
        )
    except Exception:
        return False

# ================= STATES ================= #
ASK_NUMBER, ASK_COUNTRY = range(2)

# ================= USER COMMANDS ================= #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update):
        return
    joined = await check_force_join(update.effective_user.id, context)
    if not joined:
        await update.message.reply_text(
            "👋Hello Welcome! Kindly join our channel and group below to have access to the bot.\nTap the buttons below join the channel and group then click 'I Have Joined after you have successfully join our community'.",
            reply_markup=join_buttons()
        )
        return

    await update.message.reply_text(
        "✅ Welcome! Let's register your number step by step.",
        reply_markup=main_menu()
    )
    await update.message.reply_text("📱 Please enter your phone number:")
    return ASK_NUMBER

async def ask_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if is_number_blocked(user_input):
        await update.message.reply_text("🚫 This number is blocked. Enter another number.")
        return ASK_NUMBER
    context.user_data["number"] = user_input
    await update.message.reply_text("🌍 Great! Now enter your country:")
    return ASK_COUNTRY

async def ask_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    country = update.message.text.strip()
    user_id = update.effective_user.id
    number = context.user_data.get("number")

    c.execute("""
        INSERT INTO users (id,number,country) VALUES (?,?,?)
        ON CONFLICT(id) DO UPDATE SET number=excluded.number,country=excluded.country
    """, (user_id, number, country))
    conn.commit()
    await update.message.reply_text(
        f"✅ Registration complete!\n\n📱 Number: {number}\n🌍 Country: {country}",
        reply_markup=main_menu()
    )
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration cancelled.", reply_markup=main_menu())
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_cooldown(update):
        return
    text = (
        "📖 *User Commands*\n"
        "/start - Start registration\n"
        "/help - Show help\n"
        "/getnumber - View your number\n"
        "/getcountry - View default country\n"
        "/viewotp - View your OTP\n"
        "/joinchannel - Join required channel/group\n"
    )
    if is_admin(update.effective_user.id):
        text += (
            "\n🔐 *Admin Commands*\n"
            "/broadcast <msg>\n/listusers\n/stats\n/finduser <id|number>\n/removeuser <id>\n"
            "/addadmin <id>\n/removeadmin <id>\n/block <number>\n/unblock <number>\n"
            "/setcountry <country>\n/cooldown <seconds>\n/addsms <name> <url>\n/listsms\n/otpcode <id> <code>\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())

# ================= CALLBACK ================= #
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "verify_join":
        joined = await check_force_join(query.from_user.id, context)
        if joined:
            await query.message.reply_text(
                "✅ Verified! You can now register.", reply_markup=main_menu()
            )
            await update.message.reply_text("📱 Please enter your phone number:")
            return ASK_NUMBER
        else:
            await query.message.reply_text(
                "❌ Not joined yet. Join channel/group first.",
                reply_markup=join_buttons()
            )

# ================= ADMIN COMMANDS ================= #
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    if not await check_cooldown(update): return
    if not context.args:
        await update.message.reply_text("❌ Usage: /broadcast Hello everyone")
        return
    msg = ' '.join(context.args)
    c.execute("SELECT id FROM users")
    users = c.fetchall()
    sent = failed = 0
    for (uid,) in users:
        try: await context.bot.send_message(chat_id=uid, text=msg); sent+=1
        except: failed+=1
    await update.message.reply_text(f"✅ Broadcast done.\nSent: {sent}\nFailed: {failed}")

# ================= MAIN ================= #
app = ApplicationBuilder().token(TOKEN).build()

# Conversation for registration
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_number)],
        ASK_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_country)],
    },
    fallbacks=[CommandHandler("cancel", cancel_registration)],
)
app.add_handler(conv_handler)

# User & admin commands
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("broadcast", broadcast))

# Callback buttons
app.add_handler(CallbackQueryHandler(button_handler))

print("🤖 Bot V3 FULLY INTEGRATED is running...")
app.run_polling()