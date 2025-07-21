import logging
from datetime import datetime
from functools import wraps
from typing import Dict, Any, List
import json
import os

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaAudio, InputMediaDocument
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext,
    ConversationHandler
)

# --- Config ---

TOKEN = "8160778255:AAFkAv4cWQ3UHUFsGVindhijYi3XPmoE40M"
ADMIN_IDS = [6194108258]  # <-- Replace with your admin Telegram user IDs

WELCOME_IMAGE = "https://i.postimg.cc/XYbnvLzV/1751575789815.jpg"
WELCOME_TEXT = "Welcome To MaxtonXBot. It's created by Robert Maxton."

DATA_FILE = "maxtonxbot_data.json"

# --- Data Storage (Use a real DB in production) ---

USERS: Dict[int, Dict[str, Any]] = {}
MENUS: Dict[str, List[Dict[str, Any]]] = {}  # Now each menu is a list of messages
BANNED_USERS: Dict[str, int] = {}

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "USERS": USERS,
                "MENUS": MENUS,
                "BANNED_USERS": BANNED_USERS
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

def load_data():
    global USERS, MENUS, BANNED_USERS
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                USERS = {int(k): v for k, v in data.get("USERS", {}).items()}
                # MENUS: deserialize as list of dicts for each menu
                MENUS = {k: v for k, v in data.get("MENUS", {}).items()}
                BANNED_USERS = data.get("BANNED_USERS", {})
        except Exception as e:
            print(f"Error loading data: {e}")

# --- States for ConversationHandler ---
(
    ADMIN_PANEL, MENU_CREATE_NAME, MENU_CREATE_COLLECT, MENU_CREATE_ADD_MORE, MENU_CONFIRM,
    MENU_EDIT_SELECT, MENU_EDIT_CHOICE, MENU_EDIT_NAME, MENU_EDIT_CONTENT,
    BROADCAST_CHOICE, BROADCAST_SINGLE_USER, BROADCAST_SINGLE_MSG, BROADCAST_ALL_MSG,
    MENU_DELETE_SELECT, MENU_DELETE_CONFIRM,
    BAN_ASK_USERNAME, UNBAN_ASK_USERNAME
) = range(17)

# --- Helpers ---

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("⛔ Admins only.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapped

def get_time_str():
    now = datetime.now()
    return now.strftime("%I:%M %p")

def get_date_str():
    now = datetime.now()
    return now.strftime("%d-%m-%Y")

def get_username(user):
    return f"@{user.username}" if user.username else "N/A"

def username_without_at(user):
    return f"{user.username}" if user.username else ""

def build_user_keyboard(is_admin_user=False):
    buttons = [
        [KeyboardButton("🏠 Home"), KeyboardButton("🔙 Back")]
    ]
    menu_buttons = [KeyboardButton(f"📚 {m}") for m in MENUS]
    if menu_buttons:
        buttons.append(menu_buttons)
    if is_admin_user:
        buttons.insert(0, [KeyboardButton("📂 Admin Panel")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def build_admin_panel_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📁 Menu Create"), KeyboardButton("📊 Statistics")],
        [KeyboardButton("🗑️ Menu Delete"), KeyboardButton("📝 Menu Editor")],
        [KeyboardButton("📢 Broadcast")],
        [KeyboardButton("🚫 Ban User"), KeyboardButton("✅ Unban User")],
        [KeyboardButton("🏠 Home"), KeyboardButton("🔙 Back")]
    ], resize_keyboard=True)

def build_save_cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("💾 Save"), KeyboardButton("❌ Cancel")]], resize_keyboard=True)

def build_add_more_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Add More"), KeyboardButton("💾 Save"), KeyboardButton("❌ Cancel")]
    ], resize_keyboard=True)

# --- Handlers ---

async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = user.id
    if username_without_at(user) in BANNED_USERS:
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return ConversationHandler.END

    first_time = user_id not in USERS
    if first_time:
        USERS[user_id] = {
            "name": user.full_name,
            "username": get_username(user),
            "join_date": get_date_str(),
            "join_time": get_time_str()
        }
        save_data()
        # Notify admin(s)
        text = (
            "🔔 New User Joined!\n"
            f"👤 Name: {user.full_name}\n"
            f"🆔 Username: {get_username(user)}\n"
            f"📅 Join Date: {get_date_str()}\n"
            f"⏰ Join Time: {get_time_str()}\n"
            f"👥 Total Users: {len(USERS)}"
        )
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(admin_id, text)
    # Welcome
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=WELCOME_IMAGE,
        caption=WELCOME_TEXT,
        reply_markup=build_user_keyboard(is_admin(user_id))
    )

