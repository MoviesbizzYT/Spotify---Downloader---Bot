
"""
MIT License

Copyright (c) 2022 Daniel
"""

import os
from random import randint

from yt_dlp import YoutubeDL
from mbot import LOGGER, LOG_GROUP, BUG
from requests import get
from asyncio import sleep
from asgiref.sync import sync_to_async

FIXIE_SOCKS_HOST = os.environ.get("FIXIE_SOCKS_HOST")


@sync_to_async
def parse_deezer_url(url):
    url = get(url).url
    parsed_url = url.replace("https://www.deezer.com/", "")
    item_type = parsed_url.split("/")[1]
    item_id = parsed_url.split("/")[2].split("?")[0]
    return item_type, item_id


@sync_to_async
def parse_spotify_url(url):
    if url.startswith("spotify"):
        return url.split(":")[1]

    url = get(url).url
    parsed_url = url.replace(
        "https://open.spotify.com/", ""
    ).split("/")

    return parsed_url[0], parsed_url[1].split("?")[0]


@sync_to_async
def thumb_down(link, deezer_id):
    os.makedirs("/tmp/thumbnails", exist_ok=True)

    with open(f"/tmp/thumbnails/{deezer_id}.jpg", "wb") as file:
        file.write(get(link, timeout=30).content)

    return f"/tmp/thumbnails/{deezer_id}.jpg"


@sync_to_async
def fetch_tracks(dz, item_type, item_id):
    """
    Fetch tracks from the provided Deezer URL.
    """

    songs_list = []
    offset = 0

    if item_type == "playlist":
        get_play = dz.get_playlist(item_id)
        items = get_play.tracks

        for item in items:
            track_name = item.title
            track_artist = item.artist.name
            track_album = item.album.title
            cover = item.album.cover_xl
            thumb = item.album.cover_small
            deezer_id = item.id

            songs_list.append({
                "name": track_name,
                "artist": track_artist,
                "album": track_album,
                "playlist_num": offset + 1,
                "cover": cover,
                "deezer_id": deezer_id,
                "thumb": thumb,
                "duration": item.duration
            })

            offset += 1

    elif item_type == "album":
        get_al = dz.get_album(item_id)

        track_album = get_al.title
        cover = get_al.cover_xl
        thumb = get_al.cover_small
        items = get_al.tracks

        for item in items:
            track_name = item.title
            track_artist = item.artist.name
            deezer_id = item.id

            songs_list.append({
                "name": track_name,
                "artist": track_artist,
                "album": track_album,
                "playlist_num": offset + 1,
                "cover": cover,
                "deezer_id": deezer_id,
                "thumb": thumb,
                "duration": item.duration
            })

            offset += 1

    elif item_type == "track":
        get_track = dz.get_track(item_id)

        songs_list.append({
            "name": get_track.title,
            "artist": get_track.artist.name,
            "album": get_track.album.title,
            "playlist_num": offset + 1,
            "cover": get_track.album.cover_xl,
            "deezer_id": get_track.id,
            "thumb": get_track.album.cover_small,
            "duration": get_track.duration
        })

    return songs_list


@sync_to_async
def fetch_spotify_track(client, item_id):
    """
    Fetch Spotify track metadata.
    Handles missing genres safely.
    """

    item = client.track(track_id=item_id)

    track_name = item.get("name", "")

    album_info = item.get("album") or {}

    track_artist = ", ".join(
        artist.get("name", "")
        for artist in item.get("artists", [])
    )

    track_album = album_info.get("name", "")

    release_date = album_info.get("release_date") or ""
    track_year = release_date[:4] if release_date else ""

    album_total = album_info.get("total_tracks", 0)

    track_num = item.get("track_number", 0)

    deezer_id = item_id

    images = album_info.get("images") or []
    cover = images[0].get("url") if images else None

    # Spotify artist genre information
    # may be unavailable for some API responses.
    genre = ""

    try:
        artists = item.get("artists") or []

        if artists:
            artist_id = artists[0].get("id")

            if artist_id:
                artist_info = client.artist(artist_id)
                genres = artist_info.get("genres") or []

                if genres:
                    genre = genres[0]

    except Exception as e:
        LOGGER.warning(
            f"Could not fetch Spotify artist genre: {e}"
        )

    return {
        "name": track_name,
        "artist": track_artist,
        "album": track_album,
        "year": track_year,
        "num_tracks": album_total,
        "num": track_num,
        "playlist_num": 1,
        "cover": cover,
        "genre": genre,
        "deezer_id": deezer_id
    }


