"""
Spotify metadata lookup with JioSaavn official listening links.

This plugin does not download or redistribute copyrighted audio. It matches
Spotify track metadata against JioSaavn search results and shares official
JioSaavn pages.
"""
from asyncio import sleep

from pyrogram import filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError, ChatWriteForbidden, Forbidden, UserIsBlocked

from mbot import LOGGER, Mbot, LOG_GROUP, BUG
from mbot.utils.mainhelper import (
    parse_spotify_url,
    fetch_spotify_track,
    search_saavn_tracks,
    thumb_down,
)
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from requests import head
from requests.exceptions import RequestException


MAIN = bool(__import__("os").environ.get("MAIN"))
spotify = Spotify(auth_manager=SpotifyClientCredentials())


def _spotify_track_url(track_id):
    return f"https://open.spotify.com/track/{track_id}"


async def _send_saavn_matches(message: Message, spotify_song: dict, track_id: str,
                              track_number: int = None, total: int = None):
    """Search Saavn and show official listening links for one Spotify track."""
    title = spotify_song.get("name") or "Unknown track"
    artist = spotify_song.get("artist") or "Unknown artist"
    query = f"{title} {artist}".strip()

    try:
        matches = await search_saavn_tracks(query, limit=5)
    except Exception:
        LOGGER.exception("JioSaavn search failed for %s", query)
        matches = []

    prefix = ""
    if track_number is not None and total is not None:
        prefix = f"🎵 Track {track_number}/{total}\n"

    if not matches:
        await message.reply_text(
            f"{prefix}🎧 {title}\n"
            f"🎤 {artist}\n\n"
            "JioSaavn-ൽ ഈ പാട്ടിന് match കണ്ടെത്താനായില്ല.\n"
            f"Spotify: {_spotify_track_url(track_id)}"
        )
        return None

    # Display up to three official results so the user can choose the right version.
    buttons = []
    lines = [
        f"{prefix}🎧 {title}",
        f"🎤 {artist}",
        f"💽 {spotify_song.get('album') or 'Unknown album'}",
        "",
        "JioSaavn-ൽ ലഭ്യമായ matches:",
    ]
    for index, match in enumerate(matches[:3], start=1):
        result_title = match.get("name") or title
        result_artist = match.get("artist") or artist
        result_album = match.get("album") or ""
        duration = match.get("duration")
        duration_text = ""
        try:
            if duration:
                seconds = int(duration)
                duration_text = f" · {seconds // 60}:{seconds % 60:02d}"
        except (TypeError, ValueError):
            pass

        lines.append(
            f"\n{index}. {result_title} — {result_artist}{duration_text}"
            + (f"\n   Album: {result_album}" if result_album else "")
        )
        url = match.get("url")
        if url:
            buttons.append([
                InlineKeyboardButton(
                    text=f"▶️ Open JioSaavn {index}",
                    url=url
                )
            ])

    buttons.append([
        InlineKeyboardButton(text="Open Spotify", url=_spotify_track_url(track_id))
    ])
    markup = InlineKeyboardMarkup(buttons) if buttons else None

    image = matches[0].get("image")
    try:
        if image:
            sent = await message.reply_photo(
                image,
                caption="\n".join(lines)[:1024],
                reply_markup=markup,
            )
        else:
            sent = await message.reply_text("\n".join(lines), reply_markup=markup)
    except Exception:
        sent = await message.reply_text("\n".join(lines), reply_markup=markup)

    return sent


async def _process_track(message: Message, track_id: str,
                         track_number: int = None, total: int = None):
    song = await fetch_spotify_track(spotify, track_id)
    return await _send_saavn_matches(
        message, song, track_id, track_number=track_number, total=total
    )


