
"""
MIT License

Copyright (c) 2022 Daniel
"""

import os
from random import randint

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


def _search_saavn_tracks(query, limit=5):
    """Search JioSaavn for metadata and official page URLs; no audio download."""
    response = get(
        "https://saavn.dev/search/songs",
        params={"query": query, "page": 1, "limit": limit},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json() or {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    results = data.get("results", []) if isinstance(data, dict) else []

    tracks = []
    for track in results[:limit]:
        album = track.get("album") or {}
        artists = track.get("primaryArtists") or (track.get("artists") or {}).get("primary", [])
        if isinstance(artists, list):
            artist_names = ", ".join(
                a.get("name", "") if isinstance(a, dict) else str(a) for a in artists
            ).strip(", ")
        else:
            artist_names = str(artists or "")
        images = track.get("image") or []
        image_url = images[-1].get("url", "") if isinstance(images, list) and images else ""
        tracks.append({
            "name": track.get("name") or "",
            "artist": artist_names,
            "album": album.get("name", "") if isinstance(album, dict) else str(album),
            "url": track.get("url") or "",
            "duration": track.get("duration"),
            "image": image_url,
            "source": "JioSaavn",
        })
    return tracks


@sync_to_async
def search_saavn_tracks(query, limit=5):
    """Async helper for Spotify handlers to search matching JioSaavn tracks."""
    return _search_saavn_tracks(query, limit)


@sync_to_async
def download_songs(item, download_directory="."):
    """
    Legacy compatibility only. YouTube extraction is removed.

    JioSaavn search results currently provide metadata and official listening
    links, not a licensed downloadable audio file. The Spotify handler must
    call search_saavn_tracks() and present the official link.
    """
    track_name = (item or {}).get("name") or ""
    artists = (item or {}).get("artists") or []
    artist_name = artists[0].get("name", "") if artists and isinstance(artists[0], dict) else ""
    query = f"{track_name} {artist_name}".strip()
    try:
        matches = _search_saavn_tracks(query, limit=3) if query else []
        if matches:
            LOGGER.info(
                "JioSaavn matches for %s: %s",
                query,
                ", ".join(m.get("url", "") for m in matches if m.get("url")),
            )
        else:
            LOGGER.info("No JioSaavn matches found for %s", query)
    except Exception as exc:
        LOGGER.error("JioSaavn search failed for %s: %s", query, exc)
    return None


@sync_to_async
def download_dez(song, download_directory="."):
    """Legacy compatibility stub; no YouTube extraction or audio redistribution."""
    LOGGER.info(
        "Skipping legacy Deezer audio extraction for %s - %s",
        (song or {}).get("name", ""),
        (song or {}).get("artist", ""),
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
