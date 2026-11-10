import os
import re
import sys
import json
import uuid
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp
try:
    import standard_aifc as aifc
    import sys
    sys.modules['aifc'] = aifc
except Exception:
    pass

try:
    import speech_recognition as sr
except Exception:
    sr = None
from youtube_transcript_api import YouTubeTranscriptApi

BOT_TOKEN = "9223151517:AAHq3iZ2WjwWP72oCIReUzCaKL_4LDayaQw"
PRIMARY_OWNER_ID = 6181150735
BOT_USERNAME = "HeshamClipBot"

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "downloads"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGO_PATH = BASE_DIR / "logo.jpg"

FFMPEG_PATH = r"C:\Users\Alyousifi\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
if not os.path.exists(FFMPEG_PATH):
    FFMPEG_PATH = "ffmpeg"

CONFIG_FILE = BASE_DIR / "config.json"
DATA_FILE = BASE_DIR / "users.json"
ADMIN_FILE = BASE_DIR / "admin.json"
SUPPORT_MAP_FILE = BASE_DIR / "support_map.json"
ADMIN_REPLY_IDS_FILE = BASE_DIR / "admin_reply_ids.json"
COOKIE_FILE = BASE_DIR / "cookies.txt"

DEFAULT_CONFIG = {
    "initial_points": 10,
    "points_per_referral": 10,
    "daily_bonus": 5
}

def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path: Path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {path}: {e}", flush=True)

def get_config() -> dict:
    cfg = load_json(CONFIG_FILE, {})
    changed = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if changed:
        save_json(CONFIG_FILE, cfg)
    return cfg

def update_config(key: str, val: int):
    cfg = get_config()
    cfg[key] = int(val)
    save_json(CONFIG_FILE, cfg)

def get_initial_points() -> int:
    return int(get_config().get("initial_points", 10))

def get_points_per_referral() -> int:
    return int(get_config().get("points_per_referral", 10))

def get_daily_bonus() -> int:
    return int(get_config().get("daily_bonus", 5))

def get_admins() -> list[int]:
    data = load_json(ADMIN_FILE, {})
    admins = data.get("admins", [])
    if not isinstance(admins, list):
        admins = [data.get("admin_id")] if data.get("admin_id") else []
    if PRIMARY_OWNER_ID not in admins:
        admins.append(PRIMARY_OWNER_ID)
        save_json(ADMIN_FILE, {"admins": admins})
    return admins

def is_admin(user_id: int) -> bool:
    return user_id in get_admins()

def add_admin(user_id: int) -> bool:
    admins = get_admins()
    if user_id not in admins:
        admins.append(user_id)
        save_json(ADMIN_FILE, {"admins": admins})
        return True
    return False

def remove_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return False
    admins = get_admins()
    if user_id in admins:
        admins.remove(user_id)
        save_json(ADMIN_FILE, {"admins": admins})
        return True
    return False

