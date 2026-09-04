import asyncio
import json
import logging
import os
import subprocess
import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
PROXY = os.getenv("PROXY")
MAX_SIZE = 50 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


def probe_size(path: str) -> tuple[int | None, int | None]:

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", path],
            capture_output=True, text=True, check=True,
        )
        stream = json.loads(result.stdout)["streams"][0]
        return stream["width"], stream["height"]
    except Exception:
        logging.warning("ffprobe не смог прочитать размеры %s", path)
        return None, None


def download(url: str) -> dict:

    options = {
        "format": (
            f"bestvideo[height<=720][vcodec^=avc1][filesize<{MAX_SIZE}]"
            f"+bestaudio[acodec^=mp4a]/"
            f"best[height<=720][filesize<{MAX_SIZE}]/best"
        ),
        "outtmpl": "downloads/%(title).60s.%(ext)s",
        "noplaylist": True,
        "proxy": PROXY,
        "remote_components": ["ejs:github"],
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        path = info["requested_downloads"][0]["filepath"]

        width, height = probe_size(path)
        if width is None:
            width, height = info.get("width"), info.get("height")

        return {
            "path": path,
            "width": width,
            "height": height,
            "duration": info.get("duration"),
            "title": info.get("title"),
        }


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Привет! Отправь ссылку на видео — скачаю и верну файлом.")


@dp.message(F.text.startswith("http"))
async def handle_link(message: Message):
    status = await message.answer("Скачиваю…")

    try:
        video = await asyncio.to_thread(download, message.text)
    except Exception as e:
        logging.exception("Ошибка скачивания")
        await status.edit_text(f"Не получилось скачать: {e}")
        return

    path = video["path"]

    try:
        if os.path.getsize(path) > MAX_SIZE:
            await status.edit_text("Видео больше 50 МБ — Telegram не пропустит.")
            return

        await status.edit_text("Отправляю…")
        await message.answer_video(
            FSInputFile(path),
            width=video["width"],
            height=video["height"],
            duration=video["duration"],
            caption=video["title"],
            supports_streaming=True,
        )
        await status.delete()
        await message.answer("Готово! Присылай следующую ссылку.")
    except Exception as e:
        logging.exception("Ошибка отправки")
        await status.edit_text(f"Не получилось отправить: {e}")
    finally:
        try:
            os.remove(path)
        except OSError:
            logging.warning("Не удалось удалить %s", path)


@dp.message()
async def fallback(message: Message):
    await message.answer("Это не похоже на ссылку. Пришли URL видео.")


async def main():
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
