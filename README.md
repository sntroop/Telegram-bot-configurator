# Telegram-bot-configurator
A long time ago, I made a small telegram bot that distributes various VPN configurations for free - vless, mtrpoto, shadowsocks &amp; more

# ⚡️ Telegram VPN Manager (VLESS / Reality)

Simple. Fast. Private. This is a Telegram bot designed to manage your own VPN infrastructure based on the **3X-UI** panel. No more manual config sharing — just give your friends (or users) a link and let the bot handle the rest.

## 🔥 Why it's cool:

* **Fully Automated:** It talks to your 3X-UI panel API so you don't have to.
* **Smart Limits:** Set daily usage limits so your server doesn't explode from over-usage.
* **Growth Hack:** Built-in "Force Join" feature. Want a VPN config? Subscribe to my channel first.
* **Clean Code:** Written with `Aiogram 3.x` — it's fast, asynchronous, and stable.
* **Privacy First:** Everything is stored in your own SQLite database and configured via `.env`.

## 🛠 Tech Stack

- **Python 3.10+** — The heart of the project.
- **Aiogram 3** — Modern & fast Telegram Bot framework.
- **Aiosqlite** — For asynchronous database operations.
- **3X-UI API** — The engine that generates your VLESS keys.

## 🛠 Setup
```bash
git clone https://github.com/sntroop/telegram-bot-configurator.git
cd telegram-bot-configurator
pip install aiogram aiohttp aiosqlite
python v.py

