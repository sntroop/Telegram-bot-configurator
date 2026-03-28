import asyncio
import logging
import aiohttp
import aiosqlite
import re
import os
import time
import json

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from datetime import datetime, timedelta, date
from typing import Optional, List, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
REQUIRED_CHANNEL_ID = int(os.getenv("REQUIRED_CHANNEL_ID", "0"))
REQUIRED_CHANNEL_LINK = os.getenv("REQUIRED_CHANNEL_LINK", "")
DB_PATH = os.getenv("DB_PATH", "vpn_bot.db")
BANNER_FILE = os.getenv("BANNER_FILE", "wv.png")
HOW_CONNECT_FILE = os.getenv("HOW_CONNECT_FILE", "what.png")
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "5"))
VLESS_PAGE_SIZE = int(os.getenv("VLESS_PAGE_SIZE", "5"))
PING_TIMEOUT = int(os.getenv("PING_TIMEOUT", "5"))

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

TG_EMOJI = {
    "loading": "5276220667182736079",
    "cube": "5278540791336165644",
    "search": "5276395476646653290",
    "key": "5278613311858959074",
    "check": "5278411813468269386",
    "heart": "5278611606756942667",
    "folder": "5278227821364275264",
    "note": "5276111746812112286",
    "cross": "5278578973595427038",
    "info": "5278753302023004775",
    "bell": "5278528159837348960",
    "clean": "5276442772826515132",
    "user": "5275979556308674886",
    "link": "5278305362703835500",
    "star": "5206476089127372379",
    "gamepad": "5278304890257436355",
    "at": "5278589204207528856",
    "clock": "5276412364458059956",
    "warning": "5276240711795107620",
    "back": "5278413853577734640",
    "wrench": "5276442772826515132",
    "wifi": "5278613311858959074",
    "bulb": "5278753302023004775",
    "plus": "5278304890257436355",
    "globe": "5278613311858959074",
    "globe2": "5278227821364275264",
    "pin": "5278305362703835500",
    "shield": "5276240711795107620",
    "mtp": "5276262671962892944",
    "speed": "5276395476646653290",
}

def raw_btn(text: str, cb: str = None, url: str = None, emoji_id: str = None) -> dict:
    b = {"text": text}
    if cb:
        b["callback_data"] = cb
    if url:
        b["url"] = url
    if emoji_id:
        b["icon_custom_emoji_id"] = emoji_id
    return b

def raw_kb(*rows: list) -> dict:
    return {"inline_keyboard": list(rows)}

async def tg_send(chat_id: int, text: str, markup: dict = None, reply_to: int = None) -> Optional[dict]:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if markup:
        payload["reply_markup"] = markup
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{TG_API}/sendMessage", json=payload) as r:
                data = await r.json()
                return data.get("result")
    except Exception as ex:
        logger.error(f"tg_send error: {ex}")
    return None

async def tg_edit(chat_id: int, message_id: int, text: str, markup: dict = None) -> bool:
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if markup:
        payload["reply_markup"] = markup
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{TG_API}/editMessageText", json=payload) as r:
                data = await r.json()
                return data.get("ok", False)
    except Exception as ex:
        logger.error(f"tg_edit error: {ex}")
    return False

async def tg_answer(call_id: str, text: str = "", alert: bool = False):
    payload = {"callback_query_id": call_id, "show_alert": alert}
    if text:
        payload["text"] = text
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{TG_API}/answerCallbackQuery", json=payload)
    except Exception as ex:
        logger.error(f"tg_answer error: {ex}")

async def check_channel_member(user_id: int) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{TG_API}/getChatMember",
                params={"chat_id": REQUIRED_CHANNEL_ID, "user_id": user_id}
            ) as r:
                data = await r.json()
                if data.get("ok"):
                    return data["result"].get("status", "") in ("member", "administrator", "creator")
    except Exception as ex:
        logger.error(f"check_channel_member error: {ex}")
    return False

_banner_file_id: Optional[str] = None
_how_connect_file_id: Optional[str] = None