async def user_menu_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    text = update.message.text
    user_id = user.id

    if username_without_at(user) in BANNED_USERS:
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return ConversationHandler.END

    if text == "🏠 Home":
        await update.message.reply_text("🏠 Home", reply_markup=build_user_keyboard(is_admin(user_id)))
    elif text == "🔙 Back":
        await update.message.reply_text("🔙 Back", reply_markup=build_user_keyboard(is_admin(user_id)))
    elif text.startswith("📚 "):
        menu_name = text.replace("📚 ", "", 1)
        menu_msgs = MENUS.get(menu_name)
        if menu_msgs:
            # Send all messages in the menu, one by one (serially)
            for msg in menu_msgs:
                await send_menu_msg(update, context, msg)
        else:
            await update.message.reply_text("Menu not found.")
    elif text == "📂 Admin Panel" and is_admin(user_id):
        await update.message.reply_text("📂 Admin Panel", reply_markup=build_admin_panel_keyboard())
        return ADMIN_PANEL

async def send_menu_msg(update, context, msg):
    chat_id = update.effective_chat.id
    t = msg['type']
    if t == 'text':
        await context.bot.send_message(chat_id, msg['content'])
    elif t == 'photo':
        await context.bot.send_photo(chat_id, msg['media_id'], caption=msg.get('caption', ''))
    elif t == 'video':
        await context.bot.send_video(chat_id, msg['media_id'], caption=msg.get('caption', ''))
    elif t == 'audio':
        await context.bot.send_audio(chat_id, msg['media_id'], caption=msg.get('caption', ''))
    elif t == 'document':
        await context.bot.send_document(chat_id, msg['media_id'], caption=msg.get('caption', ''))

# --- Admin Panel Flows ---

@admin_only
async def admin_panel_handler(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "📁 Menu Create":
        await update.message.reply_text("📝 Enter menu name:", reply_markup=None)
        return MENU_CREATE_NAME
    elif text == "📊 Statistics":
        msg = "\n".join(
            [f"👤 {user['name']}\n🆔 {user['username']}\n📅 {user['join_date']}\n⏰ {user['join_time']}\n" 
             for user in USERS.values()]
        )
        await update.message.reply_text(
            f"{msg}\n👥 Total Users: {len(USERS)}",
            reply_markup=build_admin_panel_keyboard()
        )
    elif text == "🗑️ Menu Delete":
        if not MENUS:
            await update.message.reply_text("No menus to delete.", reply_markup=build_admin_panel_keyboard())
            return ADMIN_PANEL
        menu_buttons = [[KeyboardButton(m)] for m in MENUS]
        await update.message.reply_text(
            "Select a menu to delete:",
            reply_markup=ReplyKeyboardMarkup(menu_buttons + [[KeyboardButton("🔙 Back")]], resize_keyboard=True)
        )
        return MENU_DELETE_SELECT
    elif text == "📝 Menu Editor":
        if not MENUS:
            await update.message.reply_text("No menus to edit.", reply_markup=build_admin_panel_keyboard())
            return ADMIN_PANEL
        menu_buttons = [[KeyboardButton(m)] for m in MENUS]
        await update.message.reply_text(
            "Send menu name to edit:",
            reply_markup=ReplyKeyboardMarkup(menu_buttons + [[KeyboardButton("🔙 Back")]], resize_keyboard=True)
        )
        return MENU_EDIT_SELECT
    elif text == "📢 Broadcast":
        await update.message.reply_text(
            "Choose:\n👤 Single User Send Message\n👥 All Users Send Message",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("👤 Single User Send Message")],
                [KeyboardButton("👥 All Users Send Message")],
                [KeyboardButton("🏠 Home"), KeyboardButton("🔙 Back")]
            ], resize_keyboard=True)
        )
        return BROADCAST_CHOICE
    elif text == "🚫 Ban User":
        await update.message.reply_text("Enter username to ban (with or without @):")
        return BAN_ASK_USERNAME
    elif text == "✅ Unban User":
        await update.message.reply_text("Enter username to unban (with or without @):")
        return UNBAN_ASK_USERNAME
    elif text in ["🏠 Home", "🔙 Back"]:
        await update.message.reply_text("Back to Home.", reply_markup=build_user_keyboard(True))
        return ConversationHandler.END
    else:
        await update.message.reply_text("Unknown admin command.", reply_markup=build_admin_panel_keyboard())
        return ADMIN_PANEL

# --- Menu Create (Multiple Messages) ---

async def menu_create_name(update: Update, context: CallbackContext):
    name = update.message.text.strip()
    if name in MENUS:
        await update.message.reply_text("Menu already exists. Choose another name.")
        return MENU_CREATE_NAME
    context.user_data['new_menu_name'] = name
    context.user_data['new_menu_msgs'] = []
    await update.message.reply_text("📤 Send content for this menu (text/photo/video/audio/document). When done, press 💾 Save. You can add multiple messages. To cancel, press ❌ Cancel.", reply_markup=build_add_more_keyboard())
    return MENU_CREATE_COLLECT

