"""JioSaavn metadata search plugin for the Telegram bot.

This plugin searches JioSaavn and returns track metadata and the official
JioSaavn page link. It does not download or redistribute full audio.
"""

import requests
from pyrogram import Client, filters


@Client.on_message(filters.command("saavn") & filters.text)
async def saavn_search(client, message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text("Usage: /saavn <song name or artist>")
        return

    query = parts[1].strip()
    status = await message.reply_text("🔎 Searching JioSaavn...")

    try:
        response = requests.get(
            "https://saavn.dev/search/songs",
            params={"query": query, "page": 1, "limit": 5},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        # Support the response shape used by the API versions commonly seen
        # by this project, while failing clearly if the schema changes.
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            await status.edit_text("No JioSaavn results found. Try another title or artist.")
            return

        lines = [f"🎵 **JioSaavn results for:** `{query}`", ""]
        for index, track in enumerate(results[:5], start=1):
            name = track.get("name") or "Unknown title"
            artists = track.get("primaryArtists") or track.get("artists", {}).get("primary", [])
            if isinstance(artists, list):
                artist_names = ", ".join(
                    a.get("name", "") if isinstance(a, dict) else str(a)
                    for a in artists
                ).strip(", ")
            else:
                artist_names = str(artists)
            album = track.get("album", {})
            album_name = album.get("name", "Unknown album") if isinstance(album, dict) else str(album)
            page_url = track.get("url") or ""
            duration = track.get("duration")
            duration_text = f"{int(duration) // 60}:{int(duration) % 60:02d}" if str(duration or "").isdigit() else "Unknown"

            lines.append(
                f"**{index}. {name}**\n"
                f"Artist: {artist_names or 'Unknown'}\n"
                f"Album: {album_name}\n"
                f"Duration: {duration_text}\n"
                f"[Open on JioSaavn]({page_url})" if page_url else
                f"**{index}. {name}**\nArtist: {artist_names or 'Unknown'}\nAlbum: {album_name}\nDuration: {duration_text}"
            )
            lines.append("")

        await status.edit_text("\n".join(lines), disable_web_page_preview=True)

    except requests.RequestException as exc:
        await status.edit_text(f"JioSaavn search request failed: `{type(exc).__name__}`")
    except Exception as exc:
        await status.edit_text(f"JioSaavn search failed: `{type(exc).__name__}: {exc}`")