async def tg_send_photo(chat_id: int, caption: str, markup: dict = None) -> Optional[dict]:
    global _banner_file_id
    try:
        async with aiohttp.ClientSession() as s:
            if _banner_file_id:
                payload = {
                    "chat_id": chat_id,
                    "photo": _banner_file_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                if markup:
                    payload["reply_markup"] = markup
                async with s.post(f"{TG_API}/sendPhoto", json=payload) as r:
                    data = await r.json()
                    if data.get("ok"):
                        return data.get("result")
                    _banner_file_id = None

            if not os.path.exists(BANNER_FILE):
                return None
            with open(BANNER_FILE, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("chat_id", str(chat_id))
                form.add_field("caption", caption)
                form.add_field("parse_mode", "HTML")
                if markup:
                    form.add_field("reply_markup", json.dumps(markup))
                form.add_field("photo", f, filename=BANNER_FILE, content_type="image/png")
                async with s.post(f"{TG_API}/sendPhoto", data=form) as r:
                    data = await r.json()
                    if data.get("ok"):
                        try:
                            _banner_file_id = data["result"]["photo"][-1]["file_id"]
                        except Exception:
                            pass
                    return data.get("result")
    except Exception as ex:
        logger.error(f"tg_send_photo error: {ex}")
    return None

async def show_menu_with_banner(chat_id: int, msg_id: int, caption: str, markup: dict) -> None:
    global _banner_file_id
    try:
        async with aiohttp.ClientSession() as s:
            if _banner_file_id:
                payload = {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "media": {
                        "type": "photo",
                        "media": _banner_file_id,
                        "caption": caption,
                        "parse_mode": "HTML"
                    },
                    "reply_markup": markup
                }
                async with s.post(f"{TG_API}/editMessageMedia", json=payload) as r:
                    data = await r.json()
                    if data.get("ok"):
                        return
                    _banner_file_id = None

            if not os.path.exists(BANNER_FILE):
                await tg_edit(chat_id, msg_id, caption, markup)
                return
            with open(BANNER_FILE, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("chat_id", str(chat_id))
                form.add_field("message_id", str(msg_id))
                form.add_field(
                    "media",
                    json.dumps({
                        "type": "photo",
                        "media": "attach://banner",
                        "caption": caption,
                        "parse_mode": "HTML"
                    })
                )
                if markup:
                    form.add_field("reply_markup", json.dumps(markup))
                form.add_field("banner", f, filename=BANNER_FILE, content_type="image/png")
                async with s.post(f"{TG_API}/editMessageMedia", data=form) as r:
                    data = await r.json()
                    if data.get("ok"):
                        try:
                            _banner_file_id = data["result"]["photo"][-1]["file_id"]
                        except Exception:
                            pass
    except Exception as ex:
        logger.error(f"show_menu_with_banner error: {ex}")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY,
                tg_id      INTEGER UNIQUE NOT NULL,
                username   TEXT,
                full_name  TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS vless_configs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT,
                vless_link  TEXT    NOT NULL,
                proto       TEXT    DEFAULT 'vless',
                is_active   INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS daily_issues (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                config_id  INTEGER,
                issued_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        await db.commit()
        try:
            await db.execute("ALTER TABLE vless_configs ADD COLUMN proto TEXT DEFAULT 'vless'")
            await db.commit()
        except Exception:
            pass

async def get_user(tg_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def create_user(tg_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, username, full_name) VALUES (?,?,?)",
            (tg_id, username, full_name),
        )
        await db.commit()

async def get_all_users() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY created_at DESC")
        return [dict(r) for r in await cur.fetchall()]

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        await db.commit()

async def get_daily_count(user_id: int) -> int:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM daily_issues WHERE user_id=? AND date(issued_at)=?",
            (user_id, today)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

async def record_daily_issue(user_id: int, config_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO daily_issues (user_id, config_id) VALUES (?,?)",
            (user_id, config_id)
        )
        await db.commit()

async def get_daily_remaining(user_id: int) -> int:
    used = await get_daily_count(user_id)
    return max(0, DAILY_LIMIT - used)

async def get_all_vless(active_only=True, proto: str = None) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if proto:
            q = ("SELECT * FROM vless_configs WHERE is_active=1 AND proto=? ORDER BY id"
                 if active_only else
                 "SELECT * FROM vless_configs WHERE proto=? ORDER BY id")
            cur = await db.execute(q, (proto,))
        else:
            q = ("SELECT * FROM vless_configs WHERE is_active=1 ORDER BY id"
                 if active_only else "SELECT * FROM vless_configs ORDER BY id")
            cur = await db.execute(q)
        return [dict(r) for r in await cur.fetchall()]

async def get_vless(config_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM vless_configs WHERE id=?", (config_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def get_random_vless_batch_for_user(user_id: int, count: int, proto: str = None) -> List[Dict]:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if proto:
            cur = await db.execute(
                """SELECT * FROM vless_configs WHERE is_active=1 AND proto=?
                   AND id NOT IN (
                       SELECT config_id FROM daily_issues
                       WHERE user_id=? AND date(issued_at)=? AND config_id IS NOT NULL
                   ) ORDER BY RANDOM() LIMIT ?""",
                (proto, user_id, today, count)
            )
        else:
            cur = await db.execute(
                """SELECT * FROM vless_configs WHERE is_active=1
                   AND id NOT IN (
                       SELECT config_id FROM daily_issues
                       WHERE user_id=? AND date(issued_at)=? AND config_id IS NOT NULL
                   ) ORDER BY RANDOM() LIMIT ?""",
                (user_id, today, count)
            )
        return [dict(r) for r in await cur.fetchall()]

async def add_vless_batch(configs: List[Dict]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO vless_configs (name, description, vless_link, proto) VALUES (?,?,?,?)",
            [(c["name"], c.get("description", ""), c["vless_link"], c.get("proto", "vless")) for c in configs]
        )
        await db.commit()

async def deactivate_vless(config_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE vless_configs SET is_active=0 WHERE id=?", (config_id,))
        await db.commit()

async def clear_configs_by_proto(proto: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM vless_configs WHERE proto=?", (proto,))
        await db.commit()

async def clear_all_configs():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM vless_configs")
        await db.commit()

async def get_configs_count_by_proto() -> Dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT proto, COUNT(*) FROM vless_configs WHERE is_active=1 GROUP BY proto")
        return {r[0]: r[1] for r in await cur.fetchall()}

def detect_proto(link: str) -> str:
    l = link.strip()
    if l.startswith("vless://"):
        return "vless"
    if l.startswith("ss://"):
        return "ss"
    if l.startswith("socks5://") or l.startswith("socks://"):
        return "socks5"
    if l.startswith("tg://proxy") or l.startswith("https://t.me/proxy"):
        return "mtproto"
    return "vless"

PROTO_LABELS = {"vless": "VLESS", "ss": "ShadowSocks", "socks5": "SOCKS5", "mtproto": "MTProto"}
PROTO_ICONS = {"vless": "globe", "ss": "cube", "socks5": "gamepad", "mtproto": "mtp"}

def extract_host_from_link(link: str) -> Optional[str]:
    link = link.strip()
    proto = detect_proto(link)
    try:
        if proto == "mtproto":
            m = re.search(r'[?&]server=([^&]+)', link)
            return m.group(1) if m else None
        if proto == "ss":
            m = re.search(r'@([^@#?/]+):(\d+)', link)
            return m.group(1) if m else None
        after = link.split('://', 1)[1].split('#')[0]
        after_at = after.rsplit('@', 1)[1] if '@' in after else after
        host_port = after_at.split('/')[0].split('?')[0]
        if host_port.startswith('['):
            return host_port.split(']')[0][1:]
        return host_port.rsplit(':', 1)[0]
    except Exception:
        return None

def extract_port_from_link(link: str) -> Optional[int]:
    link = link.strip()
    proto = detect_proto(link)
    try:
        if proto == "mtproto":
            m = re.search(r'[?&]port=(\d+)', link)
            return int(m.group(1)) if m else None
        if proto == "ss":
            m = re.search(r'@[^@#?/]+:(\d+)', link)
            return int(m.group(1)) if m else None
        after = link.split('://', 1)[1].split('#')[0]
        after_at = after.rsplit('@', 1)[1] if '@' in after else after
        host_port = after_at.split('/')[0].split('?')[0]
        if host_port.startswith('['):
            port_part = host_port.split(']')[1]
            return int(port_part.lstrip(':').split('/')[0]) if port_part else None
        parts = host_port.rsplit(':', 1)
        return int(parts[1]) if len(parts) == 2 else None
    except Exception:
        return None

def parse_links_from_text(text: str) -> List[str]:
    found = []
    pat = re.compile(r'(?:vless|ss|socks5?|tg)://[^\s]+|https://t\.me/proxy\?[^\s]+')
    for m in pat.finditer(text):
        link = m.group(0).rstrip('.,;)\'"')
        if detect_proto(link) != "ss" and '#' in link:
            link = link.split('#')[0].strip()
        if link:
            found.append(link)
    return found

async def get_country_code(host: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://ip-api.com/json/{host}?fields=countryCode",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("countryCode", "??")
    except Exception:
        pass
    return "??"

def get_country_flag(cc: str) -> str:
    if not cc or len(cc) != 2 or cc == "??":
        return "🌐"
    try:
        return chr(ord(cc[0].upper()) + 0x1F1A5) + chr(ord(cc[1].upper()) + 0x1F1A5)
    except Exception:
        return "🌐"

async def _resolve_one(idx: int, link: str) -> Dict:
    proto = detect_proto(link)
    host = extract_host_from_link(link)
    cc = "??"
    if host:
        ip_pat = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        if ip_pat.match(host):
            try:
                cc = await get_country_code(host)
            except Exception:
                pass
    label = PROTO_LABELS.get(proto, proto.upper())
    return {
        "name": f"{get_country_flag(cc)} {label} | #{idx + 1}",
        "description": "",
        "vless_link": link,
        "proto": proto,
    }

async def process_any_links(links: List[str]) -> List[Dict]:
    configs = []
    for i in range(0, len(links), 10):
        batch = links[i:i + 10]
        results = await asyncio.gather(
            *[_resolve_one(i + j, lnk) for j, lnk in enumerate(batch)],
            return_exceptions=True
        )
        for r in results:
            if isinstance(r, dict):
                configs.append(r)
        if i + 10 < len(links):
            await asyncio.sleep(1.2)
    return configs

async def ping_host(host: str, port: int) -> Optional[float]:
    try:
        start = time.monotonic()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=PING_TIMEOUT
        )
        ms = (time.monotonic() - start) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return round(ms, 1)
    except Exception:
        return None

async def ping_config(vless_link: str) -> str:
    host = extract_host_from_link(vless_link)
    port = extract_port_from_link(vless_link)
    if not host or not port:
        return "❓ Не удалось определить хост/порт"
    ms = await ping_host(host, port)
    if ms is None:
        return f"❌ Недоступен ({host}:{port})"
    if ms < 100:
        emoji = "🟢"
    elif ms < 300:
        emoji = "🟡"
    else:
        emoji = "🔴"
    return f"{emoji} {ms} ms  ({host}:{port})"

def main_menu_kb() -> dict:
    return raw_kb(
        [raw_btn("Получить конфиги", "get_configs", emoji_id=TG_EMOJI["key"])],
        [raw_btn("Мои конфиги", "my_configs", emoji_id=TG_EMOJI["folder"])],
        [raw_btn("Проверить пинг", "ping_menu", emoji_id=TG_EMOJI["speed"])],
        [raw_btn("Как подключиться", "how_connect", emoji_id=TG_EMOJI["wifi"])],
        [raw_btn("О боте", "about", emoji_id=TG_EMOJI["bulb"])],
    )

def not_subscribed_kb() -> dict:
    return raw_kb(
        [raw_btn("Подписаться на канал", url=REQUIRED_CHANNEL_LINK, emoji_id=TG_EMOJI["bell"])],
        [raw_btn("Я подписался", "check_sub", emoji_id=TG_EMOJI["check"])],
    )

def back_main_kb() -> dict:
    return raw_kb([raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])])

def proto_select_kb(action_prefix: str) -> dict:
    return raw_kb(
        [raw_btn("VLESS", f"{action_prefix}:vless:0", emoji_id=TG_EMOJI["globe"])],
        [raw_btn("ShadowSocks", f"{action_prefix}:ss:0", emoji_id=TG_EMOJI["cube"])],
        [raw_btn("SOCKS5", f"{action_prefix}:socks5:0", emoji_id=TG_EMOJI["gamepad"])],
        [raw_btn("MTProto", f"{action_prefix}:mtproto:0", emoji_id=TG_EMOJI["mtp"])],
        [raw_btn("Все", f"{action_prefix}:any:0", emoji_id=TG_EMOJI["star"])],
        [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
    )

def admin_menu_kb() -> dict:
    return raw_kb(
        [raw_btn("Добавить конфиг", "admin_add_proto", emoji_id=TG_EMOJI["plus"])],
        [raw_btn("Загрузить файл", "admin_upload", emoji_id=TG_EMOJI["wrench"])],
        [raw_btn("Spam-режим", "admin_vless_spam", emoji_id=TG_EMOJI["loading"])],
        [raw_btn("Список конфигов", "admin_list", emoji_id=TG_EMOJI["folder"])],
        [raw_btn("Очистить конфиги", "admin_clear_menu", emoji_id=TG_EMOJI["clean"])],
        [raw_btn("Пользователи", "admin_users", emoji_id=TG_EMOJI["user"])],
        [raw_btn("Рассылка", "admin_broadcast", emoji_id=TG_EMOJI["bell"])],
        [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
    )

def admin_clear_kb() -> dict:
    return raw_kb(
        [raw_btn("VLESS", "admin_clear_proto:vless", emoji_id=TG_EMOJI["globe"])],
        [raw_btn("ShadowSocks", "admin_clear_proto:ss", emoji_id=TG_EMOJI["cube"])],
        [raw_btn("SOCKS5", "admin_clear_proto:socks5", emoji_id=TG_EMOJI["gamepad"])],
        [raw_btn("MTProto", "admin_clear_proto:mtproto", emoji_id=TG_EMOJI["mtp"])],
        [raw_btn("ВСЕ", "admin_clear_proto:all", emoji_id=TG_EMOJI["warning"])],
        [raw_btn("Назад", "admin_menu", emoji_id=TG_EMOJI["back"])],
    )

class AddProtoState(StatesGroup):
    link = State()

class UploadState(StatesGroup):
    wait_for_file = State()

class BroadcastState(StatesGroup):
    message = State()

class VlessSpamState(StatesGroup):
    collecting = State()

class IsAdmin(Filter):
    async def __call__(self, update) -> bool:
        user = getattr(update, "from_user", None)
        return bool(user and user.id == ADMIN_ID)

async def require_subscription(chat_id: int, msg_id: int, user_id: int) -> bool:
    if await check_channel_member(user_id):
        return True
    await show_menu_with_banner(
        chat_id, msg_id,
        "<tg-emoji emoji-id=\"5276240711795107620\">⚠️</tg-emoji> <b>Нужна подписка на канал</b>\n\n"
        "Для использования бота необходимо подписаться на наш канал.\n"
        "После подписки нажмите <b>«Я подписался»</b>.",
        not_subscribed_kb(),
    )
    return False

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    tg_id = message.from_user.id
    await create_user(tg_id, message.from_user.username or "", message.from_user.full_name or "")

    if not await check_channel_member(tg_id):
        await tg_send(
            tg_id,
            "<tg-emoji emoji-id=\"5276240711795107620\">🛡</tg-emoji> <b>Добро пожаловать в WasVless!</b>\n\n"
            "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> Бесплатные VPN-конфиги: VLESS, ShadowSocks, SOCKS5, MTProto.\n\n"
            "Для использования бота подпишитесь на наш канал:",
            not_subscribed_kb(),
        )
        return

    result = await tg_send_photo(
        tg_id,
        "<tg-emoji emoji-id=\"5276240711795107620\">🛡</tg-emoji> <b>Добро пожаловать в WasVless!</b>\n\n"
        "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> Бесплатные VPN-конфиги каждый день — до <b>5 штук</b> в сутки!\n"
        "Нажмите <b>«Получить конфиги»</b> чтобы начать.",
        main_menu_kb(),
    )
    if not result:
        await tg_send(
            tg_id,
            "<tg-emoji emoji-id=\"5276240711795107620\">🛡</tg-emoji> <b>Добро пожаловать в WasVless!</b>\n\n"
            "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> Бесплатные VPN-конфиги каждый день — до <b>5 штук</b> в сутки!\n"
            "Нажмите <b>«Получить конфиги»</b> чтобы начать.",
            main_menu_kb(),
        )

@router.message(Command("admin"), IsAdmin())
async def cmd_admin(message: Message):
    await tg_send(message.chat.id, "<tg-emoji emoji-id=\"5206476089127372379\">⭐</tg-emoji> <b>Панель администратора</b>", admin_menu_kb())

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Главное меню</b>\n\nЖмите:",
        main_menu_kb()
    )
    await tg_answer(call.id)

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    if await check_channel_member(call.from_user.id):
        await show_menu_with_banner(
            call.message.chat.id, call.message.message_id,
            "<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> <b>Подписка подтверждена!</b>\n\n"
            "Теперь вы можете пользоваться ботом бесплатно.\n"
            f"Доступно конфигов сегодня: <b>{await get_daily_remaining(call.from_user.id)}</b>/{DAILY_LIMIT}",
            main_menu_kb(),
        )
    else:
        await tg_answer(call.id, "Вы ещё не подписаны на канал!", alert=True)
    await tg_answer(call.id)

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await tg_answer(call.id)

_ping_timestamps: Dict[int, List[float]] = {}
PING_RATE_WINDOW = 60
PING_RATE_LIMIT = 10

def _check_ping_rate(user_id: int) -> bool:
    now = time.monotonic()
    ts = _ping_timestamps.get(user_id, [])
    ts = [t for t in ts if now - t < PING_RATE_WINDOW]
    if len(ts) >= PING_RATE_LIMIT:
        _ping_timestamps[user_id] = ts
        return False
    ts.append(now)
    _ping_timestamps[user_id] = ts
    return True

def _ping_rate_wait(user_id: int) -> int:
    now = time.monotonic()
    ts = _ping_timestamps.get(user_id, [])
    ts = [t for t in ts if now - t < PING_RATE_WINDOW]
    if not ts:
        return 0
    return max(0, int(PING_RATE_WINDOW - (now - min(ts))) + 1)

@router.callback_query(F.data == "get_configs")
async def cb_get_configs(call: CallbackQuery):
    if not await require_subscription(call.message.chat.id, call.message.message_id, call.from_user.id):
        await tg_answer(call.id)
        return

    remaining = await get_daily_remaining(call.from_user.id)
    if remaining == 0:
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        delta = midnight - now
        h, m = divmod(int(delta.total_seconds()) // 60, 60)
        await show_menu_with_banner(
            call.message.chat.id, call.message.message_id,
            "<tg-emoji emoji-id=\"5276412364458059956\">⏰</tg-emoji> <b>Дневной лимит исчерпан</b>\n\n"
            f"Вы уже получили <b>{DAILY_LIMIT}</b> конфигов сегодня.\n"
            f"Новые будут доступны через <b>{h}ч {m}мин</b>.",
            back_main_kb(),
        )
        await tg_answer(call.id)
        return

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Каталог конфигов</b>\n\n"
        f"<tg-emoji emoji-id=\"5276111746812112286\">📊</tg-emoji> Осталось сегодня: <b>{remaining}/{DAILY_LIMIT}</b>\n\n"
        "Выберите протокол:",
        proto_select_kb("catalog"),
    )
    await tg_answer(call.id)

@router.callback_query(F.data.startswith("catalog:"))
async def cb_catalog(call: CallbackQuery):
    if not await require_subscription(call.message.chat.id, call.message.message_id, call.from_user.id):
        await tg_answer(call.id)
        return

    parts = call.data.split(":")
    proto = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    remaining = await get_daily_remaining(call.from_user.id)
    if remaining == 0:
        await tg_answer(call.id, "Дневной лимит исчерпан. Возвращайтесь завтра!", alert=True)
        return

    proto_arg = None if proto == "any" else proto
    configs = await get_all_vless(proto=proto_arg)

    if not configs:
        label = PROTO_LABELS.get(proto, proto.upper()) if proto != "any" else "любого протокола"
        await tg_answer(call.id, f"Конфиги {label} временно недоступны", alert=True)
        return

    total_pages = max(1, (len(configs) + VLESS_PAGE_SIZE - 1) // VLESS_PAGE_SIZE)
    page_cfgs = configs[page * VLESS_PAGE_SIZE: (page + 1) * VLESS_PAGE_SIZE]
    icon = PROTO_ICONS.get(proto, "globe")

    rows = []
    for c in page_cfgs:
        rows.append([raw_btn(c["name"], f"config_detail:{c['id']}:{proto}:{page}", emoji_id=TG_EMOJI[icon])])

    nav = []
    if page > 0:
        nav.append(raw_btn("◀", f"catalog:{proto}:{page-1}"))
    nav.append(raw_btn(f"{page+1}/{total_pages}", "noop"))
    if (page + 1) * VLESS_PAGE_SIZE < len(configs):
        nav.append(raw_btn("▶", f"catalog:{proto}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([raw_btn("Назад", "get_configs", emoji_id=TG_EMOJI["back"])])

    label = PROTO_LABELS.get(proto, proto.upper()) if proto != "any" else "Все протоколы"
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        f"<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>{label}</b>\n\n"
        f"Доступно: <b>{len(configs)}</b>  |  Осталось сегодня: <b>{remaining}/{DAILY_LIMIT}</b>\n\n"
        "Выберите конфиг:",
        raw_kb(*rows),
    )
    await tg_answer(call.id)

@router.callback_query(F.data.startswith("config_detail:"))
async def cb_config_detail(call: CallbackQuery):
    if not await require_subscription(call.message.chat.id, call.message.message_id, call.from_user.id):
        await tg_answer(call.id)
        return

    parts = call.data.split(":")
    config_id = int(parts[1])
    proto = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0

    config = await get_vless(config_id)
    if not config:
        await tg_answer(call.id, "Конфиг не найден", alert=True)
        return

    remaining = await get_daily_remaining(call.from_user.id)
    label = PROTO_LABELS.get(config.get("proto", "vless"), "VPN")

    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM daily_issues WHERE user_id=? AND config_id=? AND date(issued_at)=?",
            (call.from_user.id, config_id, today)
        )
        already = await cur.fetchone() is not None

    if already:
        get_btn = raw_btn("Уже получен сегодня", "noop", emoji_id=TG_EMOJI["check"])
    elif remaining == 0:
        get_btn = raw_btn("Лимит исчерпан на сегодня", "noop", emoji_id=TG_EMOJI["clock"])
    else:
        get_btn = raw_btn(f"Получить  (осталось {remaining})", f"take_config:{config_id}:{proto}:{page}",
                          emoji_id=TG_EMOJI["key"])

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        f"<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>{config['name']}</b>  [{label}]\n\n"
        f"<tg-emoji emoji-id=\"5278613311858959074\">📶</tg-emoji> Нажмите «Получить» чтобы забрать конфиг.",
        raw_kb(
            [get_btn],
            [raw_btn("Пинг", f"ping_config:{config_id}", emoji_id=TG_EMOJI["speed"])],
            [raw_btn("Назад", f"catalog:{proto}:{page}", emoji_id=TG_EMOJI["back"])],
        ),
    )
    await tg_answer(call.id)

@router.callback_query(F.data.startswith("take_config:"))
async def cb_take_config(call: CallbackQuery):
    if not await require_subscription(call.message.chat.id, call.message.message_id, call.from_user.id):
        await tg_answer(call.id)
        return

    parts = call.data.split(":")
    config_id = int(parts[1])
    proto = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    user_id = call.from_user.id

    remaining = await get_daily_remaining(user_id)
    if remaining == 0:
        await tg_answer(call.id, "Дневной лимит исчерпан. Возвращайтесь завтра!", alert=True)
        return

    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM daily_issues WHERE user_id=? AND config_id=? AND date(issued_at)=?",
            (user_id, config_id, today)
        )
        already = await cur.fetchone() is not None

    if already:
        await tg_answer(call.id, "Вы уже получили этот конфиг сегодня!", alert=True)
        return

    config = await get_vless(config_id)
    if not config:
        await tg_answer(call.id, "Конфиг не найден", alert=True)
        return

    await record_daily_issue(user_id, config_id)
    new_remaining = await get_daily_remaining(user_id)
    label = PROTO_LABELS.get(config.get("proto", "vless"), "VPN")

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        f"<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> <b>Конфиг получен!</b>\n\n"
        f"<b>{config['name']}</b>  [{label}]\n\n"
        f"<code>{config['vless_link']}</code>\n\n"
        f"<tg-emoji emoji-id=\"5276111746812112286\">📊</tg-emoji> Осталось сегодня: <b>{new_remaining}/{DAILY_LIMIT}</b>",
        raw_kb(
            [raw_btn("Пинг этого конфига", f"ping_config:{config_id}", emoji_id=TG_EMOJI["speed"])],
            [raw_btn("Как подключиться", "how_connect", emoji_id=TG_EMOJI["wifi"])],
            [raw_btn("Назад в каталог", f"catalog:{proto}:{page}", emoji_id=TG_EMOJI["back"])],
            [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
        ),
    )
    await tg_answer(call.id)

@router.callback_query(F.data == "my_configs")
async def cb_my_configs(call: CallbackQuery):
    if not await require_subscription(call.message.chat.id, call.message.message_id, call.from_user.id):
        await tg_answer(call.id)
        return

    user_id = call.from_user.id
    today = date.today().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT di.config_id, vc.name, vc.vless_link, vc.proto
            FROM daily_issues di
            LEFT JOIN vless_configs vc ON di.config_id = vc.id
            WHERE di.user_id=? AND date(di.issued_at)=?
            ORDER BY di.issued_at DESC
        """, (user_id, today))
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        await show_menu_with_banner(
            call.message.chat.id, call.message.message_id,
            "<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Сегодня вы ещё не получали конфиги.\n\n"
            "Зайдите в каталог и выберите нужный!",
            raw_kb(
                [raw_btn("Каталог конфигов", "get_configs", emoji_id=TG_EMOJI["key"])],
                [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
            ),
        )
        await tg_answer(call.id)
        return

    lines = [f"<tg-emoji emoji-id=\"5278227821364275264\">📁</tg-emoji> <b>Ваши конфиги за сегодня ({len(rows)} шт.)</b>\n"]
    for i, r in enumerate(rows, 1):
        label = PROTO_LABELS.get(r.get("proto") or "", "VPN")
        lines.append(f"<b>#{i} {r['name'] or 'Конфиг'}</b>  [{label}]")
        if r.get("vless_link"):
            lines.append(f"<code>{r['vless_link']}</code>")
        lines.append("")

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "\n".join(lines),
        raw_kb(
            [raw_btn("Пинг всех конфигов", "ping_all_today", emoji_id=TG_EMOJI["speed"])],
            [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
        ),
    )
    await tg_answer(call.id)

@router.callback_query(F.data.startswith("ping_config:"))
async def cb_ping_config(call: CallbackQuery):
    config_id = int(call.data.split(":")[1])

    if not _check_ping_rate(call.from_user.id):
        wait = _ping_rate_wait(call.from_user.id)
        await tg_answer(call.id, f"Слишком много пингов. Подождите {wait} сек.", alert=True)
        return

    await tg_answer(call.id, "Проверяю...", alert=False)

    config = await get_vless(config_id)
    if not config:
        await tg_answer(call.id, "Конфиг не найден", alert=True)
        return

    result = await ping_config(config["vless_link"])
    label = PROTO_LABELS.get(config.get("proto", ""), "VPN")

    await tg_edit(
        call.message.chat.id, call.message.message_id,
        f"<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Пинг</b>\n\n"
        f"<b>{config['name']}</b>  [{label}]\n\n"
        f"{result}",
        raw_kb(
            [raw_btn("Повторить", f"ping_config:{config_id}", emoji_id=TG_EMOJI["speed"])],
            [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
        ),
    )

@router.callback_query(F.data == "ping_menu")
async def cb_ping_menu(call: CallbackQuery):
    if not await require_subscription(call.message.chat.id, call.message.message_id, call.from_user.id):
        await tg_answer(call.id)
        return

    today = date.today().isoformat()
    user_id = call.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT DISTINCT di.config_id, vc.name, vc.vless_link, vc.proto
            FROM daily_issues di
            LEFT JOIN vless_configs vc ON di.config_id = vc.id
            WHERE di.user_id=? AND date(di.issued_at)=? AND vc.vless_link IS NOT NULL
            ORDER BY di.issued_at DESC
        """, (user_id, today))
        configs = [dict(r) for r in await cur.fetchall()]

    if not configs:
        await show_menu_with_banner(
            call.message.chat.id, call.message.message_id,
            "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Проверка пинга</b>\n\n"
            "У вас нет полученных конфигов сегодня.",
            raw_kb(
                [raw_btn("Каталог конфигов", "get_configs", emoji_id=TG_EMOJI["key"])],
                [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
            ),
        )
        await tg_answer(call.id)
        return

    rows = []
    for c in configs:
        label = PROTO_LABELS.get(c.get("proto", ""), "VPN")
        rows.append([raw_btn(f"{c['name'][:30]}  [{label}]",
                             f"ping_config:{c['config_id']}", emoji_id=TG_EMOJI["speed"])])
    rows.append([raw_btn("Пинговать все", "ping_all_today", emoji_id=TG_EMOJI["speed"])])
    rows.append([raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])])

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Проверка пинга</b>\n\n"
        "Выберите конфиг:",
        raw_kb(*rows),
    )
    await tg_answer(call.id)

@router.callback_query(F.data == "ping_all_today")
async def cb_ping_all(call: CallbackQuery):
    if not _check_ping_rate(call.from_user.id):
        wait = _ping_rate_wait(call.from_user.id)
        await tg_answer(call.id, f"Слишком много пингов. Подождите {wait} сек.", alert=True)
        return

    await tg_answer(call.id, "Пингую все...", alert=False)

    today = date.today().isoformat()
    user_id = call.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT DISTINCT di.config_id, vc.name, vc.vless_link, vc.proto
            FROM daily_issues di
            LEFT JOIN vless_configs vc ON di.config_id = vc.id
            WHERE di.user_id=? AND date(di.issued_at)=? AND vc.vless_link IS NOT NULL
            ORDER BY di.issued_at DESC
        """, (user_id, today))
        configs = [dict(r) for r in await cur.fetchall()]

    if not configs:
        await tg_answer(call.id, "Конфигов нет", alert=True)
        return

    results = await asyncio.gather(*[ping_config(c["vless_link"]) for c in configs])

    lines = ["<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Пинг всех конфигов</b>\n"]
    for c, res in zip(configs, results):
        label = PROTO_LABELS.get(c.get("proto", ""), "VPN")
        lines.append(f"<b>{c['name'] or 'Конфиг'}</b>  [{label}]")
        lines.append(f"  {res}\n")

    await tg_edit(
        call.message.chat.id, call.message.message_id,
        "\n".join(lines),
        raw_kb(
            [raw_btn("Обновить", "ping_all_today", emoji_id=TG_EMOJI["speed"])],
            [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
        ),
    )

@router.callback_query(F.data == "how_connect")
async def cb_how_connect(call: CallbackQuery):
    global _how_connect_file_id
    kb = raw_kb([raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])])
    try:
        async with aiohttp.ClientSession() as s:
            if _how_connect_file_id:
                payload = {
                    "chat_id": call.message.chat.id,
                    "photo": _how_connect_file_id,
                    "caption": "<tg-emoji emoji-id=\"5275979556308674886\">📱</tg-emoji> <b>Как подключиться</b>",
                    "parse_mode": "HTML",
                    "reply_markup": kb
                }
                async with s.post(f"{TG_API}/sendPhoto", json=payload) as r:
                    data = await r.json()
                    if data.get("ok"):
                        await tg_answer(call.id)
                        return
                    _how_connect_file_id = None

            if os.path.exists(HOW_CONNECT_FILE):
                with open(HOW_CONNECT_FILE, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", str(call.message.chat.id))
                    form.add_field("caption", "<tg-emoji emoji-id=\"5275979556308674886\">📱</tg-emoji> <b>Как подключиться</b>")
                    form.add_field("parse_mode", "HTML")
                    form.add_field("reply_markup", json.dumps(kb))
                    form.add_field("photo", f, filename=HOW_CONNECT_FILE, content_type="image/png")
                    async with s.post(f"{TG_API}/sendPhoto", data=form) as r:
                        data = await r.json()
                        if data.get("ok"):
                            try:
                                _how_connect_file_id = data["result"]["photo"][-1]["file_id"]
                            except Exception:
                                pass
            else:
                await tg_send(
                    call.message.chat.id,
                    "<tg-emoji emoji-id=\"5275979556308674886\">📱</tg-emoji> <b>Как подключиться</b>\n\n"
                    "1. Скачайте v2rayNG (Android) или Streisand (iOS)\n"
                    "2. Нажмите «+» — вставьте ссылку конфига\n"
                    "3. Подключитесь одной кнопкой\n\n"
                    "По вопросам: @sntroop",
                    kb,
                )
    except Exception as ex:
        logger.error(f"how_connect error: {ex}")
    await tg_answer(call.id)

@router.callback_query(F.data == "about")
async def cb_about(call: CallbackQuery):
    total_configs = len(await get_all_vless())
    counts = await get_configs_count_by_proto()
    proto_lines = "\n".join(
        f"  {PROTO_LABELS.get(p, p.upper())}: {n}"
        for p, n in counts.items()
    ) or "  Пока нет конфигов"

    text = (
        "<b>WasVless — бесплатный VPN-бот</b>\n\n"
        f"<tg-emoji emoji-id=\"5278227821364275264\">📦</tg-emoji> Всего конфигов: <b>{total_configs}</b>\n"
        f"<pre>{proto_lines}</pre>\n"
        f"<tg-emoji emoji-id=\"5278528159837348960\">🎁</tg-emoji> Лимит: до <b>{DAILY_LIMIT}</b> конфигов в день\n"
        f"<tg-emoji emoji-id=\"5276412364458059956\">🔄</tg-emoji> Обновляется каждые сутки\n\n"
        "<b>Контакты:</b>\n"
        "<pre>Поддержка: @sntroop\nКанал: @TLOPSpace</pre>"
    )
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id, text,
        raw_kb(
            [raw_btn("Политика конф.", url="https://telegra.ph/Politika-konfidencialnosti-08-15-17",
                     emoji_id=TG_EMOJI["shield"])],
            [raw_btn("Главное меню", "main_menu", emoji_id=TG_EMOJI["back"])],
        ),
    )
    await tg_answer(call.id)

@router.callback_query(IsAdmin(), F.data == "admin_menu")
async def cb_admin_menu(call: CallbackQuery):
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5206476089127372379\">⭐</tg-emoji> <b>Панель администратора</b>", admin_menu_kb())
    await tg_answer(call.id)

@router.callback_query(IsAdmin(), F.data == "admin_add_proto")
async def cb_admin_add_proto(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddProtoState.link)
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5278304890257436355\">➕</tg-emoji> <b>Добавить конфиг</b>\n\nОтправьте ссылку (vless://, ss://, socks5://, tg://proxy и т.д.).\n"
        "Можно несколько ссылок — каждую на новой строке.",
        raw_kb([raw_btn("Отмена", "admin_menu", emoji_id=TG_EMOJI["back"])]),
    )
    await tg_answer(call.id)

@router.message(IsAdmin(), AddProtoState.link)
async def admin_add_proto_link(message: Message, state: FSMContext):
    links = parse_links_from_text(message.text or "")
    if not links:
        await tg_send(message.chat.id, "<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Ссылки не найдены. Попробуйте ещё раз.", admin_menu_kb())
        await state.clear()
        return

    await tg_send(message.chat.id, f"<tg-emoji emoji-id=\"5276220667182736079\">⏳</tg-emoji> Обрабатываю <b>{len(links)}</b> ссылок...")
    configs = await process_any_links(links)
    await add_vless_batch(configs)
    await state.clear()
    await tg_send(
        message.chat.id,
        f"<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> Добавлено <b>{len(configs)}</b> конфигов.",
        admin_menu_kb(),
    )

@router.callback_query(IsAdmin(), F.data == "admin_upload")
async def cb_admin_upload(call: CallbackQuery, state: FSMContext):
    await state.set_state(UploadState.wait_for_file)
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5278227821364275264\">📤</tg-emoji> <b>Загрузить файл</b>\n\nОтправьте .txt файл с конфигурациями (по одной на строке).",
        raw_kb([raw_btn("Отмена", "admin_menu", emoji_id=TG_EMOJI["back"])]),
    )
    await tg_answer(call.id)

@router.message(IsAdmin(), UploadState.wait_for_file)
async def admin_upload_file(message: Message, state: FSMContext):
    if not message.document:
        await tg_send(message.chat.id, "<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Пришлите файл (.txt)", admin_menu_kb())
        await state.clear()
        return

    await tg_send(message.chat.id, "<tg-emoji emoji-id=\"5276220667182736079\">⏳</tg-emoji> Читаю файл...")
    try:
        file_info = await message.bot.get_file(message.document.file_id)
        file_path = file_info.file_path
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}") as r:
                content = await r.text(encoding="utf-8", errors="ignore")

        links = parse_links_from_text(content)
        if not links:
            await tg_send(message.chat.id, "<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Ссылки не найдены в файле.", admin_menu_kb())
            await state.clear()
            return

        await tg_send(message.chat.id, f"<tg-emoji emoji-id=\"5276220667182736079\">⏳</tg-emoji> Обрабатываю <b>{len(links)}</b> ссылок...")
        configs = await process_any_links(links)
        await add_vless_batch(configs)
        await state.clear()
        await tg_send(message.chat.id, f"<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> Добавлено <b>{len(configs)}</b> конфигов.", admin_menu_kb())
    except Exception as e:
        logger.error(f"upload error: {e}")
        await tg_send(message.chat.id, f"<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Ошибка: {e}", admin_menu_kb())
        await state.clear()

@router.callback_query(IsAdmin(), F.data == "admin_list")
async def cb_admin_list(call: CallbackQuery):
    counts = await get_configs_count_by_proto()
    total = sum(counts.values())
    lines = [f"<tg-emoji emoji-id=\"5278227821364275264\">📋</tg-emoji> <b>Конфиги в базе</b>  (всего: {total})\n"]
    for proto, cnt in counts.items():
        label = PROTO_LABELS.get(proto, proto.upper())
        lines.append(f"  {label}: <b>{cnt}</b>")

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "\n".join(lines) or "Конфигов нет.",
        raw_kb([raw_btn("Назад", "admin_menu", emoji_id=TG_EMOJI["back"])]),
    )
    await tg_answer(call.id)

@router.callback_query(IsAdmin(), F.data == "admin_clear_menu")
async def cb_admin_clear_menu(call: CallbackQuery):
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5276442772826515132\">🗑</tg-emoji> <b>Очистить конфиги</b>\n\nВыберите что удалить:", admin_clear_kb())
    await tg_answer(call.id)

@router.callback_query(IsAdmin(), F.data.startswith("admin_clear_proto:"))
async def cb_admin_clear_proto(call: CallbackQuery):
    proto = call.data.split(":")[1]
    if proto == "all":
        await clear_all_configs()
        msg = "Все конфиги удалены."
    else:
        await clear_configs_by_proto(proto)
        msg = f"Конфиги {PROTO_LABELS.get(proto, proto)} удалены."
    await tg_answer(call.id, msg, alert=True)
    await cb_admin_clear_menu(call)

@router.callback_query(IsAdmin(), F.data == "admin_users")
async def cb_admin_users(call: CallbackQuery):
    users = await get_all_users()
    text = (
        f"<tg-emoji emoji-id=\"5275979556308674886\">👥</tg-emoji> <b>Пользователи</b>\n\n"
        f"Всего: <b>{len(users)}</b>\n\n"
    )
    for u in users[-10:]:
        name = u.get("full_name") or u.get("username") or str(u["tg_id"])
        text += f"  <code>{u['tg_id']}</code> — {name}\n"
    if len(users) > 10:
        text += f"\n<i>...и ещё {len(users)-10}</i>"

    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id, text,
        raw_kb([raw_btn("Назад", "admin_menu", emoji_id=TG_EMOJI["back"])]),
    )
    await tg_answer(call.id)

@router.callback_query(IsAdmin(), F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.message)
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5278528159837348960\">🔔</tg-emoji> <b>Рассылка</b>\n\nОтправьте сообщение для рассылки всем пользователям:",
        raw_kb([raw_btn("Отмена", "admin_menu", emoji_id=TG_EMOJI["back"])]),
    )
    await tg_answer(call.id)

@router.message(IsAdmin(), BroadcastState.message)
async def admin_broadcast_msg(message: Message, state: FSMContext):
    await state.clear()
    users = await get_all_users()
    ok = 0
    for u in users:
        try:
            await tg_send(u["tg_id"], message.text or "", back_main_kb())
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await tg_send(message.chat.id, f"<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> Разослано: <b>{ok}/{len(users)}</b>", admin_menu_kb())

@router.callback_query(IsAdmin(), F.data == "admin_vless_spam")
async def cb_admin_vless_spam(call: CallbackQuery, state: FSMContext):
    await state.set_state(VlessSpamState.collecting)
    await state.update_data(spam_links=[])
    await show_menu_with_banner(
        call.message.chat.id, call.message.message_id,
        "<tg-emoji emoji-id=\"5276220667182736079\">⏳</tg-emoji> <b>Spam-режим активен</b>\n\n"
        "Пересылайте любые сообщения с ссылками (vless://, ss://, socks5://, tg://proxy) — "
        "бот будет автоматически их извлекать.\n\n"
        "Для завершения напишите <b>/done</b>",
        raw_kb([raw_btn("Отмена", "admin_menu", emoji_id=TG_EMOJI["cross"])]),
    )
    await tg_answer(call.id)

@router.message(IsAdmin(), StateFilter(VlessSpamState.collecting), Command("done"))
async def admin_spam_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    collected = data.get("spam_links", [])
    await state.clear()
    if not collected:
        await tg_send(message.chat.id,
            "<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Ни одной ссылки не найдено.",
            admin_menu_kb())
        return
    await tg_send(message.chat.id,
        f"<tg-emoji emoji-id=\"5276220667182736079\">⏳</tg-emoji> <b>Обработка {len(collected)} ссылок...</b>")
    configs = await process_any_links(collected)
    if not configs:
        await tg_send(message.chat.id,
            "<tg-emoji emoji-id=\"5278578973595427038\">❌</tg-emoji> Не удалось обработать ссылки.", admin_menu_kb())
        return
    await add_vless_batch(configs)
    proto_stat: dict = {}
    country_stat: dict = {}
    for cfg in configs:
        p = cfg.get("proto", "vless")
        proto_stat[p] = proto_stat.get(p, 0) + 1
        cc = cfg["name"].split()[0]
        country_stat[cc] = country_stat.get(cc, 0) + 1
    proto_text = "  ".join(f"{PROTO_LABELS.get(p,p)}: <b>{c}</b>" for p, c in proto_stat.items())
    country_text = "\n".join(
        f"{cc}: {n}" for cc, n in sorted(country_stat.items(), key=lambda x: -x[1])[:15]
    )
    await tg_send(message.chat.id,
        f"<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> <b>Добавлено {len(configs)} конфигов</b>\n\n"
        f"{proto_text}\n\n"
        f"<tg-emoji emoji-id=\"5278613311858959074\">🌐</tg-emoji> <b>Страны:</b>\n{country_text}",
        admin_menu_kb())

@router.message(IsAdmin(), VlessSpamState.collecting)
async def admin_spam_collect(message: Message, state: FSMContext):
    if message.text and message.text.strip().startswith("/"):
        return
    raw_parts = []
    if message.text:
        raw_parts.append(message.text)
    if message.caption:
        raw_parts.append(message.caption)
    for ents in [message.entities or [], message.caption_entities or []]:
        for e in ents:
            if e.type == "text_link" and e.url:
                raw_parts.append(e.url)
    new_links = parse_links_from_text("\n".join(raw_parts))
    if not new_links:
        return
    data = await state.get_data()
    existing = data.get("spam_links", [])
    added = [l for l in new_links if l not in existing]
    existing.extend(added)
    await state.update_data(spam_links=existing)
    if added:
        await tg_send(
            message.chat.id,
            f"<tg-emoji emoji-id=\"5278411813468269386\">✅</tg-emoji> +{len(added)} ссылок | "
            f"Всего: <b>{len(existing)}</b>\n"
            f"<i>Пересылайте ещё или напишите /done</i>"
        )

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        return
    if not ADMIN_ID:
        logger.error("ADMIN_ID not set")
        return
    if not REQUIRED_CHANNEL_ID:
        logger.error("REQUIRED_CHANNEL_ID not set")
        return

    await init_db()
    logger.info("Database ready")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())