import logging
import time
import sqlite3
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set!")

CHANNEL_ID = -1003742411752
CHANNEL_LINK = "https://t.me/+oSyheKUVST9mM2I0"
REQUIRED_REFERRALS = 2
COOLDOWN_SECONDS = 10
# ==========================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    referrals INTEGER DEFAULT 0,
    referred_by INTEGER,
    last_message_time INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    msg_id INTEGER,
    user_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)
""")
conn.commit()

# Default admin
cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (8525657434,))
conn.commit()

# ================= HELPERS =================
def is_admin(user_id: int):
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None

def get_all_admins():
    cursor.execute("SELECT user_id FROM admins")
    return [row[0] for row in cursor.fetchall()]

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("START command triggered")

    user_id = update.effective_user.id
    args = context.args

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()

    if not user:
        referred_by = None

        if args:
            try:
                potential_ref = int(args[0])

                # prevent self-referral & ensure referrer exists
                cursor.execute("SELECT 1 FROM users WHERE user_id=?", (potential_ref,))
                if potential_ref != user_id and cursor.fetchone():
                    referred_by = potential_ref

            except:
                pass

        cursor.execute(
            "INSERT INTO users (user_id, referred_by) VALUES (?, ?)",
            (user_id, referred_by)
        )

        # increment referral safely
        if referred_by:
            cursor.execute(
                "UPDATE users SET referrals = referrals + 1 WHERE user_id=?",
                (referred_by,)
            )

        conn.commit()

    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    referrals = result[0] if result else 0

    ref_link = f"https://t.me/{context.bot.username}?start={user_id}"

    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify")],
        [InlineKeyboardButton("🎯 Dashboard", callback_data="user_dashboard")],
        [InlineKeyboardButton("🛠 Admin Dashboard", callback_data="admin_dashboard")]
    ]

    text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
👋 <b>Hello! Welcome To Our Official Telegram Bot</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ Join Channel  
2️⃣ Invite {REQUIRED_REFERRALS} friends  

🔗 <b>Your Link:</b>
{ref_link}

👥 <b>Referrals:</b> {referrals}/{REQUIRED_REFERRALS}
"""

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# ================= VERIFY =================
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
    except:
        await query.answer("Bot must be admin in channel!", show_alert=True)
        return

    if member.status not in ["member", "administrator", "creator"]:
        await query.answer("❌ Join channel first!", show_alert=True)
        return

    cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    referrals = result[0] if result else 0

    if referrals < REQUIRED_REFERRALS:
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await query.message.reply_text(
            f"🚫 Need {REQUIRED_REFERRALS} referrals\n"
            f"👥 Yours: {referrals}\n\n{ref_link}"
        )
        return

    await query.message.reply_text("✅ Access granted! Send your message.")

# ================= USER MESSAGE =================
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = int(time.time())

    cursor.execute("SELECT referrals, last_message_time FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if not result:
        return

    referrals, last_time = result

    if now - last_time < COOLDOWN_SECONDS:
        await update.message.reply_text("⏳ Slow down...")
        return

    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
    except:
        return

    if member.status not in ["member", "administrator", "creator"] or referrals < REQUIRED_REFERRALS:
        return

    admins = get_all_admins()
    if not admins:
        await update.message.reply_text("No admin available.")
        return

    for admin_id in admins:
        try:
            sent = await context.bot.forward_message(
                chat_id=admin_id,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )

            cursor.execute(
                "INSERT INTO messages (msg_id, user_id) VALUES (?, ?)",
                (sent.message_id, user_id)
            )

        except:
            pass

    cursor.execute(
        "UPDATE users SET last_message_time=? WHERE user_id=?",
        (now, user_id)
    )
    conn.commit()

    await update.message.reply_text("📩 Sent to admin.")

# ================= ADMIN REPLY =================
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        return

    msg_id = update.message.reply_to_message.message_id

    cursor.execute("SELECT user_id FROM messages WHERE msg_id=?", (msg_id,))
    result = cursor.fetchone()
    if not result:
        return

    user_id = result[0]
    await context.bot.send_message(chat_id=user_id, text=update.message.text)

# ================= DASHBOARD =================
async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    data = query.data

    if data == "user_dashboard":
        keyboard = [
            [InlineKeyboardButton("👥 Referrals", callback_data="user_referrals")],
            [InlineKeyboardButton("🔗 Link", callback_data="user_link")]
        ]
        await query.message.reply_text("🎯 Dashboard", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "user_referrals":
        cursor.execute("SELECT referrals FROM users WHERE user_id=?", (user_id,))
        r = cursor.fetchone()[0]
        await query.message.reply_text(f"You have {r} referrals")

    elif data == "user_link":
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await query.message.reply_text(ref_link)

    elif data == "admin_dashboard":
        if not is_admin(user_id):
            return

        keyboard = [
            [InlineKeyboardButton("➕ Add Admin", callback_data="add_admin")],
            [InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]
        ]
        await query.message.reply_text("Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "add_admin":
        context.user_data["add_admin"] = True
        await query.message.reply_text("Send user ID")

    elif data == "remove_admin":
        context.user_data["remove_admin"] = True
        await query.message.reply_text("Send user ID")

    elif data == "broadcast":
        context.user_data["broadcast"] = True
        await query.message.reply_text("Send message to broadcast")

# ================= ADMIN ACTION HANDLER =================
async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if not is_admin(user_id):
        return

    # ADD ADMIN
    if context.user_data.get("add_admin"):
        try:
            target_id = int(text)
            cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (target_id,))
            conn.commit()
            await update.message.reply_text("✅ Admin added")
        except:
            await update.message.reply_text("❌ Invalid user ID")

        context.user_data["add_admin"] = False

    # REMOVE ADMIN
    elif context.user_data.get("remove_admin"):
        try:
            target_id = int(text)
            cursor.execute("DELETE FROM admins WHERE user_id=?", (target_id,))
            conn.commit()
            await update.message.reply_text("✅ Admin removed")
        except:
            await update.message.reply_text("❌ Invalid user ID")

        context.user_data["remove_admin"] = False

    # BROADCAST
    elif context.user_data.get("broadcast"):
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()

        count = 0
        for u in users:
            try:
                await context.bot.send_message(u[0], text)
                count += 1
            except:
                pass

        await update.message.reply_text(f"📢 Sent to {count} users")
        context.user_data["broadcast"] = False

# ================= ERROR HANDLER =================
async def error_handler(update, context):
    logging.error(f"Update {update} caused error {context.error}")

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # COMMAND
    app.add_handler(CommandHandler("start", start))

    # CALLBACKS
    app.add_handler(CallbackQueryHandler(verify, pattern="verify"))
    app.add_handler(CallbackQueryHandler(dashboard_callback))

    # ADMIN REPLY
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, handle_admin_reply))

    # ADMIN ACTION
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_handler), group=0)

    # USER MESSAGE
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message), group=1)

    # ERROR HANDLER
    app.add_error_handler(error_handler)

    print("🤖 Bot Running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()