async def menu_create_collect(update: Update, context: CallbackContext):
    msg = update.message
    # Accept text, photo, video, audio, document
    new_msg = None
    if msg.text and msg.text not in ("💾 Save", "❌ Cancel", "➕ Add More"):
        new_msg = {'type': 'text', 'content': msg.text}
    elif msg.photo:
        photo = msg.photo[-1]
        caption = msg.caption or ""
        new_msg = {'type': 'photo', 'media_id': photo.file_id, 'caption': caption}
    elif msg.video:
        caption = msg.caption or ""
        new_msg = {'type': 'video', 'media_id': msg.video.file_id, 'caption': caption}
    elif msg.audio:
        caption = msg.caption or ""
        new_msg = {'type': 'audio', 'media_id': msg.audio.file_id, 'caption': caption}
    elif msg.document:
        caption = msg.caption or ""
        new_msg = {'type': 'document', 'media_id': msg.document.file_id, 'caption': caption}

    if new_msg:
        context.user_data['new_menu_msgs'].append(new_msg)
        await msg.reply_text("📥 Content received. Add more or press 💾 Save.", reply_markup=build_add_more_keyboard())
        return MENU_CREATE_COLLECT
    elif msg.text == "💾 Save":
        if not context.user_data['new_menu_msgs']:
            await msg.reply_text("Please add at least one message before saving.", reply_markup=build_add_more_keyboard())
            return MENU_CREATE_COLLECT
        name = context.user_data['new_menu_name']
        MENUS[name] = context.user_data['new_menu_msgs']
        save_data()
        await msg.reply_text("✅ Menu & messages successfully added.", reply_markup=build_admin_panel_keyboard())
        context.user_data.pop('new_menu_name', None)
        context.user_data.pop('new_menu_msgs', None)
        return ADMIN_PANEL
    elif msg.text == "❌ Cancel":
        await msg.reply_text("Cancelled.", reply_markup=build_admin_panel_keyboard())
        context.user_data.pop('new_menu_name', None)
        context.user_data.pop('new_menu_msgs', None)
        return ADMIN_PANEL
    elif msg.text == "➕ Add More":
        await msg.reply_text("Send another message (text/photo/video/audio/document).", reply_markup=build_add_more_keyboard())
        return MENU_CREATE_COLLECT
    else:
        await msg.reply_text("Please send a valid message (text/photo/video/audio/document) or use the buttons.", reply_markup=build_add_more_keyboard())
        return MENU_CREATE_COLLECT

# --- Menu Delete ---

async def menu_delete_select(update: Update, context: CallbackContext):
    menu_to_delete = update.message.text.strip()
    if menu_to_delete == "🔙 Back":
        await update.message.reply_text("Back to Admin Panel.", reply_markup=build_admin_panel_keyboard())
        return ADMIN_PANEL
    if menu_to_delete not in MENUS:
        await update.message.reply_text("Menu not found or already deleted.", reply_markup=build_admin_panel_keyboard())
        return ADMIN_PANEL
    context.user_data['delete_menu'] = menu_to_delete
    await update.message.reply_text(
        f'Are you sure you want to delete "{menu_to_delete}"?',
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("✅ Yes, delete")],
                [KeyboardButton("❌ Cancel")]
            ],
            resize_keyboard=True
        )
    )
    return MENU_DELETE_CONFIRM

async def menu_delete_confirm(update: Update, context: CallbackContext):
    text = update.message.text
    menu_name = context.user_data.get('delete_menu')
    if text == "✅ Yes, delete":
        if menu_name in MENUS:
            MENUS.pop(menu_name)
            save_data()
            await update.message.reply_text(
                f'Menu "{menu_name}" deleted.',
                reply_markup=build_admin_panel_keyboard()
            )
        else:
            await update.message.reply_text("Menu already deleted.", reply_markup=build_admin_panel_keyboard())
        return ADMIN_PANEL
    elif text == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=build_admin_panel_keyboard())
        return ADMIN_PANEL

# --- Ban/Unban User ---

async def ban_ask_username(update: Update, context: CallbackContext):
    username = update.message.text.replace('@', '').strip()
    if not username:
        await update.message.reply_text("Please enter a valid username to ban.")
        return BAN_ASK_USERNAME

    for uid, user in USERS.items():
        if user['username'].replace('@', '') == username:
            BANNED_USERS[username] = uid
            save_data()
            await update.message.reply_text(f"🚫 User @{username} has been banned.", reply_markup=build_admin_panel_keyboard())
            try:
                await context.bot.send_message(uid, "🚫 You have been banned by the admin.")
            except Exception:
                pass
            return ADMIN_PANEL
    await update.message.reply_text("User not found or never started the bot.", reply_markup=build_admin_panel_keyboard())
    return ADMIN_PANEL