@Mbot.on_message(
    filters.incoming
    & (filters.regex(r"https?://open\.spotify\.com/[^\s]+")
       | filters.regex(r"https?://spotify\.link/[^\s]+")),
    group=-1,
)
async def spotify_dl(client, message: Message):
    if MAIN:
        await message.reply_text("Bot Is Under Maintenance ⚠️")
        return

    status = None
    try:
        link = message.matches[0].group(0).rstrip(".,)")
        if "spotify.link" in link:
            response = head(link, allow_redirects=True, timeout=15)
            link = response.url

        item_type, item_id = await parse_spotify_url(link)
        if item_type not in {"track", "album", "playlist", "artist"}:
            await message.reply_text("ഈ Spotify link type support ചെയ്യുന്നില്ല.")
            return

        # Existing utility commands are retained.
        if message.text and message.text.startswith("/thumb"):
            if item_type == "track":
                data = spotify.track(item_id)
                image = (data.get("album", {}).get("images") or [{}])[0].get("url")
            elif item_type == "album":
                data = spotify.album(item_id)
                image = (data.get("images") or [{}])[0].get("url")
            elif item_type == "playlist":
                data = spotify.playlist(item_id)
                image = (data.get("images") or [{}])[0].get("url")
            else:
                data = spotify.artist(item_id)
                image = (data.get("images") or [{}])[0].get("url")
            if image:
                await message.reply_document(image)
            else:
                await message.reply_text("Thumbnail ലഭ്യമല്ല.")
            return

        if message.text and message.text.startswith("/preview"):
            if item_type != "track":
                await message.reply_text("Spotify preview track links-ന് മാത്രമാണ്.")
                return
            data = spotify.track(item_id)
            preview = data.get("preview_url")
            if preview:
                await message.reply_audio(preview)
            else:
                await message.reply_text(
                    "ഈ track-ന് Spotify preview ലഭ്യമല്ല. "
                    "Full audio ഇവിടെ download ചെയ്യുന്നില്ല."
                )
            return

        status = await message.reply_text("🔎 Spotify details പരിശോധിക്കുന്നു…")
        await message.reply_chat_action(enums.ChatAction.TYPING)

        if item_type == "track":
            await _process_track(message, item_id)

        elif item_type == "album":
            album = spotify.album(item_id)
            artists = ", ".join(a.get("name", "") for a in album.get("artists", []))
            cover = (album.get("images") or [{}])[0].get("url")
            header = (
                f"💽 Album: {album.get('name', 'Unknown')}\n"
                f"👥 Artist(s): {artists or 'Unknown'}\n"
                f"🎧 Total tracks: {album.get('total_tracks', 0)}\n"
                f"📅 Release: {album.get('release_date', 'Unknown')}"
            )
            if cover:
                await message.reply_photo(cover, caption=header[:1024])
            else:
                await message.reply_text(header)

            tracks = album.get("tracks", {}).get("items", [])
            total = album.get("total_tracks", len(tracks))
            for number, track in enumerate(tracks, start=1):
                if track.get("id"):
                    await _process_track(message, track["id"], number, total)
                    await sleep(0.4)

        elif item_type == "playlist":
            playlist = spotify.playlist(item_id)
            owner = (playlist.get("owner") or {}).get("display_name", "Unknown")
            cover = (playlist.get("images") or [{}])[0].get("url")
            total = (playlist.get("tracks") or {}).get("total", 0)
            header = (
                f"▶️ Playlist: {playlist.get('name', 'Unknown')}\n"
                f"👤 Owner: {owner}\n"
                f"🔢 Total tracks: {total}\n"
                f"🔗 {link}"
            )
            if cover:
                await message.reply_photo(cover, caption=header[:1024])
            else:
                await message.reply_text(header)

            offset = 0
            number = 0
            while offset < total:
                page = spotify.playlist_items(
                    item_id, limit=100, offset=offset,
                    additional_types=["track"],
                )
                entries = page.get("items", [])
                if not entries:
                    break
                for entry in entries:
                    track = (entry or {}).get("track") or {}
                    if track.get("id") and track.get("type") == "track":
                        number += 1
                        await _process_track(message, track["id"], number, total)
                        await sleep(0.4)
                offset += len(entries)
                if len(entries) < 100:
                    break

        elif item_type == "artist":
            artist = spotify.artist(item_id)
            cover = (artist.get("images") or [{}])[0].get("url")
            header = (
                f"👤 Artist: {artist.get('name', 'Unknown')}\n"
                f"❤️ Followers: {(artist.get('followers') or {}).get('total', 0)}\n"
                f"🎶 Genres: {', '.join(artist.get('genres') or []) or 'Unknown'}\n"
                f"⭐ Popularity: {artist.get('popularity', 'N/A')}"
            )
            if cover:
                await message.reply_photo(cover, caption=header[:1024])
            else:
                await message.reply_text(header)

            top_tracks = spotify.artist_top_tracks(item_id).get("tracks", [])[:10]
            await message.reply_text(
                f"Sending up to {len(top_tracks)} top tracks for {artist.get('name', 'this artist')}."
            )
            for number, track in enumerate(top_tracks, start=1):
                if track.get("id"):
                    await _process_track(message, track["id"], number, len(top_tracks))
                    await sleep(0.4)

        if status:
            try:
                await status.delete()
            except Exception:
                pass

    except FloodWait as exc:
        await sleep(exc.value)
        await message.reply_text(
            f"Telegram FloodWait: {exc.value} seconds. Please try again."
        )
    except ChatWriteForbidden:
        try:
            await Mbot.leave_chat(message.chat.id)
        except Exception:
            pass
    except (Forbidden, UserIsBlocked):
        LOGGER.warning("Bot cannot message this user/chat")
    except (RequestException, RPCError) as exc:
        LOGGER.exception("Spotify/JioSaavn request failed")
        await message.reply_text(f"Request failed: {str(exc)[:500]}")
    except Exception as exc:
        LOGGER.exception("Spotify handler failed")
        await message.reply_text(
            f"Spotify link process ചെയ്യാൻ കഴിഞ്ഞില്ല: {str(exc)[:500]}"
        )
        if BUG:
            try:
                await Mbot.send_message(BUG, f"Spotify plugin error: {str(exc)[:3000]}")
            except Exception:
                pass
    finally:
        if status:
            try:
                await status.delete()
            except Exception:
                pass


@Mbot.on_callback_query(filters.regex(r"^feed$"))
async def feedback(_, query):
    try:
        await query.message.edit(
            "Feedback 🏴‍☠️",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    text="Press here",
                    url="https://t.me/dailychannelsbot?start=spotify_downloa_bot",
                )
            ]]),
        )
    except Exception as exc:
        LOGGER.warning("Feedback callback failed: %s", exc)


@Mbot.on_callback_query(filters.regex(r"^bug$"))
async def bug_report(_, query):
    try:
        await query.message.edit(
            "Bug Report 🪲",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Report to dev", url="https://t.me/masterolic")
            ]]),
        )
    except Exception as exc:
        LOGGER.warning("Bug callback failed: %s", exc)


@Mbot.on_callback_query(filters.regex(r"^cancel$"))
async def cancel_result(_, query):
    try:
        await query.message.delete()
        await query.answer("Closed ❌")
    except Exception:
        pass
