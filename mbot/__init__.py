
"""MIT License

Copyright (c) 2022 Daniel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"""

from pyrogram import Client
from os import environ, sys, mkdir, path
import logging
import requests
from flask import Flask
from threading import Thread
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from aiohttp import ClientSession
from dotenv import load_dotenv
import os
import shutil
import time

load_dotenv("config.env")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

# Mandatory Variables
try:
    API_ID = int(environ["API_ID"])
    API_HASH = environ["API_HASH"]
    BOT_TOKEN = environ["BOT_TOKEN"]
    OWNER_ID = int(environ["OWNER_ID"])

except KeyError as e:
    LOGGER.error(f"Missing environment variable: {e}")
    sys.exit(1)

except ValueError as e:
    LOGGER.error(f"Invalid environment variable: {e}")
    sys.exit(1)

# Optional Variables
F_SUB = environ.get("F_SUB", False)
F_SUB_CHANNEL_ID = environ.get("F_SUB_CHANNEL_ID")
F_SUB_CHANNEL_INVITE_LINK = environ.get("F_SUB_CHANNEL_INVITE_LINK")

SUDO_USERS = environ.get("SUDO_USERS", str(OWNER_ID)).split()
SUDO_USERS = [int(x) for x in SUDO_USERS]

if OWNER_ID not in SUDO_USERS:
    SUDO_USERS.append(OWNER_ID)

# FIX: AUTH_CHATS can safely be empty
AUTH_CHATS = environ.get("AUTH_CHATS", "").split()
AUTH_CHATS = [int(x) for x in AUTH_CHATS]

LOG_GROUP = environ.get("LOG_GROUP")
if LOG_GROUP:
    LOG_GROUP = int(LOG_GROUP)

BUG = environ.get("BUG")
if BUG:
    BUG = int(BUG)

genius_api = environ.get("genius_api")

# Paste helper
def paste(text):
    try:
        url = "https://spaceb.in/api/"
        res = requests.post(
            url,
            json={"content": text, "extension": "txt"},
            timeout=20
        )
        return f"https://spaceb.in/{res.json()['payload']['id']}"

    except Exception:
        try:
            url = "https://dpaste.org/api/"
            data = {
                "format": "json",
                "content": text.encode("utf-8"),
                "lexer": "python",
                "expires": "604800"
            }

            res = requests.post(url, data=data, timeout=20)
            return res.json()["url"]

        except Exception as e:
            LOGGER.error(f"Paste failed: {e}")
            return None


class Mbot(Client):

    def __init__(self):
        name = self.__class__.__name__.lower()

        super().__init__(
            ":memory:",
            plugins=dict(root=f"{name}/plugins"),
            workdir="",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            sleep_threshold=30
        )

    # FIX: Accept arguments passed by the installed Pyrogram/Kurigram run()
    async def start(self, *args, **kwargs):

        global BOT_INFO

        await super().start(*args, **kwargs)

        BOT_INFO = await self.get_me()

        if not path.exists("/tmp/thumbnails/"):
            mkdir("/tmp/thumbnails/")

        for chat in AUTH_CHATS:
            try:
                await self.send_photo(
                    chat,
                    "https://telegra.ph/file/97bc8a091ac1b119b72e4.jpg",
                    "**Spotify Downloader Started**"
                )
            except Exception as e:
                LOGGER.error(f"Could not notify chat {chat}: {e}")

        LOGGER.info(
            f"Bot Started Successfully As @{BOT_INFO.username}"
        )

    async def stop(self, *args, **kwargs):
        await super().stop(*args, **kwargs)
        LOGGER.info("Bot Stopped, Bye.")


# Flask uptime server
RENDER_EXTERNAL_URL = environ.get(
    "RENDER_EXTERNAL_URL",
    "http://localhost:10000"
)


def ping_self():
    url = f"{RENDER_EXTERNAL_URL}/alive"

    try:
        response = requests.get(url, timeout=15)

        if response.status_code == 200:
            LOGGER.info("Ping successful!")
        else:
            LOGGER.error(
                f"Ping failed with status code {response.status_code}"
            )

    except Exception as e:
        LOGGER.error(f"Ping failed: {e}")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.utc)

    scheduler.add_job(
        ping_self,
        "interval",
        minutes=3
    )

    scheduler.start()
    return scheduler


app = Flask(__name__)


@app.route("/alive")
def alive():
    return "I am alive!", 200


def run_flask():
    app.run(
        host="0.0.0.0",
        port=int(environ.get("PORT", 10000)),
        debug=False,
        use_reloader=False
    )


# Start background services
flask_thread = Thread(
    target=run_flask,
    daemon=True
)
flask_thread.start()

scheduler = start_scheduler()
            