@sync_to_async
def download_songs(item, download_directory="."):
    """
    Download audio from an authorized source
    using yt-dlp and convert it to FLAC.
    """

    os.makedirs(download_directory, exist_ok=True)

    file = (
        f"{download_directory}/"
        f"{item['name']} - {item['artists'][0]['name']}"
    )

    query = (
        f"{item['name']} - {item['artists'][0]['name']}"
    ).replace(":", "").replace('"', "")

    ydl_opts = {
        "format": "bestaudio",
        "default_search": "ytsearch",
        "noplaylist": True,
        "nocheckcertificate": True,
        "outtmpl": file,
        "quiet": True,
        "addmetadata": True,
        "prefer_ffmpeg": False,
        "geo_bypass": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "flac",
            "preferredquality": "693"
        }]
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(
                f"ytsearch:{query}",
                download=True
            )

            entry = info["entries"][0]
            filename = ydl.prepare_filename(entry)

            return os.path.splitext(filename)[0] + ".flac"

        except Exception as e:
            LOGGER.error(f"Audio download failed: {e}")

            if FIXIE_SOCKS_HOST:
                try:
                    ydl_opts["proxy"] = f"socks5://{FIXIE_SOCKS_HOST}"

                    with YoutubeDL(ydl_opts) as proxy_ydl:
                        info = proxy_ydl.extract_info(
                            f"ytsearch:{query}",
                            download=True
                        )

                        entry = info["entries"][0]
                        filename = proxy_ydl.prepare_filename(entry)

                        return os.path.splitext(filename)[0] + ".flac"

                except Exception as proxy_error:
                    LOGGER.error(
                        f"Proxy download failed: {proxy_error}"
                    )

            return None


@sync_to_async
def download_dez(song, download_directory="."):
    """
    Download audio for a Deezer track using
    an authorized audio source.
    """

    os.makedirs(download_directory, exist_ok=True)

    file = (
        f"{download_directory}/"
        f"{song['name']} - {song['artist']}"
    )

    query = (
        f"{song.get('name')} - {song.get('artist')}"
    ).replace(":", "").replace('"', "").strip()

    ydl_opts = {
        "format": "bestaudio",
        "default_search": "ytsearch",
        "noplaylist": True,
        "nocheckcertificate": True,
        "outtmpl": file,
        "quiet": True,
        "addmetadata": True,
        "prefer_ffmpeg": False,
        "geo_bypass": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "flac",
            "preferredquality": "824"
        }]
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(
                f"ytsearch:{query}",
                download=True
            )

            entry = info["entries"][0]
            filename = ydl.prepare_filename(entry)

            return os.path.splitext(filename)[0] + ".flac"

        except Exception as e:
            LOGGER.error(f"Deezer audio download failed: {e}")

            if FIXIE_SOCKS_HOST:
                try:
                    ydl_opts["proxy"] = FIXIE_SOCKS_HOST

                    with YoutubeDL(ydl_opts) as proxy_ydl:
                        info = proxy_ydl.extract_info(
                            f"ytsearch:{query}",
                            download=True
                        )

                        entry = info["entries"][0]
                        filename = proxy_ydl.prepare_filename(entry)

                        return os.path.splitext(filename)[0] + ".flac"

                except Exception as proxy_error:
                    LOGGER.error(
                        f"Proxy download failed: {proxy_error}"
                    )

            return None


@sync_to_async
def copy(P, A):
    P.copy(BUG)
    A.copy(BUG)


@sync_to_async
def forward(A, P):
    A.copy(LOG_GROUP)
    P.copy(LOG_GROUP)