async def unban_ask_username(update: Update, context: CallbackContext):
    username = update.message.text.replace('@', '').strip()
    if not username:
        await update.message.reply_text("Please enter a valid username to unban.")
        return UNBAN_ASK_USERNAME

    if username in BANNED_USERS:
        BANNED_USERS.pop(username)
        save_data()
        await update.message.reply_text(f"✅ User @{username} has been unbanned.", reply_markup=build_admin_panel_keyboard())
    else:
        await update.message.reply_text("User was not banned.", reply_markup=build_admin_panel_keyboard())
    return ADMIN_PANEL

# --- Broadcast ---

async def broadcast_choice(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "👤 Single User Send Message":
        await update.message.reply_text("Enter username (with or without @):")
        return BROADCAST_SINGLE_USER
    elif text == "👥 All Users Send Message":
        await update.message.reply_text("Send message to broadcast to all users:")
        return BROADCAST_ALL_MSG

async def broadcast_single_user(update: Update, context: CallbackContext):
    username = update.message.text.replace('@', '').strip()
    for uid, user in USERS.items():
        if user['username'].replace('@', '') == username:
            context.user_data['broadcast_uid'] = uid
            await update.message.reply_text("Send your message:")
            return BROADCAST_SINGLE_MSG
    await update.message.reply_text("User not found. Try again.")
    return BROADCAST_SINGLE_USER

async def broadcast_single_msg(update: Update, context: CallbackContext):
    uid = context.user_data['broadcast_uid']
    msg = update.message
    try:
        if msg.text and not msg.photo and not msg.video and not msg.audio and not msg.document:
            await context.bot.send_message(uid, msg.text)
        elif msg.photo:
            await context.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
        elif msg.video:
            await context.bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
        elif msg.audio:
            await context.bot.send_audio(uid, msg.audio.file_id, caption=msg.caption or "")
        elif msg.document:
            await context.bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
        await update.message.reply_text("Sent.", reply_markup=build_admin_panel_keyboard())
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}", reply_markup=build_admin_panel_keyboard())
    return ADMIN_PANEL

async def broadcast_all_msg(update: Update, context: CallbackContext):
    msg = update.message
    count = 0
    for uid in USERS:
        if USERS[uid]['username'].replace('@', '') in BANNED_USERS:
            continue
        try:
            if msg.text and not msg.photo and not msg.video and not msg.audio and not msg.document:
                await context.bot.send_message(uid, msg.text)
            elif msg.photo:
                await context.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.video:
                await context.bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            elif msg.audio:
                await context.bot.send_audio(uid, msg.audio.file_id, caption=msg.caption or "")
            elif msg.document:
                await context.bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"Broadcast sent to {count} users.", reply_markup=build_admin_panel_keyboard())
    return ADMIN_PANEL

# --- Main ---

def main():
    logging.basicConfig(level=logging.INFO)
    load_data()
    app = Application.builder().token(TOKEN).build()

    # Start and Home
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^(🏠 Home|🔙 Back|📚 .+)"), user_menu_handler))

    # Admin panel conversation
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📂 Admin Panel$"), admin_panel_handler)],
        states={
            ADMIN_PANEL: [MessageHandler(filters.TEXT, admin_panel_handler)],
            MENU_CREATE_NAME: [MessageHandler(filters.TEXT, menu_create_name)],
            MENU_CREATE_COLLECT: [MessageHandler(filters.ALL, menu_create_collect)],
            MENU_DELETE_SELECT: [MessageHandler(filters.TEXT, menu_delete_select)],
            MENU_DELETE_CONFIRM: [MessageHandler(filters.TEXT, menu_delete_confirm)],
            BROADCAST_CHOICE: [MessageHandler(filters.TEXT, broadcast_choice)],
            BROADCAST_SINGLE_USER: [MessageHandler(filters.TEXT, broadcast_single_user)],
            BROADCAST_SINGLE_MSG: [MessageHandler(filters.ALL, broadcast_single_msg)],
            BROADCAST_ALL_MSG: [MessageHandler(filters.ALL, broadcast_all_msg)],
            BAN_ASK_USERNAME: [MessageHandler(filters.TEXT, ban_ask_username)],
            UNBAN_ASK_USERNAME: [MessageHandler(filters.TEXT, unban_ask_username)],
        },
        fallbacks=[MessageHandler(filters.Regex("^(🏠 Home|🔙 Back)$"), admin_panel_handler)]
    )
    app.add_handler(admin_conv)

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()