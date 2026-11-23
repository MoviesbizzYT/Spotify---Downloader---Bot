"""Shared helpers for the Spotify/JioSaavn Telegram bot.

The Spotify integration uses JioSaavn search metadata and official listening
URLs. It does not download or redistribute copyrighted audio.
"""

import os
from urllib.parse import urlparse

import requests
from asgiref.sync import sync_to_async

from mbot import LOGGER, LOG_GROUP, BUG


# Current API server documented by the JioSaavn API project.
# Can be overridden in the hosting environment if the provider changes it.
SAAVN_API_BASE_URL = os.environ.get(
    "SAAVN_API_BASE_URL", "https://saavn.bycomsolutions.com/api"
).rstrip("/")
SAAVN_SEARCH_TIMEOUT = int(os.environ.get("SAAVN_SEARCH_TIMEOUT", "20"))


@sync_to_async
def parse_deezer_url(url):
    response = requests.get(url, timeout=20, allow_redirects=True)
    response.raise_for_status()
    parsed_url = response.url.replace("https://www.deezer.com/", "")
    parts = parsed_url.split("/")
    if len(parts) < 3:
        raise ValueError("Unsupported Deezer URL")
    return parts[1], parts[2].split("?")[0]


@sync_to_async
def parse_spotify_url(url):
    """Return (item_type, item_id) for Spotify URLs and Spotify URIs."""
    url = (url or "").strip()

    if url.startswith("spotify:"):
        parts = url.split(":")
        if len(parts) >= 3:
            return parts[1], parts[2]
        raise ValueError("Invalid Spotify URI")

    if "spotify.link/" in url:
        response = requests.get(url, timeout=20, allow_redirects=True)
        response.raise_for_status()
        url = response.url

    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"open.spotify.com", "www.open.spotify.com"}:
        raise ValueError("Unsupported Spotify URL")

    parts = [part for part in parsed.path.split("/") if part]
    # Spotify URLs may include a locale prefix, e.g. /intl-en/track/<id>.
    if parts and parts[0].startswith("intl-"):
        parts = parts[1:]
    if len(parts) < 2:
        raise ValueError("Spotify URL does not contain an item ID")

    item_type, item_id = parts[0], parts[1]
    if item_type not in {"track", "album", "playlist", "artist", "show", "episode"}:
        raise ValueError(f"Unsupported Spotify item type: {item_type}")
    return item_type, item_id


@sync_to_async
def thumb_down(link, deezer_id):
    """Download a supplied artwork image to the temporary thumbnail folder."""
    if not link:
        raise ValueError("No artwork URL was supplied")

    os.makedirs("/tmp/thumbnails", exist_ok=True)
    safe_id = "".join(ch for ch in str(deezer_id) if ch.isalnum() or ch in "-_ ")
    if not safe_id:
        safe_id = "artwork"
    path = f"/tmp/thumbnails/{safe_id}.jpg"

    response = requests.get(link, timeout=30)
    response.raise_for_status()
    with open(path, "wb") as file:
        file.write(response.content)
    return path


@sync_to_async
def fetch_tracks(dz, item_type, item_id):
    """Fetch track metadata from the existing Deezer client."""
    songs_list = []

    if item_type == "playlist":
        items = dz.get_playlist(item_id).tracks
        for index, item in enumerate(items, start=1):
            songs_list.append({
                "name": item.title,
                "artist": item.artist.name,
                "album": item.album.title,
                "playlist_num": index,
                "cover": item.album.cover_xl,
                "deezer_id": item.id,
                "thumb": item.album.cover_small,
                "duration": item.duration,
            })

    elif item_type == "album":
        album = dz.get_album(item_id)
        for index, item in enumerate(album.tracks, start=1):
            songs_list.append({
                "name": item.title,
                "artist": item.artist.name,
                "album": album.title,
                "playlist_num": index,
                "cover": album.cover_xl,
                "deezer_id": item.id,
                "thumb": album.cover_small,
                "duration": item.duration,
            })

    elif item_type == "track":
        item = dz.get_track(item_id)
        songs_list.append({
            "name": item.title,
            "artist": item.artist.name,
            "album": item.album.title,
            "playlist_num": 1,
            "cover": item.album.cover_xl,
            "deezer_id": item.id,
            "thumb": item.album.cover_small,
            "duration": item.duration,
        })

    return songs_list