def record_user(user, referrer_id=None):
    if not user:
        return
    users = load_json(DATA_FILE, {})
    uid = str(user.id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    is_new = uid not in users
    if is_new:
        users[uid] = {
            "first_name": user.first_name or "",
            "username": user.username or "",
            "joined_at": now_str,
            "last_active": now_str,
            "points": get_initial_points(),
            "total_used": 0,
            "invited_by": str(referrer_id) if referrer_id and str(referrer_id) != uid else None,
            "referral_rewarded": False,
            "invited_count": 0,
            "last_daily_bonus": "",
            "lang": "ar"
        }
    else:
        users[uid]["last_active"] = now_str
        if "points" not in users[uid]:
            users[uid]["points"] = get_initial_points()
        if user.username:
            users[uid]["username"] = user.username
        if user.first_name:
            users[uid]["first_name"] = user.first_name

    save_json(DATA_FILE, users)
    return is_new

def get_user_lang(user_id: int) -> str:
    users = load_json(DATA_FILE, {})
    return users.get(str(user_id), {}).get("lang", "ar")

def set_user_lang(user_id: int, lang: str):
    users = load_json(DATA_FILE, {})
    uid = str(user_id)
    if uid in users:
        users[uid]["lang"] = lang
        save_json(DATA_FILE, users)

def get_user_points(user_id: int) -> int:
    if is_admin(user_id):
        return 999999
    users = load_json(DATA_FILE, {})
    return users.get(str(user_id), {}).get("points", get_initial_points())

def deduct_user_point(user_id: int, amount: int = 1) -> bool:
    if is_admin(user_id):
        return True
    users = load_json(DATA_FILE, {})
    uid = str(user_id)
    pts = users.get(uid, {}).get("points", get_initial_points())
    if pts >= amount:
        users[uid]["points"] = pts - amount
        users[uid]["total_used"] = users[uid].get("total_used", 0) + 1
        save_json(DATA_FILE, users)
        return True
    return False

def set_user_points(user_id: int, points: int) -> bool:
    users = load_json(DATA_FILE, {})
    uid = str(user_id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if uid not in users:
        users[uid] = {
            "first_name": "مستخدم",
            "username": "",
            "joined_at": now_str,
            "last_active": now_str,
            "points": int(points),
            "total_used": 0,
            "invited_by": None,
            "referral_rewarded": False,
            "invited_count": 0,
            "last_daily_bonus": "",
            "lang": "ar"
        }
    else:
        users[uid]["points"] = int(points)
    save_json(DATA_FILE, users)
    return True

def add_user_points(user_id: int, points: int) -> int:
    users = load_json(DATA_FILE, {})
    uid = str(user_id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if uid not in users:
        users[uid] = {
            "first_name": "مستخدم",
            "username": "",
            "joined_at": now_str,
            "last_active": now_str,
            "points": get_initial_points() + int(points),
            "total_used": 0,
            "invited_by": None,
            "referral_rewarded": False,
            "invited_count": 0,
            "last_daily_bonus": "",
            "lang": "ar"
        }
    else:
        users[uid]["points"] = users[uid].get("points", 0) + int(points)
    save_json(DATA_FILE, users)
    return users[uid]["points"]

async def check_and_reward_referrer(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    users = load_json(DATA_FILE, {})
    uid = str(user_id)
    user_info = users.get(uid, {})
    referrer_str = user_info.get("invited_by")
    rewarded = user_info.get("referral_rewarded", False)

    if referrer_str and not rewarded and referrer_str in users:
        users[uid]["referral_rewarded"] = True
        referrer_id = int(referrer_str)
        ref_reward = get_points_per_referral()
        users[referrer_str]["points"] = users[referrer_str].get("points", 0) + ref_reward
        users[referrer_str]["invited_count"] = users[referrer_str].get("invited_count", 0) + 1
        save_json(DATA_FILE, users)

        try:
            invited_name = user_info.get("first_name", "صديقك")
            new_bal = users[referrer_str]["points"]
            lang = get_user_lang(referrer_id)
            if lang == "en":
                reward_msg = (
                    f"🎉 **Congratulations! Your friend ({invited_name}) just used the bot!**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"➕ `+{ref_reward}` attempts added to your accumulated balance!\n"
                    f"💎 Current balance: `{new_bal}` attempts."
                )
            else:
                reward_msg = (
                    f"🎉 **تهانينا! صديقك ({invited_name}) بدأ باستخدام البوت الآن!**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"➕ تمت إضافة `+{ref_reward}` محاولات إلى رصيدك التراكمي!\n"
                    f"💎 رصيدك الحالي أصبح: `{new_bal}` محاولة."
                )
            await context.bot.send_message(chat_id=referrer_id, text=reward_msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"Error sending referral reward notification: {e}", flush=True)

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def get_main_keyboard(user_id: int):
    lang = get_user_lang(user_id)
    if lang == "en":
        keyboard = [
            [KeyboardButton("🎬 Main Menu"), KeyboardButton("💎 My Balance & Points")],
            [KeyboardButton("🌐 Language / اللغة"), KeyboardButton("ℹ️ Instructions & Help")],
            [KeyboardButton("💬 Contact Support")]
        ]
        if is_admin(user_id):
            keyboard.append([KeyboardButton("👑 Admin Panel")])
    else:
        keyboard = [
            [KeyboardButton("🎬 القائمة الرئيسية"), KeyboardButton("💎 رصيدي وتجميع النقاط")],
            [KeyboardButton("🌐 تغيير اللغة (Language)"), KeyboardButton("ℹ️ المساعدة والتعليمات")],
            [KeyboardButton("💬 التواصل مع الإدارة")]
        ]
        if is_admin(user_id):
            keyboard.append([KeyboardButton("👑 لوحة تحكم المدير")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def check_points_or_warn(chat_id, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if is_admin(user_id):
        return True
    pts = get_user_points(user_id)
    lang = get_user_lang(user_id)
    if pts <= 0:
        ref_link = get_referral_link(user_id)
        ref_pts = get_points_per_referral()
        daily_pts = get_daily_bonus()
        if lang == "en":
            share_url = f"https://t.me/share/url?url={ref_link}&text=Hesham%20Clip%20Bot%20-%20Download%20and%20cut%20videos!"
            msg = (
                "⛔ **Sorry, your attempts balance is zero!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎁 **How to get more free attempts?**\n\n"
                f"1. 🔗 **Share your referral link:**\n`{ref_link}`\n"
                f"*(Earn `+{ref_pts}` attempts whenever a friend starts using the bot)*\n\n"
                f"2. 🌟 **Daily Bonus:** Claim `+{daily_pts}` free attempts every 24 hours via 'My Balance' below."
            )
            keyboard = [
                [InlineKeyboardButton(f"📤 Share Bot (+{ref_pts} attempts)", url=share_url)],
                [InlineKeyboardButton("💎 Check Balance / Daily Bonus", callback_data="btn_check_points")]
            ]
        else:
            share_url = f"https://t.me/share/url?url={ref_link}&text=بوت%20هشام%20كليب%20الرهيب%20لتحميل%20وقص%20الفيديوهات!"
            msg = (
                "⛔ **عذراً، لقد نفد رصيد محاولاتك!**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎁 **كيف تجمع رصيد محاولات جديد؟**\n\n"
                f"1. 🔗 **شارك رابط الدعوة الخاص بك:**\n`{ref_link}`\n"
                f"*(تحصل على `+{ref_pts}` محاولات تتراكم برصيدك فور استخدام أي صديق للبوت)*\n\n"
                f"2. 🌟 **المكافأة اليومية:** احصل على `+{daily_pts}` محاولات مجانية كل 24 ساعة عبر زر 'رصيدي وتجميع النقاط' بالأسفل."
            )
            keyboard = [
                [InlineKeyboardButton(f"📤 مشاركة البوت لكسب {ref_pts} محاولات", url=share_url)],
                [InlineKeyboardButton("💎 فحص الرصيد / المكافأة اليومية", callback_data="btn_check_points")]
            ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        return False
    return True

def normalize_digits(s: str) -> str:
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    english_digits = "0123456789"
    for a, e in zip(arabic_digits, english_digits):
        s = s.replace(a, e)
    return s

def parse_time(time_str: str) -> float:
    time_str = normalize_digits(time_str.strip())
    if ":" in time_str:
        parts = time_str.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(time_str)

def parse_time_range(text: str):
    text = normalize_digits(text.strip())
    for sep in ['-', '–', '—', 'to', 'إلى', 'الى', ',', ';']:
        text = text.replace(sep, ' ')
    parts = text.split()
    if len(parts) != 2:
        return None, None
    try:
        s = parse_time(parts[0])
        e = parse_time(parts[1])
        return s, e
    except Exception:
        return None, None

def format_time(seconds: float) -> str:
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def format_upload_date(date_str: str) -> str:
    if not date_str or len(date_str) != 8:
        return date_str or "N/A"
    return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer = None
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer = int(arg.replace("ref_", ""))
            except Exception:
                referrer = None

    record_user(user, referrer_id=referrer)

    pts = get_user_points(user.id)
    ref_link = get_referral_link(user.id)
    lang = get_user_lang(user.id)
    ref_pts = get_points_per_referral()
    daily_pts = get_daily_bonus()

    if lang == "en":
        pts_display = f"`{pts}` attempts" if not is_admin(user.id) else "Unlimited ♾️ (Admin)"
        admin_tag = "\n\n👑 **You are an Admin!** Send /admin or use the bottom Admin button." if is_admin(user.id) else ""
        caption = (
            "🎬 **Welcome to Hesham Clip Bot (@HeshamClipBot)** ✨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **Your Current Balance:** {pts_display}\n"
            f"*(Earn `+{ref_pts}` attempts for every friend who joins & uses the bot)*\n\n"
            "🛠️ **Features:**\n"
            "• 📥 **Video Downloader** with instant thumbnail preview from all platforms.\n"
            "• ✂️ **Precise Video Trimming** by seconds or minutes.\n"
            "• 🎵 **Extract High Quality Audio to MP3**.\n"
            "• 🎙️ **High-Accuracy Speech-to-Text** for videos & voice notes.\n"
            "• 📝 **Copy Caption & Description** with 1 click.\n\n"
            f"🔗 **Your Referral Link:**\n`{ref_link}`"
            f"{admin_tag}"
        )
        inline_kb = [
            [InlineKeyboardButton(f"📤 Share Bot (+{ref_pts} attempts)", url=f"https://t.me/share/url?url={ref_link}&text=Check%20out%20Hesham%20Clip%20Bot!")],
            [InlineKeyboardButton("💎 My Balance & Daily Bonus", callback_data="btn_check_points")]
        ]
    else:
        pts_display = f"`{pts}` محاولة" if not is_admin(user.id) else "غير محدود ♾️ (مدير)"
        admin_tag = "\n\n👑 **أنت مدير معتمد للبوت!** للتحكم أرسل /admin أو اضغط على زر لوحة المدير." if is_admin(user.id) else ""
        caption = (
            "🎬 **مرحباً بك في بوت هشام كليب (@HeshamClipBot)** ✨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **رصيد محاولاتك الحالي:** {pts_display}\n"
            f"*(تكسب `+{ref_pts}` محاولات تتراكم برصيدك لكل صديق يدخل ويستخدم البوت عبرك)*\n\n"
            "🛠️ **خدمات البوت المتاحة:**\n"
            "• 📥 **تحميل الفيديوهات** بمعاينة مباشرة وجودة عالية من جميع المنصات.\n"
            "• ✂️ **قص أي مقطع محدد** بدقة بالثواني أو الدقائق.\n"
            "• 🎵 **تحويل واستخراج الصوت بصيغة MP3**.\n"
            "• 🎙️ **تحويل الفيديو والتسجيلات الصوتية إلى نصوص مكتوبة** بأعلى دقة.\n"
            "• 📝 **نسخ الكابشن والوصف كاملاً** بنقرة واحدة.\n\n"
            f"🔗 **رابط الدعوة الخاص بك:**\n`{ref_link}`"
            f"{admin_tag}"
        )
        inline_kb = [
            [InlineKeyboardButton(f"📤 مشاركة البوت وتجميع رصيد (+{ref_pts})", url=f"https://t.me/share/url?url={ref_link}&text=بوت%20هشام%20كليب%20الرهيب%20لتحميل%20وقص%20الفيديوهات%20وتحويلها%20إلى%20نص!")],
            [InlineKeyboardButton("💎 رصيدي والمكافأة اليومية", callback_data="btn_check_points")]
        ]

    reply_markup_inline = InlineKeyboardMarkup(inline_kb)
    reply_kb = get_main_keyboard(user.id)

    if LOGO_PATH.exists():
        with open(LOGO_PATH, 'rb') as photo:
            await update.message.reply_photo(photo=photo, caption=caption, reply_markup=reply_markup_inline, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(caption, reply_markup=reply_markup_inline, parse_mode=ParseMode.MARKDOWN)

    kb_hint = "👇 Use the quick buttons below:" if lang == "en" else "👇 استخدم شريط الاختصارات بالأسفل للتحكم السريع:"
    await update.message.reply_text(kb_hint, reply_markup=reply_kb)

async def show_points_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_user(user)
    users = load_json(DATA_FILE, {})
    uinfo = users.get(str(user.id), {})

    pts = get_user_points(user.id)
    lang = get_user_lang(user.id)
    invited = uinfo.get("invited_count", 0)
    total_used = uinfo.get("total_used", 0)
    ref_link = get_referral_link(user.id)

    ref_pts = get_points_per_referral()
    daily_pts = get_daily_bonus()

    if lang == "en":
        pts_display = f"`{pts}` attempts" if not is_admin(user.id) else "Unlimited ♾️"
        text = (
            "💎 **Your Account & Points System:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {user.first_name}\n"
            f"⭐ **Accumulated Balance:** {pts_display}\n"
            f"👥 **Friends Joined via you:** `{invited}` users\n"
            f"📊 **Total Operations:** `{total_used}`\n\n"
            "🚀 **How to increase your balance?**\n"
            f"• Share your link below: get `+{ref_pts}` attempts whenever someone joins and uses the bot!\n"
            f"• Claim `+{daily_pts}` free bonus attempts every 24 hours.\n\n"
            f"🔗 **Your Referral Link (Tap to copy):**\n`{ref_link}`"
        )
        keyboard = [
            [InlineKeyboardButton(f"📤 Share Link (+{ref_pts} attempts)", url=f"https://t.me/share/url?url={ref_link}&text=Try%20Hesham%20Clip%20Bot!")],
            [InlineKeyboardButton(f"🌟 Claim Daily Bonus (+{daily_pts})", callback_data="claim_daily")]
        ]
    else:
        pts_display = f"`{pts}` محاولة" if not is_admin(user.id) else "غير محدود ♾️ (مدير)"
        text = (
            "💎 **بيانات حسابك ونظام تجميع الرصيد:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **المستخدم:** {user.first_name}\n"
            f"⭐ **رصيد المحاولات التراكمي:** {pts_display}\n"
            f"👥 **الأصدقاء الذين بدأوا الاستخدام عبرك:** `{invited}` شخص\n"
            f"📊 **إجمالي الخدمات المنفذة:** `{total_used}` خدمة\n\n"
            "🚀 **طرق تجميع وزيادة رصيدك:**\n"
            f"• شارك رابطك أدناه: ستحصل فوراً على `+{ref_pts}` محاولات لكل شخص يبدأ باستخدام البوت!\n"
            f"• اضغط زر **المكافأة اليومية** للحصول على `+{daily_pts}` محاولات مجانية كل يوم.\n\n"
            f"🔗 **رابطك الخاص (انقر للنسخ):**\n`{ref_link}`"
        )
        keyboard = [
            [InlineKeyboardButton(f"📤 مشاركة الرابط مع الأصدقاء (+{ref_pts})", url=f"https://t.me/share/url?url={ref_link}&text=جرب%20بوت%20هشام%20كليب%20الرهيب%20لتحميل%20وقص%20الفيديوهات!")],
            [InlineKeyboardButton(f"🌟 المطالبة بالمكافأة اليومية (+{daily_pts})", callback_data="claim_daily")]
        ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_json(DATA_FILE, {})
    cur_lang = users.get(str(user.id), {}).get("lang", "ar")
    keyboard = [
        [InlineKeyboardButton("🇸🇦 العربية" + (" (الحالية)" if cur_lang == "ar" else ""), callback_data="set_lang_ar")],
        [InlineKeyboardButton("🇬🇧 English" + (" (Current)" if cur_lang == "en" else ""), callback_data="set_lang_en")]
    ]
    await update.message.reply_text("🌐 **اختر لغة واجهة البوت / Select Language:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(update.effective_user.id)
    if lang == "en":
        text = (
            "ℹ️ **Hesham Clip Bot Guide & Instructions:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "1. **Video Preview & Download:** Send any video link directly. A photo preview with download and trim options will appear.\n"
            "2. **Trim Specific Clip:** Click '✂️ Trim Clip' then send start and end times (e.g. `10 30` or `01:00 01:30`).\n"
            "3. **Audio to Text (Speech-to-Text):** Send/forward any voice note, MP3, or video note to get an instant, highly accurate transcript.\n"
            "4. **Extract MP3:** Convert any video link into high-quality MP3 audio.\n"
            "5. **Support & Direct Conversation:** Use '💬 Contact Support' or swipe to reply to any message from administration."
        )
    else:
        text = (
            "ℹ️ **دليل استخدام بوت هشام كليب (@HeshamClipBot):**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "1. **معاينة وتحميل الفيديو:** أرسل رابط الفيديو مباشرة ليظهر لك غلاف الفيديو ومعاينته مع خيارات التحميل والقص.\n"
            "2. **قص مقطع محدد:** اضغط على '✂️ قص مقطع محدد' ثم أرسل وقت البداية والنهاية (مثال: `10 30` أو `01:00 01:30`).\n"
            "3. **تحويل صوت إلى نص:** أرسل أي تسجيل صوتي، ملف MP3، أو فيديو دائري ليقوم البوت بتفريغه نصياً بأعلى دقة.\n"
            "4. **تحويل إلى MP3:** استخرج ملف صوتي نقي من أي رابط فيديو بنقرة زر.\n"
            "5. **المحادثة المباشرة مع الإدارة:** اضغط زر '💬 التواصل مع الإدارة' أو اسحب واعمل رد (Reply) على أي رسالة من الإدارة للرد عليهم مباشرة."
        )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def contact_support_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_lang(user.id)
    context.user_data['state'] = 'waiting_for_support_message'

    if lang == "en":
        msg = (
            "💬 **Contact Bot Administration:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Please write your message now (text, photo, voice note).\n"
            "It will be delivered directly to the administration!"
        )
    else:
        msg = (
            "💬 **التواصل المباشر مع إدارة البوت:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "أرسل الآن رسالتك أو استفسارك (نص، صورة، أو رسالة صوتية).\n"
            "وسيتم تسليمها فوراً لإدارة البوت وسيردون عليك هنا مباشرة!"
        )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

def get_points_settings_keyboard():
    daily = get_daily_bonus()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖ إنقاص (-1)", callback_data="admin_daily_dec"),
            InlineKeyboardButton(f"⭐ اليومي: {daily} محاولات", callback_data="admin_points_settings"),
            InlineKeyboardButton("➕ زيادة (+1)", callback_data="admin_daily_inc")
        ],
        [
            InlineKeyboardButton("🎯 3 يومياً", callback_data="admin_set_daily:3"),
            InlineKeyboardButton("🎯 4 يومياً", callback_data="admin_set_daily:4"),
            InlineKeyboardButton("🎯 5 يومياً", callback_data="admin_set_daily:5"),
            InlineKeyboardButton("🎯 10 يومياً", callback_data="admin_set_daily:10")
        ],
        [
            InlineKeyboardButton("✍️ تعديل رصيد مستخدم معين", callback_data="admin_ask_set_points")
        ],
        [
            InlineKeyboardButton("🔙 العودة للوحة الإدارة", callback_data="admin_back_to_panel")
        ]
    ])

def get_points_settings_text():
    return (
        "⚙️ **لوحة التحكم في الرصيد والنقاط اليومية:**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🌟 **المكافأة اليومية للمشتركين:** `{get_daily_bonus()}` محاولات كل 24 ساعة\n"
        f"🎁 **رصيد الترحيب للمشترك الجديد:** `{get_initial_points()}` محاولات\n"
        f"👥 **مكافأة دعوة الأصدقاء:** `+{get_points_per_referral()}` محاولات لكل مشترك نشط\n\n"
        "👇 **التحكم السريع في النقاط اليومية:**\n"
        "اضغط على الأزرار السريعة لتحديد الرصيد اليومي (3، 4، 5، أو 10 محاولات)، أو (+1 / -1).\n\n"
        "📌 **أوامر الإدارة المباشرة:**\n"
        "• `/setdaily <العدد>` : تحديد المحاولات اليومية (مثال: `/setdaily 4` أو `/setdaily 5`).\n"
        "• `/setpoints <User_ID> <النقاط>` : تحديد رصيد مشترك معين.\n"
        "• `/addpoints <User_ID> <النقاط>` : زيادة رصيد مشترك معين.\n"
        "• `/setinitial <النقاط>` : ضبط رصيد الترحيب للمشترك الجديد.\n"
        "• `/setref <النقاط>` : تحديد نقاط دعوة الأصدقاء."
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ هذا الأمر مخصص لمدراء البوت فقط.")
        return

    users = load_json(DATA_FILE, {})
    total_users = len(users)
    admins = get_admins()

    keyboard = [
        [InlineKeyboardButton("📊 إحصائيات المشتركين ومعرفاتهم", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ إعدادات الرصيد والنقاط اليومية", callback_data="admin_points_settings")],
        [InlineKeyboardButton("👥 قائمة المدراء", callback_data="admin_list_admins"), InlineKeyboardButton("📢 إرسال إذاعة (Broadcast)", callback_data="admin_ask_broadcast")],
        [InlineKeyboardButton("🖼️ إرسال صورة البروفايل الرسمية", callback_data="admin_send_logo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    panel_text = (
        "👑 **لوحة تحكم إدارة البوت**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 **إجمالي المستخدمين المسجلين:** `{total_users}` مستخدم\n"
        f"🛡️ **عدد المدراء المعتمدين:** `{len(admins)}`\n"
        f"🌟 **المكافأة اليومية الحالية:** `{get_daily_bonus()}` محاولات/يوم\n"
        f"🎁 **رصيد المشترك الجديد:** `{get_initial_points()}` محاولات\n\n"
        "📌 **أوامر التحكم بالرصيد والنقاط:**\n"
        "• `/setdaily <عدد>` : تحديد النقاط اليومية للمستخدمين (مثال: `/setdaily 5` أو `/setdaily 4`).\n"
        "• `/setpoints <User_ID> <نقاط>` : تحديد رصيد مشترك معين مباشرة.\n"
        "• `/addpoints <User_ID> <نقاط>` : إضافة نقاط لرصيد مشترك معين.\n"
        "• `/setinitial <نقاط>` : تحديد رصيد البداية للأعضاء الجدد.\n\n"
        "📌 **أوامر الإدارة العامة:**\n"
        "• للرد على أي رسالة دعم: اضغط زر **'✍️ رد على المستخدم'** المرفق مع الرسالة، أو اسحب واعمل رد (Reply) عليها مباشرة!\n"
        "• `/reply <User_ID> <الرد>` : إرسال رد مباشر لأي مستخدم بمعرفه.\n"
        "• `/broadcast <الرسالة>` : بث رسالة نصية فورية لجميع المشتركين.\n"
        "• `/addadmin <User_ID>` : إضافة مدير جديد.\n"
        "• `/removeadmin <User_ID>` : إزالة مدير."
    )
    await update.message.reply_text(panel_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def set_daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("⚠️ طريقة الاستخدام:\n`/setdaily 4` أو `/setdaily 5` (لتحديد المحاولات اليومية لكل مستخدم)", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        val = int(context.args[0].strip())
        if val < 0:
            val = 0
        update_config("daily_bonus", val)
        await update.message.reply_text(
            f"✅ **تم تحديث الرصيد اليومي بنجاح!**\n"
            f"🌟 أصبحت المكافأة اليومية لجميع المشتركين: `{val}` محاولات في اليوم.",
            parse_mode=ParseMode.MARKDOWN
        )
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إدخال رقم صحيح، مثلاً: `/setdaily 5`")

async def set_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ طريقة الاستخدام:\n`/setpoints <آيدي_المستخدم> <الرصيد>`\nمثال:\n`/setpoints 6181150735 20`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        target_uid = int(context.args[0].strip())
        pts = int(context.args[1].strip())
        set_user_points(target_uid, pts)
        await update.message.reply_text(f"✅ تم ضبط رصيد المستخدم `{target_uid}` إلى `{pts}` محاولة بنجاح!", parse_mode=ParseMode.MARKDOWN)
        try:
            lang = get_user_lang(target_uid)
            msg = f"🎁 **إشعار من الإدارة:**\nتم تحديث رصيد محاولاتك في البوت إلى: `{pts}` محاولة!" if lang != "en" else f"🎁 **Admin Notice:**\nYour bot attempts balance has been updated to: `{pts}` attempts!"
            await context.bot.send_message(chat_id=target_uid, text=msg, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    except ValueError:
        await update.message.reply_text("⚠️ يرجى التأكد من كتابة الآيدي وعدد النقاط بالأرقام.")

async def add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ طريقة الاستخدام:\n`/addpoints <آيدي_المستخدم> <النقاط_الإضافية>`\nمثال:\n`/addpoints 6181150735 10`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        target_uid = int(context.args[0].strip())
        added = int(context.args[1].strip())
        new_tot = add_user_points(target_uid, added)
        await update.message.reply_text(f"✅ تمت إضافة `+{added}` محاولات للمستخدم `{target_uid}` بنجاح! رصيده الآن: `{new_tot}`", parse_mode=ParseMode.MARKDOWN)
        try:
            lang = get_user_lang(target_uid)
            msg = f"🎉 **هدية من الإدارة!**\nتمت إضافة `+{added}` محاولات إضافية لرصيدك! رصيدك الحالي أصبح: `{new_tot}` محاولة." if lang != "en" else f"🎉 **Admin Gift!**\nYou received `+{added}` bonus attempts! Your balance is now: `{new_tot}` attempts."
            await context.bot.send_message(chat_id=target_uid, text=msg, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إدخال الآيدي والنقاط كأرقام صحيحة.")

async def set_initial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("⚠️ طريقة الاستخدام:\n`/setinitial 10` (لتحديد رصيد الترحيب للمشتركين الجدد)", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        val = int(context.args[0].strip())
        update_config("initial_points", max(0, val))
        await update.message.reply_text(f"✅ تم تحديد رصيد الترحيب للمشترك الجديد إلى: `{val}` محاولات.", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إدخال رقم صحيح.")

async def set_ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("⚠️ طريقة الاستخدام:\n`/setref 10` (لتحديد نقاط مكافأة دعوة الأصدقاء)", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        val = int(context.args[0].strip())
        update_config("points_per_referral", max(0, val))
        await update.message.reply_text(f"✅ تم تحديد مكافأة دعوة الأصدقاء إلى: `+{val}` محاولات.", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إدخال رقم صحيح.")

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ طريقة الاستخدام:\n`/reply <User_ID> نص الرد هنا`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        target_uid = int(context.args[0])
        reply_text = " ".join(context.args[1:])
        await send_admin_reply_to_user(target_uid, reply_text, context)
        await update.message.reply_text(f"✅ تم تسليم الرد للمستخدم `{target_uid}` بنجاح!", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ تعذر إرسال الرد للمستخدم: {e}")

async def send_admin_reply_to_user(target_uid: int, text_or_msg, context: ContextTypes.DEFAULT_TYPE, is_copy: bool = False):
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 الرد على الإدارة", callback_data="user_reply_to_admin")]
    ])
    
    reply_ids = load_json(ADMIN_REPLY_IDS_FILE, [])

    if is_copy:
        sent = await text_or_msg.copy(chat_id=target_uid, reply_markup=reply_markup)
        reply_ids.append(sent.message_id)
    else:
        sent = await context.bot.send_message(
            chat_id=target_uid,
            text=f"📬 **رد من إدارة البوت:**\n\n{text_or_msg}\n\n*(يمكنك الرد المباشر بالسحب Reply على هذه الرسالة للمتابعة)*",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        reply_ids.append(sent.message_id)

    # Keep last 500 message IDs
    if len(reply_ids) > 500:
        reply_ids = reply_ids[-500:]
    save_json(ADMIN_REPLY_IDS_FILE, reply_ids)

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("⚠️ يرجى كتابة الآيدي، مثال:\n`/addadmin 123456789`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        new_id = int(context.args[0].strip())
        if add_admin(new_id):
            await update.message.reply_text(f"✅ تم إضافة المعرف `{new_id}` كمدير للبوت بنجاح!", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("⚠️ هذا المستخدم موجود بالفعل في قائمة المدراء.")
    except ValueError:
        await update.message.reply_text("⚠️ الآيدي المدخل غير صحيح.")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    if not context.args or len(context.args) == 0:
        await update.message.reply_text("⚠️ يرجى كتابة الآيدي المراد حذفه:\n`/removeadmin 123456789`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        target_id = int(context.args[0].strip())
        if target_id == PRIMARY_OWNER_ID:
            await update.message.reply_text("⛔ لا يمكن إزالة المالك الأساسي للبوت.")
            return
        if remove_admin(target_id):
            await update.message.reply_text(f"✅ تم إزالة المعرف `{target_id}` من قائمة المدراء.", parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("⚠️ هذا المعرف ليس موجوداً في قائمة المدراء.")
    except ValueError:
        await update.message.reply_text("⚠️ الآيدي المدخل غير صحيح.")

async def execute_broadcast(msg_or_text, is_copy: bool, context: ContextTypes.DEFAULT_TYPE, origin_chat_id: int):
    users = load_json(DATA_FILE, {})
    user_ids = list(users.keys())

    status_msg = await context.bot.send_message(
        chat_id=origin_chat_id,
        text=f"📢 **جاري بدء البث إلى `{len(user_ids)}` مشترك...**",
        parse_mode=ParseMode.MARKDOWN
    )

    success = 0
    failed = 0

    for uid in user_ids:
        try:
            target_chat = int(uid)
            if is_copy:
                await msg_or_text.copy(chat_id=target_chat)
            else:
                await context.bot.send_message(
                    chat_id=target_chat,
                    text=f"📢 **إشعار من الإدارة:**\n\n{msg_or_text}"
                )
            success += 1
            await asyncio.sleep(0.04)
        except Exception as e:
            failed += 1
            print(f"Broadcast failed for user {uid}: {e}", flush=True)

    report = (
        "✅ **اكتملت عملية البث بنجاح!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"✔️ **تم الإرسال بنجاح إلى:** `{success}` مستخدم\n"
        f"✖️ **تعذر الإرسال إلى:** `{failed}` مستخدم (حظروا البوت)\n"
        f"📊 **نسبة الوصول:** `{(success / max(len(user_ids), 1)) * 100:.1f}%`"
    )
    await status_msg.edit_text(report, parse_mode=ParseMode.MARKDOWN)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ هذا الأمر مخصص للمدير فقط.")
        return

    reply = update.message.reply_to_message
    if reply:
        await execute_broadcast(reply, is_copy=True, context=context, origin_chat_id=update.message.chat_id)
        return

    broadcast_text = " ".join(context.args) if context.args else None
    if broadcast_text:
        await execute_broadcast(broadcast_text, is_copy=False, context=context, origin_chat_id=update.message.chat_id)
        return

    await update.message.reply_text("⚠️ اكتب: `/broadcast رسالتك` أو قم بالرد بـ `/broadcast` على أي منشور.", parse_mode=ParseMode.MARKDOWN)

def extract_video_info(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'socket_timeout': 15,
        'no_check_certificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if COOKIE_FILE.exists():
        ydl_opts['cookiefile'] = str(COOKIE_FILE)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
        res = "غير محدد"
        if info.get('resolution'):
            res = info['resolution']
        elif info.get('height'):
            res = f"{info['height']}p"

        desc = info.get('description') or ""
        uploader = info.get('uploader') or info.get('channel') or info.get('uploader_id') or "غير معروف"
        upload_date = format_upload_date(info.get('upload_date'))
        thumbnail = info.get('thumbnail')

        return {
            'title': info.get('title', 'فيديو بدون عنوان'),
            'channel': uploader,
            'duration': info.get('duration', 0),
            'quality': res,
            'upload_date': upload_date,
            'description': desc,
            'url': url,
            'id': info.get('id'),
            'thumbnail': thumbnail
        }

async def forward_support_to_admin(msg, user, context: ContextTypes.DEFAULT_TYPE):
    username_display = f"@{user.username}" if user.username else "بدون يوزر"
    support_map = load_json(SUPPORT_MAP_FILE, {})
    admins = get_admins()

    for aid in admins:
        try:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ رد على هذا المستخدم", callback_data=f"admin_reply_btn_{user.id}")]
            ])

            header = (
                f"📩 **رسالة دعم جديدة من مستخدم:**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **الاسم:** {user.first_name}\n"
                f"🆔 **معرف المستخدم (ID):** `{user.id}`\n"
                f"🔗 **اليوزر:** {username_display}\n"
                f"⏰ **التاريخ:** {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "*(للرد: اضغط زر الرد أدناه أو اسحب واعمل رد Reply على هذه الرسالة)*"
            )
            
            sent_header = await context.bot.send_message(chat_id=aid, text=header, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            support_map[str(sent_header.message_id)] = user.id

            sent_copy = await msg.copy(chat_id=aid)
            support_map[str(sent_copy.message_id)] = user.id

        except Exception as e:
            print(f"Failed to forward support to admin {aid}: {e}", flush=True)

    save_json(SUPPORT_MAP_FILE, support_map)

    lang = get_user_lang(user.id)
    confirm_text = "✅ **Your message has been sent to administration. We will reply shortly!**" if lang == "en" else "✅ **تم إرسال رسالتك إلى إدارة البوت بنجاح! سيتم الرد عليك قريباً.**"
    await msg.reply_text(confirm_text, parse_mode=ParseMode.MARKDOWN)

def find_target_user_from_admin_reply(admin_msg) -> int | None:
    reply = admin_msg.reply_to_message
    if not reply:
        return None

    support_map = load_json(SUPPORT_MAP_FILE, {})
    mid_str = str(reply.message_id)
    if mid_str in support_map:
        return int(support_map[mid_str])

    full_text = (reply.text or "") + " " + (reply.caption or "")
    match = re.search(r"(?:المعرف|ID):\s*`?(\d{7,12})`?", full_text)
    if match:
        return int(match.group(1))

    return None

def is_user_replying_to_admin_message(msg) -> bool:
    reply = msg.reply_to_message
    if not reply:
        return False
    
    # 1. Check if replied message is in ADMIN_REPLY_IDS_FILE
    reply_ids = load_json(ADMIN_REPLY_IDS_FILE, [])
    if reply.message_id in reply_ids:
        return True

    # 2. Check text or caption of the replied message
    full_text = (reply.text or "") + " " + (reply.caption or "")
    if "رد من إدارة البوت" in full_text or "Reply from Bot Admin" in full_text:
        return True

    return False

async def handle_url_or_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_user(user)

    text = update.message.text.strip()
    lang = get_user_lang(user.id)
    user_state = context.user_data.get('state', '')

    # --- 0. CANCEL WORD CHECK ---
    if text.lower() in ['/cancel', 'cancel', 'الغاء', 'إلغاء']:
        context.user_data['state'] = None
        cancel_txt = "✅ Operation cancelled. Send any video URL anytime!" if lang == "en" else "✅ تم إلغاء العملية بنجاح. أرسل أي رابط فيديو للبدء!"
        await update.message.reply_text(cancel_txt)
        return

    # --- 0.1 URL OVERRIDE: Any URL always resets waiting states & processes immediately! ---
    url_match = re.search(r'(https?://[^\s]+)', text)
    if url_match:
        context.user_data['state'] = None
        if not await check_points_or_warn(update.message.chat_id, user.id, context):
            return

        url = url_match.group(1)
        loading_text = "🔍 Checking URL and preparing video preview..." if lang == "en" else "🔍 جاري فحص الرابط وتجهيز معاينة الفيديو..."
        status_msg = await update.message.reply_text(loading_text)

        try:
            current_time = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, extract_video_info, url)
            
            context.user_data['current_video'] = info
            context.user_data['current_video']['send_time'] = current_time
            context.user_data['state'] = None

            desc_snippet = info['description'][:120].strip()
            no_caption_txt = "No caption available" if lang == "en" else "لا يوجد كابشن متوفر"
            desc_display = (desc_snippet + ("..." if len(info['description']) > 120 else "")) if desc_snippet else no_caption_txt
            
            pts = get_user_points(user.id)
            if lang == "en":
                pts_display = f"`{pts}` attempts" if not is_admin(user.id) else "Unlimited ♾️"
                report = (
                    f"🎬 **Video Details & Preview:**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 **Title:** {info['title']}\n"
                    f"👤 **Channel / Account:** {info['channel']}\n"
                    f"⏱️ **Duration:** {format_time(info['duration'])}\n"
                    f"🎯 **Best Quality:** {info['quality']}\n"
                    f"📅 **Date:** {info['upload_date']}\n"
                    f"💎 **Your Balance:** {pts_display}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📝 **Caption:**\n_{desc_display}_\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "👇 **Select action from buttons below:**"
                )
                keyboard = [
                    [
                        InlineKeyboardButton("📥 Download Full Video", callback_data="download_full"),
                        InlineKeyboardButton("🎵 Convert to MP3", callback_data="download_mp3")
                    ],
                    [
                        InlineKeyboardButton("✂️ Trim Clip", callback_data="ask_cut_range"),
                        InlineKeyboardButton("🎙️ Transcribe to Text", callback_data="transcribe_video")
                    ],
                    [
                        InlineKeyboardButton("📝 Copy Full Caption", callback_data="copy_caption"),
                        InlineKeyboardButton("📤 Share (+10)", url=f"https://t.me/share/url?url={get_referral_link(user.id)}&text=Hesham%20Clip%20Bot")
                    ]
                ]
            else:
                pts_display = f"`{pts}` محاولات" if not is_admin(user.id) else "غير محدود ♾️"
                report = (
                    f"🎬 **معاينة وتفاصيل الفيديو:**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 **العنوان:** {info['title']}\n"
                    f"👤 **القناة / الحساب:** {info['channel']}\n"
                    f"⏱️ **المدة:** {format_time(info['duration'])}\n"
                    f"🎯 **أعلى جودة:** {info['quality']}\n"
                    f"📅 **تاريخ النشر:** {info['upload_date']}\n"
                    f"💎 **رصيدك الحالي:** {pts_display}\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📝 **الكابشن:**\n_{desc_display}_\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "👇 **اختر الخدمة المطلوبة من الأزرار:**"
                )
                keyboard = [
                    [
                        InlineKeyboardButton("📥 تحميل الفيديو كاملاً", callback_data="download_full"),
                        InlineKeyboardButton("🎵 تحويل إلى MP3", callback_data="download_mp3")
                    ],
                    [
                        InlineKeyboardButton("✂️ قص مقطع محدد", callback_data="ask_cut_range"),
                        InlineKeyboardButton("🎙️ تحويل الفيديو إلى نص", callback_data="transcribe_video")
                    ],
                    [
                        InlineKeyboardButton("📝 نسخ الكابشن كامل", callback_data="copy_caption"),
                        InlineKeyboardButton("📤 مشاركة البوت (+10)", url=f"https://t.me/share/url?url={get_referral_link(user.id)}&text=بوت%20هشام%20كليب%20الرهيب")
                    ]
                ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            thumbnail_sent = False
            if info.get('thumbnail'):
                try:
                    await update.message.reply_photo(
                        photo=info['thumbnail'],
                        caption=report,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    thumbnail_sent = True
                    await status_msg.delete()
                except Exception as pe:
                    print(f"Error sending photo preview: {pe}", flush=True)

            if not thumbnail_sent:
                await status_msg.edit_text(report, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            err_msg = f"⚠️ Could not analyze video: {str(e)[:120]}" if lang == "en" else f"⚠️ تعذر تحليل الفيديو. تأكد أن الرابط متاح للعامة.\nالخطأ: {str(e)[:120]}"
            await status_msg.edit_text(err_msg)
        return

    # --- 1. ADMIN DIRECT REPLY TO A USER (BUTTON MODE OR STATE) ---
    if is_admin(user.id) and user_state.startswith("admin_replying_to_"):
        target_uid = int(user_state.replace("admin_replying_to_", ""))
        context.user_data['state'] = None
        try:
            await send_admin_reply_to_user(target_uid, text, context)
            await update.message.reply_text(f"✅ تم تسليم ردك للمستخدم `{target_uid}` بنجاح!", parse_mode=ParseMode.MARKDOWN)
            return
        except Exception as e:
            await update.message.reply_text(f"❌ فشل إرسال الرد للمستخدم: {e}")
            return

    # --- 2. ADMIN SWIPE-TO-REPLY ON A SUPPORT MESSAGE ---
    if is_admin(user.id) and update.message.reply_to_message:
        target_user_id = find_target_user_from_admin_reply(update.message)
        if target_user_id:
            try:
                await send_admin_reply_to_user(target_user_id, text, context)
                await update.message.reply_text(f"✅ تم إيصال ردك للمستخدم (`{target_user_id}`) بنجاح!", parse_mode=ParseMode.MARKDOWN)
                return
            except Exception as e:
                await update.message.reply_text(f"❌ تعذر تسليم الرد للمستخدم: {e}")
                return

    # --- 3. USER SWIPE-TO-REPLY TO AN ADMIN'S REPLY MESSAGE ---
    if update.message.reply_to_message and is_user_replying_to_admin_message(update.message):
        await forward_support_to_admin(update.message, user, context)
        return

    # --- 4. BOTTOM SHORTCUT BAR BUTTONS ---
    if text in ["🎬 القائمة الرئيسية", "🎬 Main Menu"]:
        await start_command(update, context)
        return
    elif text in ["💎 رصيدي وتجميع النقاط", "💎 My Balance & Points"]:
        await show_points_info(update, context)
        return
    elif text in ["🌐 تغيير اللغة (Language)", "🌐 Language / اللغة"]:
        await language_command(update, context)
        return
    elif text in ["ℹ️ المساعدة والتعليمات", "ℹ️ Instructions & Help"]:
        await help_command(update, context)
        return
    elif text in ["💬 التواصل مع الإدارة", "💬 Contact Support"]:
        await contact_support_prompt(update, context)
        return
    elif text in ["👑 لوحة تحكم المدير", "👑 Admin Panel"]:
        if is_admin(user.id):
            await admin_command(update, context)
        return

    # --- 5. USER IN SUPPORT MESSAGE INPUT STATE ---
    if user_state == 'waiting_for_support_message':
        context.user_data['state'] = None
        await forward_support_to_admin(update.message, user, context)
        return

    # --- 6. ADMIN IN BROADCAST STATE ---
    if user_state == 'waiting_for_broadcast_msg' and is_admin(user.id):
        context.user_data['state'] = None
        await execute_broadcast(update.message, is_copy=True, context=context, origin_chat_id=update.message.chat_id)
        return

    # --- 6.5 ADMIN IN SET USER POINTS STATE ---
    if user_state == 'waiting_for_admin_user_points' and is_admin(user.id):
        if text.strip() == '/cancel':
            context.user_data['state'] = None
            await update.message.reply_text("❌ تم إلغاء العملية.")
            return
        parts = text.strip().split()
        if len(parts) >= 2 and parts[0].isdigit() and (parts[1].isdigit() or (parts[1].startswith('-') and parts[1][1:].isdigit())):
            target_uid = int(parts[0])
            new_pts = int(parts[1])
            set_user_points(target_uid, new_pts)
            context.user_data['state'] = None
            await update.message.reply_text(f"✅ تم ضبط رصيد المشترك `{target_uid}` إلى `{new_pts}` محاولة بنجاح!", parse_mode=ParseMode.MARKDOWN)
            try:
                lang = get_user_lang(target_uid)
                msg = f"🎁 **إشعار من الإدارة:**\nتم تحديث رصيد محاولاتك في البوت إلى: `{new_pts}` محاولة!" if lang != "en" else f"🎁 **Admin Notice:**\nYour bot attempts balance has been updated to: `{new_pts}` attempts!"
                await context.bot.send_message(chat_id=target_uid, text=msg, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
            return
        else:
            await update.message.reply_text("⚠️ صيغة غير صحيحة. يرجى إرسال المعرف الرقمي متبوعاً بالرصيد، مثلاً:\n`6181150735 20`\nأو أرسل /cancel للإلغاء.", parse_mode=ParseMode.MARKDOWN)
            return

    # --- 7. USER IN CUTTING STATE (Only reached if message is NOT a URL) ---
    if user_state == 'waiting_for_cut_range':
        await handle_cut_input(update, context)
        return

    # --- 8. NO MATCHING HANDLER OR URL ---
    hint = "Please send a valid video URL (starting with http/https) or choose from the menu below." if lang == "en" else "يرجى إرسال رابط فيديو صالح (يبدأ بـ http أو https) أو استخدام أزرار القائمة بالأسفل."
    await update.message.reply_text(hint)

# High Accuracy Speech Recognition with Audio Preprocessing
def transcribe_audio_file(audio_path: str, lang: str = "ar") -> str:
    wav_path = audio_path + ".wav"
    try:
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", audio_path,
            "-af", "highpass=f=200,lowpass=f=3500,volume=1.5",
            "-ar", "16000",
            "-ac", "1",
            wav_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.energy_threshold = 300

        with sr.AudioFile(wav_path) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)

            primary_lang = "ar-SA" if lang == "ar" else "en-US"
            fallback_lang = "en-US" if lang == "ar" else "ar-SA"

            try:
                return r.recognize_google(audio_data, language=primary_lang)
            except sr.UnknownValueError:
                try:
                    return r.recognize_google(audio_data, language=fallback_lang)
                except Exception:
                    return "⚠️ Could not clearly recognize speech in the audio." if lang == "en" else "⚠️ تعذر التعرف على الكلام بوضوح في التسجيل."
            except Exception as e:
                return f"⚠️ Speech recognition error: {e}"
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

async def handle_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_user(user)

    # Check if admin is replying with audio
    if is_admin(user.id) and update.message.reply_to_message:
        target_uid = find_target_user_from_admin_reply(update.message)
        if target_uid:
            try:
                await send_admin_reply_to_user(target_uid, update.message, context, is_copy=True)
                await update.message.reply_text(f"✅ تم إرسال التسجيل الصوتي للمستخدم `{target_uid}` بنجاح!", parse_mode=ParseMode.MARKDOWN)
                return
            except Exception as e:
                await update.message.reply_text(f"❌ فشل الإرسال للمستخدم: {e}")
                return

    # Check if user is replying with voice to admin message
    if update.message.reply_to_message and is_user_replying_to_admin_message(update.message):
        await forward_support_to_admin(update.message, user, context)
        return

    # Check if this was a support message sent as audio
    if context.user_data.get('state') == 'waiting_for_support_message':
        context.user_data['state'] = None
        await forward_support_to_admin(update.message, user, context)
        return

    if not await check_points_or_warn(update.message.chat_id, user.id, context):
        return

    msg = update.message
    audio_obj = msg.voice or msg.audio or msg.video_note
    if not audio_obj:
        return

    lang = get_user_lang(user.id)
    wait_msg = "🎙️ Downloading & transcribing audio with high accuracy..." if lang == "en" else "🎙️ جاري تنزيل وتحويل المقطع الصوتي إلى نص بدقة عالية..."
    status = await msg.reply_text(wait_msg)

    file_id = uuid.uuid4().hex[:8]
    ext = ".ogg" if msg.voice else ".mp3"
    input_file = str(TEMP_DIR / f"{file_id}{ext}")

    try:
        tg_file = await audio_obj.get_file()
        await tg_file.download_to_drive(input_file)

        loop = asyncio.get_running_loop()
        transcribed = await loop.run_in_executor(None, transcribe_audio_file, input_file, lang)

        deduct_user_point(user.id, 1)
        await check_and_reward_referrer(user.id, context)

        pts = get_user_points(user.id)
        pts_display = f"`{pts}` attempts" if lang == "en" else f"`{pts}` محاولات"
        if is_admin(user.id):
            pts_display = "♾️"

        if lang == "en":
            result_msg = (
                "📝 **Transcribed Text:**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"```text\n{transcribed}\n```\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 Remaining Balance: {pts_display}"
            )
        else:
            result_msg = (
                "📝 **النص المستخرج من الصوت بدقة:**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"```text\n{transcribed}\n```\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 رصيد محاولاتك المتبقي: {pts_display}"
            )
        await status.edit_text(result_msg, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await status.edit_text(f"❌ Error processing audio: {str(e)[:150]}")
    finally:
        for f in TEMP_DIR.glob(f"{file_id}*"):
            try:
                os.remove(f)
            except Exception:
                pass

async def process_video_transcription(chat_id, user_id, context, video_data, status_msg):
    url = video_data['url']
    video_id = video_data.get('id')
    transcript_text = None
    lang = get_user_lang(user_id)

    if "youtube.com" in url or "youtu.be" in url:
        try:
            if not video_id:
                m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                if m:
                    video_id = m.group(1)

            if video_id:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ar', 'en', 'auto'])
                if transcript_list:
                    lines = [item['text'] for item in transcript_list]
                    transcript_text = " ".join(lines)
        except Exception:
            transcript_text = None

    if not transcript_text:
        wait_text = "⏳ Extracting audio track for transcription..." if lang == "en" else "⏳ جاري استخراج مسار الصوت لمعالجته بدقة عالية..."
        await status_msg.edit_text(wait_text)
        file_id = uuid.uuid4().hex[:8]
        audio_file = str(TEMP_DIR / f"{file_id}.mp3")

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, download_mp3_sync, url, audio_file)

            found = list(TEMP_DIR.glob(f"{file_id}*.mp3"))
            if found:
                actual_audio = str(found[0])
                wait_sub = "🎙️ Transcribing speech to text..." if lang == "en" else "🎙️ جاري تحويل الكلام في الفيديو إلى نص بدقة عالية..."
                await status_msg.edit_text(wait_sub)
                transcript_text = await loop.run_in_executor(None, transcribe_audio_file, actual_audio, lang)
            else:
                transcript_text = "Could not extract audio track." if lang == "en" else "تعذر استخراج الصوت."
        except Exception as e:
            transcript_text = f"Error: {e}"
        finally:
            for f in TEMP_DIR.glob(f"{file_id}*"):
                try:
                    os.remove(f)
                except Exception:
                    pass

    if not transcript_text or len(transcript_text.strip()) == 0:
        transcript_text = "No clear speech detected in the video." if lang == "en" else "لم يتم العثور على كلام واضح داخل الفيديو."

    deduct_user_point(user_id, 1)
    await check_and_reward_referrer(user_id, context)
    pts = get_user_points(user_id)
    pts_display = f"`{pts}`" if not is_admin(user_id) else "♾️"

    header_title = "Transcribed Text from Video" if lang == "en" else "النص المستخرج من الفيديو بدقة"
    footer = "Remaining attempts:" if lang == "en" else "رصيد محاولاتك المتبقي:"

    response = (
        f"📝 **{header_title}:**\n"
        f"🎬 **{video_data['title']}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"```text\n{transcript_text[:3800]}\n```\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 {footer} `{pts_display}`"
    )
    await status_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    lang = get_user_lang(user.id)

    # Admin one-click reply button handler
    if query.data.startswith("admin_reply_btn_"):
        if not is_admin(user.id):
            return
        target_uid = query.data.replace("admin_reply_btn_", "")
        context.user_data['state'] = f"admin_replying_to_{target_uid}"
        await query.message.reply_text(
            f"✍️ **أنت الآن تقوم بالرد على المستخدم صاحب المعرف:** `{target_uid}`\n"
            "أرسل الآن نص الرد أو رسالتك الصوتية مباشرة وسيتم إيصالها له فوراً:",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # User clicked reply to admin
    elif query.data == "user_reply_to_admin":
        context.user_data['state'] = 'waiting_for_support_message'
        prompt = "✍️ Write your message to the administration now:" if lang == "en" else "✍️ أرسل الآن ردك أو رسالتك لإدارة البوت:"
        await query.message.reply_text(prompt)
        return

    elif query.data == "btn_check_points":
        await show_points_info(update, context)
        return

    elif query.data == "claim_daily":
        users = load_json(DATA_FILE, {})
        uid = str(user.id)
        today = datetime.now().strftime("%Y-%m-%d")
        last_bonus = users.get(uid, {}).get("last_daily_bonus", "")
        daily_pts = get_daily_bonus()

        if last_bonus == today:
            already_msg = "⏳ You already claimed today's bonus! Come back tomorrow." if lang == "en" else "⏳ لقد استلمت مكافأتك اليومية بالفعل اليوم! عد غداً للحصول على مكافأة جديدة."
            await query.message.reply_text(already_msg)
        else:
            if uid not in users:
                record_user(user)
                users = load_json(DATA_FILE, {})
            users[uid]["last_daily_bonus"] = today
            users[uid]["points"] = users[uid].get("points", 0) + daily_pts
            save_json(DATA_FILE, users)
            if lang == "en":
                claimed_msg = (
                    f"🎉 **Congrats! You got `+{daily_pts}` bonus attempts!**\n"
                    f"💎 Current balance: `{users[uid]['points']}` attempts."
                )
            else:
                claimed_msg = (
                    f"🎉 **مبروك! حصلت على `+{daily_pts}` محاولات إضافية كمكافأة يومية!**\n"
                    f"💎 رصيدك التراكمي الآن: `{users[uid]['points']}` محاولة."
                )
            await query.message.reply_text(claimed_msg, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "set_lang_ar":
        set_user_lang(user.id, "ar")
        reply_kb = get_main_keyboard(user.id)
        await query.message.reply_text("✅ تم تغيير لغة البوت إلى: **العربية**\nتم تحديث الأزرار والواجهة بالكامل!", reply_markup=reply_kb, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "set_lang_en":
        set_user_lang(user.id, "en")
        reply_kb = get_main_keyboard(user.id)
        await query.message.reply_text("✅ Bot language changed to: **English**\nAll buttons & interface have been updated!", reply_markup=reply_kb, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "admin_stats":
        if not is_admin(user.id):
            return
        users = load_json(DATA_FILE, {})
        text = f"📊 **إحصائيات البوت التفصيلية ومعرفات المستخدمين:**\n"
        text += f"👥 **إجمالي المشتركين:** `{len(users)}` مستخدم\n\n"
        for i, (uid, u) in enumerate(users.items(), 1):
            uname = f"@{u.get('username')}" if u.get('username') else "بدون يوزر"
            text += (
                f"**{i}. {u.get('first_name', 'مستخدم')}** ({uname})\n"
                f"   🆔 **المعرف (ID):** `{uid}`\n"
                f"   💎 الرصيد: `{u.get('points', 0)}` | 🔄 العمليات: `{u.get('total_used', 0)}` | 👥 الدعوات: `{u.get('invited_count', 0)}`\n"
                f"   ⏰ آخر ظهور: `{u.get('last_active', 'N/A')}`\n"
                "──────────────────\n"
            )
            if len(text) > 3500:
                text += f"... والمزيد ({len(users) - i} مستخدم آخر)"
                break
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "admin_points_settings":
        if not is_admin(user.id):
            return
        await query.message.reply_text(get_points_settings_text(), reply_markup=get_points_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "admin_back_to_panel":
        if not is_admin(user.id):
            return
        users = load_json(DATA_FILE, {})
        admins = get_admins()
        keyboard = [
            [InlineKeyboardButton("📊 إحصائيات المشتركين ومعرفاتهم", callback_data="admin_stats")],
            [InlineKeyboardButton("⚙️ إعدادات الرصيد والنقاط اليومية", callback_data="admin_points_settings")],
            [InlineKeyboardButton("👥 قائمة المدراء", callback_data="admin_list_admins"), InlineKeyboardButton("📢 إرسال إذاعة (Broadcast)", callback_data="admin_ask_broadcast")],
            [InlineKeyboardButton("🖼️ إرسال صورة البروفايل الرسمية", callback_data="admin_send_logo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        panel_text = (
            "👑 **لوحة تحكم إدارة البوت**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **إجمالي المستخدمين المسجلين:** `{len(users)}` مستخدم\n"
            f"🛡️ **عدد المدراء المعتمدين:** `{len(admins)}`\n"
            f"🌟 **المكافأة اليومية الحالية:** `{get_daily_bonus()}` محاولات/يوم\n"
            f"🎁 **رصيد المشترك الجديد:** `{get_initial_points()}` محاولات\n\n"
            "📌 **أوامر التحكم بالرصيد:**\n"
            "• `/setdaily <عدد>` : تحديد النقاط اليومية (مثال: `/setdaily 5` أو `/setdaily 4`).\n"
            "• `/setpoints <User_ID> <نقاط>` : تحديد رصيد مشترك معين.\n"
            "• `/addpoints <User_ID> <نقاط>` : زيادة نقاط لرصيد مشترك.\n"
            "• `/setinitial <نقاط>` : تحديد رصيد البداية.\n\n"
            "📌 **أوامر الإدارة:**\n"
            "• للرد على الدعم: اضغط '✍️ رد على المستخدم' أو اسحب واعمل Reply مباشرة!\n"
            "• `/reply <User_ID> <الرد>` : إرسال رد مباشر بمعرف المشترك.\n"
            "• `/broadcast <الرسالة>` : بث رسالة لجميع المشتركين."
        )
        await query.message.edit_text(panel_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data.startswith("admin_set_daily:"):
        if not is_admin(user.id):
            return
        val = int(query.data.split(":")[1])
        update_config("daily_bonus", val)
        await query.answer(f"✅ تم ضبط المكافأة اليومية إلى {val} محاولات!", show_alert=True)
        try:
            await query.message.edit_text(get_points_settings_text(), reply_markup=get_points_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        return

    elif query.data == "admin_daily_inc":
        if not is_admin(user.id):
            return
        val = get_daily_bonus() + 1
        update_config("daily_bonus", val)
        await query.answer(f"تمت الزيادة إلى {val} محاولات يومياً")
        try:
            await query.message.edit_text(get_points_settings_text(), reply_markup=get_points_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        return

    elif query.data == "admin_daily_dec":
        if not is_admin(user.id):
            return
        val = max(1, get_daily_bonus() - 1)
        update_config("daily_bonus", val)
        await query.answer(f"تم الإنقاص إلى {val} محاولات يومياً")
        try:
            await query.message.edit_text(get_points_settings_text(), reply_markup=get_points_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        return

    elif query.data == "admin_ask_set_points":
        if not is_admin(user.id):
            return
        context.user_data['state'] = 'waiting_for_admin_user_points'
        await query.message.reply_text(
            "✍️ **أرسل الآن معرف المشترك والرصيد المطلوب مفصولين بمسافة:**\n\n"
            "مثال:\n`6181150735 25`\n\n"
            "*(أو أرسل /cancel للإلغاء)*",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    elif query.data == "admin_list_admins":
        if not is_admin(user.id):
            return
        admins = get_admins()
        text = "🛡️ **قائمة مدراء البوت المعتمدين:**\n\n"
        for i, aid in enumerate(admins, 1):
            owner_label = " (المالك الأساسي)" if aid == PRIMARY_OWNER_ID else ""
            text += f"{i}. `{aid}`{owner_label}\n"
        text += "\n💡 لإضافة مدير: `/addadmin <User_ID>`\n💡 لحذف مدير: `/removeadmin <User_ID>`"
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "admin_send_logo":
        if is_admin(user.id) and LOGO_PATH.exists():
            with open(LOGO_PATH, 'rb') as photo:
                await query.message.reply_photo(
                    photo=photo,
                    caption="🖼️ **الصورة الشخصية الرسمية للبوت جاهزة!**\n\nلوضعها كصورة بروفايل للبوت:\n1. افتح @BotFather\n2. أرسل `/setuserpic`\n3. اختر `@HeshamClipBot`\n4. أرسل له هذه الصورة مباشرة!",
                    parse_mode=ParseMode.MARKDOWN
                )
        return

    elif query.data == "admin_ask_broadcast":
        if not is_admin(user.id):
            return
        context.user_data['state'] = 'waiting_for_broadcast_msg'
        await query.message.reply_text("📢 **أرسل الآن أي منشور (نص، صورة، فيديو، أو صوت) وسيتم بثه فوراً لجميع المشتركين:**")
        return

    if not await check_points_or_warn(query.message.chat_id, user.id, context):
        return

    video_data = context.user_data.get('current_video')
    if not video_data:
        err = "Session expired, please resend video link." if lang == "en" else "انتهت صلاحية الجلسة، يرجى إعادة إرسال الرابط مجدداً."
        await query.message.reply_text(err)
        return

    if query.data == "download_full":
        wait_d = "⏳ Downloading video in best quality, please wait..." if lang == "en" else "⏳ جاري تنزيل الفيديو بأفضل جودة، يرجى الانتظار..."
        await query.message.reply_text(wait_d)
        asyncio.create_task(process_full_download(query, context, video_data, user.id))

    elif query.data == "download_mp3":
        wait_m = "🎵 Extracting MP3 audio..." if lang == "en" else "🎵 جاري استخراج الصوت بصيغة MP3..."
        await query.message.reply_text(wait_m)
        asyncio.create_task(process_mp3_download(query, context, video_data, user.id))

    elif query.data == "transcribe_video":
        wait_t = "🔍 Transcribing video speech to text..." if lang == "en" else "🔍 جاري استخراج وتحويل الكلام إلى نص بدقة..."
        status_msg = await query.message.reply_text(wait_t)
        asyncio.create_task(process_video_transcription(query.message.chat_id, user.id, context, video_data, status_msg))

    elif query.data == "copy_caption":
        desc = video_data.get('description', '').strip()
        if not desc:
            no_c = "⚠️ No description available for this video." if lang == "en" else "⚠️ لا يتوفر كابشن أو وصف لهذا الفيديو."
            await query.message.reply_text(no_c)
        else:
            header_cap = "📋 **Full Caption / Description (Tap to copy):**" if lang == "en" else "📋 **الكابشن / الوصف الكامل (جاهز للنسخ):**"
            full_caption_msg = f"{header_cap}\n\n```text\n{desc[:3900]}\n```"
            await query.message.reply_text(full_caption_msg, parse_mode=ParseMode.MARKDOWN)

    elif query.data == "ask_cut_range":
        context.user_data['state'] = 'waiting_for_cut_range'
        dur_note = f" (المدة: {format_time(video_data['duration'])})" if video_data.get('duration') else ""
        cancel_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء القص / Cancel", callback_data="cancel_action")]
        ])
        if lang == "en":
            msg = (
                f"✂️ **Trim Video Clip**{dur_note}\n\n"
                "Send start and end times separated by space or hyphen:\n"
                "• `00:10 00:35` (from 0:10 to 0:35)\n"
                "• `15 45` (seconds: 15 to 45)\n"
                "• `10-30` or `10 to 30`\n\n"
                "*(Or click Cancel below or send a new link directly)*"
            )
        else:
            msg = (
                f"✂️ **قص مقطع من الفيديو**{dur_note}\n\n"
                "أرسل وقت البداية والنهاية بأي صيغة تفضلها:\n"
                "• `00:10 00:35` (من 0:10 إلى 0:35)\n"
                "• `15 45` (بالثواني: من 15 إلى 45)\n"
                "• `10-30` أو `10 إلى 30`\n\n"
                "*(أو اضغط زر إلغاء بالأسفل أو أرسل رابط فيديو جديد مباشرة)*"
            )
        await query.message.reply_text(msg, reply_markup=cancel_kb, parse_mode=ParseMode.MARKDOWN)
        return

    elif query.data == "cancel_action":
        context.user_data['state'] = None
        txt = "✅ Operation cancelled. Send any video link anytime!" if lang == "en" else "✅ تم إلغاء العملية. يمكنك إرسال أي رابط فيديو مباشرة!"
        await query.message.reply_text(txt)
        return

def download_video_sync(url: str, output_path: str):
    ydl_opts = {
        'format': 'best[filesize<48M]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
        'quiet': True,
        'ffmpeg_location': FFMPEG_PATH,
        'concurrent_fragment_downloads': 5,
        'buffersize': 1024 * 64,
        'http_chunk_size': 10485760,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if COOKIE_FILE.exists():
        ydl_opts['cookiefile'] = str(COOKIE_FILE)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def download_mp3_sync(url: str, output_path: str):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'ffmpeg_location': FFMPEG_PATH,
        'concurrent_fragment_downloads': 5,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if COOKIE_FILE.exists():
        ydl_opts['cookiefile'] = str(COOKIE_FILE)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def cut_video_sync(input_path: str, output_path: str, start_sec: float, end_sec: float):
    duration = end_sec - start_sec
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "ultrafast",
        "-threads", "0",
        "-crf", "24",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

async def process_full_download(query, context: ContextTypes.DEFAULT_TYPE, video_data: dict, user_id: int):
    chat_id = query.message.chat_id
    file_id = uuid.uuid4().hex[:8]
    output_file = str(TEMP_DIR / f"{file_id}.mp4")
    lang = get_user_lang(user_id)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, download_video_sync, video_data['url'], output_file)

        if not os.path.exists(output_file):
            found = list(TEMP_DIR.glob(f"{file_id}.*"))
            if found:
                output_file = str(found[0])
            else:
                raise FileNotFoundError("Could not find downloaded file.")

        file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
        if file_size_mb > 49.5:
            oversize_msg = f"⚠️ Video size ({file_size_mb:.1f} MB) exceeds Telegram 50MB limit. Try trimming a clip instead." if lang == "en" else f"⚠️ حجم الفيديو ({file_size_mb:.1f} MB) يتجاوز الحد المسموح في تيليجرام (50 ميجابايت). يمكنك قص مقطع محدد منه بدلاً من ذلك."
            await context.bot.send_message(chat_id=chat_id, text=oversize_msg)
            return

        deduct_user_point(user_id, 1)
        await check_and_reward_referrer(user_id, context)
        pts = get_user_points(user_id)
        pts_display = f"`{pts}`" if not is_admin(user_id) else "♾️"

        caption = (
            f"🎬 **{video_data['title']}**\n👤 {video_data['channel']}\n💎 Balance: {pts_display}\n\nDownloaded by @HeshamClipBot" if lang == "en"
            else f"🎬 **{video_data['title']}**\n👤 {video_data['channel']}\n💎 رصيد محاولاتك: {pts_display}\n\nتم التحميل بواسطة @HeshamClipBot"
        )
        with open(output_file, 'rb') as vf:
            await context.bot.send_video(chat_id=chat_id, video=vf, caption=caption, supports_streaming=True, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error downloading: {str(e)[:150]}")
    finally:
        for f in TEMP_DIR.glob(f"{file_id}*"):
            try:
                os.remove(f)
            except Exception:
                pass

async def process_mp3_download(query, context: ContextTypes.DEFAULT_TYPE, video_data: dict, user_id: int):
    chat_id = query.message.chat_id
    file_id = uuid.uuid4().hex[:8]
    output_base = str(TEMP_DIR / f"{file_id}")
    mp3_file = str(TEMP_DIR / f"{file_id}.mp3")
    lang = get_user_lang(user_id)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, download_mp3_sync, video_data['url'], output_base)

        if not os.path.exists(mp3_file):
            found = list(TEMP_DIR.glob(f"{file_id}*.mp3"))
            if found:
                mp3_file = str(found[0])
            else:
                raise FileNotFoundError("Could not find MP3 file.")

        deduct_user_point(user_id, 1)
        await check_and_reward_referrer(user_id, context)
        pts = get_user_points(user_id)
        pts_display = f"`{pts}`" if not is_admin(user_id) else "♾️"

        caption = f"🎵 Extracted by @HeshamClipBot | Balance: {pts_display}" if lang == "en" else f"🎵 استخرج بواسطة @HeshamClipBot | محاولاتك: {pts_display}"

        with open(mp3_file, 'rb') as af:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=af,
                title=video_data['title'][:60],
                performer=video_data['channel'][:60],
                caption=caption
            )

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error extracting MP3: {str(e)[:150]}")
    finally:
        for f in TEMP_DIR.glob(f"{file_id}*"):
            try:
                os.remove(f)
            except Exception:
                pass

async def handle_cut_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    video_data = context.user_data.get('current_video')
    lang = get_user_lang(user.id)

    if not video_data:
        err = "Please send a video link first." if lang == "en" else "يرجى إرسال رابط فيديو أولاً."
        await update.message.reply_text(err)
        context.user_data['state'] = None
        return

    if not await check_points_or_warn(update.message.chat_id, user.id, context):
        return

    start_sec, end_sec = parse_time_range(text)
    if start_sec is None or end_sec is None:
        err_fmt = (
            "⚠️ **تنسيق التوقيت غير صالح!**\n\n"
            "أرسل وقت البداية والنهاية مفصولين بمسافة أو شرطة:\n"
            "• `00:10 00:35` (من 0:10 إلى 0:35)\n"
            "• `15 45` (بالثواني: من ثانية 15 إلى 45)\n"
            "• `10-30` أو `10 إلى 30`\n\n"
            "💡 أو أرسل `/cancel` لإلغاء القص وإرسال رابط فيديو جديد."
        ) if lang != "en" else (
            "⚠️ **Invalid time format!**\n\n"
            "Send start and end times separated by space or hyphen:\n"
            "• `00:10 00:35`\n"
            "• `15 45` (seconds)\n"
            "• `10-30`\n\n"
            "💡 Or send `/cancel` to abort."
        )
        await update.message.reply_text(err_fmt, parse_mode=ParseMode.MARKDOWN)
        return

    if start_sec >= end_sec:
        err_o = "⚠️ End time must be greater than start time." if lang == "en" else "⚠️ يجب أن يكون وقت النهاية أكبر من وقت البداية."
        await update.message.reply_text(err_o)
        return

    total_dur = video_data.get('duration')
    if total_dur and end_sec > total_dur:
        end_sec = total_dur

    context.user_data['state'] = None
    wait_trim = f"✂️ Trimming clip from `{format_time(start_sec)}` to `{format_time(end_sec)}`..." if lang == "en" else f"✂️ جاري قص الفيديو من `{format_time(start_sec)}` إلى `{format_time(end_sec)}`..."
    status_msg = await update.message.reply_text(wait_trim, parse_mode=ParseMode.MARKDOWN)

    asyncio.create_task(process_cut_and_send(update.message.chat_id, user.id, context, video_data, start_sec, end_sec, status_msg))

async def process_cut_and_send(chat_id, user_id, context, video_data, start_sec, end_sec, status_msg):
    file_id = uuid.uuid4().hex[:8]
    raw_file = str(TEMP_DIR / f"{file_id}_raw.mp4")
    cut_file = str(TEMP_DIR / f"{file_id}_cut.mp4")
    lang = get_user_lang(user_id)

    try:
        loop = asyncio.get_running_loop()
        
        down_s = "⏳ Downloading source video..." if lang == "en" else "⏳ جاري تنزيل مقطع المصدر للقص..."
        await status_msg.edit_text(down_s)
        await loop.run_in_executor(None, download_video_sync, video_data['url'], raw_file)

        if not os.path.exists(raw_file):
            found = list(TEMP_DIR.glob(f"{file_id}_raw.*"))
            if found:
                raw_file = str(found[0])
            else:
                raise FileNotFoundError("Could not download video source.")

        trim_s = "✂️ Trimming clip with FFmpeg..." if lang == "en" else "✂️ جاري قص المقطع عبر FFmpeg بدقة عالية..."
        await status_msg.edit_text(trim_s)
        await loop.run_in_executor(None, cut_video_sync, raw_file, cut_file, start_sec, end_sec)

        file_size_mb = os.path.getsize(cut_file) / (1024 * 1024)
        if file_size_mb > 49.5:
            over = f"⚠️ Trimmed clip size ({file_size_mb:.1f} MB) exceeds Telegram 50MB limit." if lang == "en" else f"⚠️ حجم المقطع المقصوص ({file_size_mb:.1f} MB) يتجاوز حد تيليجرام 50MB."
            await status_msg.edit_text(over)
            return

        deduct_user_point(user_id, 1)
        await check_and_reward_referrer(user_id, context)
        pts = get_user_points(user_id)
        pts_display = f"`{pts}`" if not is_admin(user_id) else "♾️"

        duration_clip = int(end_sec - start_sec)
        caption = (
            f"🎬 **{video_data['title']}**\n"
            f"✂️ Clip: `{format_time(start_sec)}` to `{format_time(end_sec)}` ({duration_clip}s)\n"
            f"💎 Balance: {pts_display}\n\nTrimmed by @HeshamClipBot" if lang == "en"
            else f"🎬 **{video_data['title']}**\n"
            f"✂️ المقطع: من `{format_time(start_sec)}` إلى `{format_time(end_sec)}` ({duration_clip} ثانية)\n"
            f"💎 رصيد محاولاتك: {pts_display}\n\nتم القص عبر @HeshamClipBot"
        )
        with open(cut_file, 'rb') as vf:
            await context.bot.send_video(chat_id=chat_id, video=vf, caption=caption, supports_streaming=True, parse_mode=ParseMode.MARKDOWN)
        await status_msg.delete()

    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error during clip trimming: {str(e)[:150]}")
    finally:
        for f in TEMP_DIR.glob(f"{file_id}*"):
            try:
                os.remove(f)
            except Exception:
                pass

async def post_init(application):
    commands = [
        BotCommand("start", "🎬 تشغيل البوت / Start"),
        BotCommand("points", "💎 رصيدي وتجميع النقاط / Balance"),
        BotCommand("language", "🌐 تغيير اللغة / Language"),
        BotCommand("support", "💬 التواصل مع الإدارة / Support"),
        BotCommand("help", "ℹ️ المساعدة والتعليمات / Help"),
        BotCommand("admin", "👑 لوحة تحكم المدير / Admin")
    ]
    await application.bot.set_my_commands(commands)
    print("Bot commands registered successfully!", flush=True)

def main():
    print(f"Starting Hesham Clip Bot (Seamless 2-Way Chat, Direct Reply Buttons, Complete Decoupling)...", flush=True)
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("removeadmin", remove_admin_command))
    app.add_handler(CommandHandler("setdaily", set_daily_command))
    app.add_handler(CommandHandler("setpoints", set_points_command))
    app.add_handler(CommandHandler("addpoints", add_points_command))
    app.add_handler(CommandHandler("setinitial", set_initial_command))
    app.add_handler(CommandHandler("setref", set_ref_command))
    app.add_handler(CommandHandler("points", show_points_info))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("support", contact_support_prompt))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_audio_message))

    async def media_support_or_broadcast_catcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        state = context.user_data.get('state', '')

        # Check if admin is replying to support with media
        if is_admin(user.id) and update.message.reply_to_message:
            target_uid = find_target_user_from_admin_reply(update.message)
            if target_uid:
                try:
                    await send_admin_reply_to_user(target_uid, update.message, context, is_copy=True)
                    await update.message.reply_text(f"✅ تم تسليم الملف للمستخدم `{target_uid}` بنجاح!", parse_mode=ParseMode.MARKDOWN)
                    return
                except Exception as e:
                    await update.message.reply_text(f"❌ فشل تسليم الملف للمستخدم: {e}")
                    return

        # Check if user is replying with media to admin message
        if update.message.reply_to_message and is_user_replying_to_admin_message(update.message):
            await forward_support_to_admin(update.message, user, context)
            return

        if state == 'waiting_for_support_message':
            context.user_data['state'] = None
            await forward_support_to_admin(update.message, user, context)
            return
        elif state == 'waiting_for_broadcast_msg' and is_admin(user.id):
            context.user_data['state'] = None
            await execute_broadcast(update.message, is_copy=True, context=context, origin_chat_id=update.message.chat_id)
            return

    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, media_support_or_broadcast_catcher))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_or_text))

    print("Bot is up and listening for messages!", flush=True)
    app.run_polling()

if __name__ == "__main__":
    main()