@sync_to_async
def fetch_spotify_track(client, item_id):
    """Fetch Spotify track metadata without assuming optional fields exist."""
    item = client.track(track_id=item_id)
    album_info = item.get("album") or {}
    artists = item.get("artists") or []
    artist_names = [a.get("name", "") for a in artists if a.get("name")]
    release_date = album_info.get("release_date") or ""
    images = album_info.get("images") or []

    genre = ""
    try:
        if artists and artists[0].get("id"):
            artist_info = client.artist(artists[0]["id"])
            genres = artist_info.get("genres") or []
            genre = genres[0] if genres else ""
    except Exception as exc:
        LOGGER.warning("Could not fetch Spotify artist genre: %s", exc)

    return {
        "name": item.get("name", ""),
        "artist": ", ".join(artist_names),
        "album": album_info.get("name", ""),
        "year": release_date[:4],
        "num_tracks": album_info.get("total_tracks", 0),
        "num": item.get("track_number", 0),
        "playlist_num": 1,
        "cover": images[0].get("url") if images else None,
        "genre": genre,
        "deezer_id": item_id,
    }


def _first_image(images):
    """Extract an image URL from the API's quality/url image array."""
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict) and image.get("url"):
            return image["url"]
    return None


def _normalize_saavn_song(song):
    """Normalize one JioSaavn search result for the Telegram plugin."""
    if not isinstance(song, dict):
        return None

    artists_block = song.get("artists") or {}
    primary_artists = artists_block.get("primary") or []
    artist_names = [
        artist.get("name", "")
        for artist in primary_artists
        if isinstance(artist, dict) and artist.get("name")
    ]

    # Some API versions expose a flat primaryArtists string instead.
    artist_text = ", ".join(artist_names) or song.get("primaryArtists") or "Unknown artist"
    album = song.get("album") or {}
    if isinstance(album, dict):
        album_name = album.get("name") or ""
    else:
        album_name = str(album)

    return {
        "id": song.get("id"),
        "name": song.get("name") or song.get("title") or "Unknown title",
        "artist": artist_text,
        "album": album_name,
        "duration": song.get("duration"),
        "url": song.get("url"),
        "cover": _first_image(song.get("image")) or song.get("image_url"),
        "language": song.get("language"),
    }


def _search_saavn_tracks(query, limit=5):
    """Synchronous JioSaavn search; raises a clear error on API/DNS failures."""
    query = " ".join(str(query or "").split()).strip()
    if not query:
        return []

    endpoint = f"{SAAVN_API_BASE_URL}/search/songs"
    try:
        response = requests.get(
            endpoint,
            params={"query": query, "page": 0, "limit": max(1, min(int(limit), 20))},
            headers={"User-Agent": "Mozilla/5.0 (compatible; TelegramMusicBot/1.0)"},
            timeout=SAAVN_SEARCH_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.Timeout as exc:
        LOGGER.warning("JioSaavn search timed out: %s", exc)
        raise RuntimeError("JioSaavn search timed out. Please try again shortly.") from exc
    except requests.exceptions.ConnectionError as exc:
        LOGGER.warning("Cannot connect to JioSaavn API (%s): %s", endpoint, exc)
        raise RuntimeError(
            "Cannot reach the JioSaavn API from this hosting server. "
            "Check the host's DNS/network connection and try again."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        LOGGER.warning("JioSaavn API returned an HTTP error: %s", exc)
        raise RuntimeError(f"JioSaavn API returned an HTTP error: {exc}") from exc
    except (requests.exceptions.RequestException, ValueError) as exc:
        LOGGER.exception("JioSaavn search request failed")
        raise RuntimeError(f"JioSaavn search failed: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("success") is False:
        raise RuntimeError("JioSaavn API returned an unsuccessful response.")

    data = payload.get("data") or {}
    raw_results = data.get("results") or []
    if not isinstance(raw_results, list):
        raise RuntimeError("JioSaavn API response format was not recognized.")

    results = []
    for raw_song in raw_results:
        normalized = _normalize_saavn_song(raw_song)
        if normalized and normalized.get("url"):
            results.append(normalized)
        if len(results) >= limit:
            break
    return results


@sync_to_async

def search_saavn_tracks(query, limit=5):
    """Async wrapper used by spotify.py to search JioSaavn."""
    return _search_saavn_tracks(query, limit)


@sync_to_async
def download_songs(item, download_directory="."):
    """Legacy compatibility stub: Spotify links now resolve to official links."""
    LOGGER.warning(
        "download_songs() is disabled: this bot does not fetch audio from YouTube."
    )
    return None


@sync_to_async
def download_dez(song, download_directory="."):
    """Legacy compatibility stub: no unlicensed audio extraction is performed."""
    LOGGER.warning(
        "download_dez() is disabled: configure an audio source you are authorized to use."
    )
    return None


@sync_to_async
def copy(P, A):
    if P is not None:
        P.copy(BUG)
    if A is not None:
        A.copy(BUG)


@sync_to_async
def forward(A, P):
    if A is not None:
        A.copy(LOG_GROUP)
    if P is not None:
        P.copy(LOG_GROUP)
