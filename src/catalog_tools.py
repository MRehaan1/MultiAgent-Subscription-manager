"""Music Catalog tools (Task 3).

All lookups use case-insensitive fuzzy matching (`LIKE '%value%'`) so "Rolling
Stones" finds "The Rolling Stones" (decision: grill #11). "Similar artists" is
interpreted as this fuzzy name match — Chinook has no artist-similarity data.
"""

from langchain_core.tools import tool

from .database import run_query

_LIMIT = 50


def _fuzzy(value: str) -> str:
    return f"%{value.strip()}%"


@tool
def get_albums_by_artist(artist: str) -> str:
    """Retrieve albums by a given artist (fuzzy name match)."""
    rows = run_query(
        """
        SELECT al.Title AS album, ar.Name AS artist
        FROM Album al
        JOIN Artist ar ON al.ArtistId = ar.ArtistId
        WHERE ar.Name LIKE :p
        ORDER BY al.Title
        LIMIT :lim
        """,
        {"p": _fuzzy(artist), "lim": _LIMIT},
    )
    if not rows:
        return f"No albums found for an artist matching '{artist}'."
    lines = [f"- {r['album']} (by {r['artist']})" for r in rows]
    return "Albums found:\n" + "\n".join(lines)


@tool
def get_tracks_by_artist(artist: str) -> str:
    """Retrieve tracks (songs) by a given artist or similar (fuzzy-matched) artists."""
    rows = run_query(
        """
        SELECT t.Name AS track, ar.Name AS artist
        FROM Track t
        JOIN Album al ON t.AlbumId = al.AlbumId
        JOIN Artist ar ON al.ArtistId = ar.ArtistId
        WHERE ar.Name LIKE :p
        ORDER BY ar.Name, t.Name
        LIMIT :lim
        """,
        {"p": _fuzzy(artist), "lim": _LIMIT},
    )
    if not rows:
        return f"No tracks found for an artist matching '{artist}'."
    lines = [f"- {r['track']} (by {r['artist']})" for r in rows]
    return "Tracks found:\n" + "\n".join(lines)


@tool
def get_songs_by_genre(genre: str) -> str:
    """Fetch songs that match a specific genre (fuzzy name match)."""
    rows = run_query(
        """
        SELECT t.Name AS song, g.Name AS genre, ar.Name AS artist
        FROM Track t
        JOIN Genre g ON t.GenreId = g.GenreId
        LEFT JOIN Album al ON t.AlbumId = al.AlbumId
        LEFT JOIN Artist ar ON al.ArtistId = ar.ArtistId
        WHERE g.Name LIKE :p
        ORDER BY t.Name
        LIMIT :lim
        """,
        {"p": _fuzzy(genre), "lim": _LIMIT},
    )
    if not rows:
        return f"No songs found for a genre matching '{genre}'."
    lines = [f"- {r['song']} (by {r['artist'] or 'Unknown'}, genre {r['genre']})" for r in rows]
    return "Songs found:\n" + "\n".join(lines)


@tool
def check_for_songs(song_title: str) -> str:
    """Check whether a song exists by its name (fuzzy name match)."""
    rows = run_query(
        """
        SELECT t.Name AS song, ar.Name AS artist
        FROM Track t
        LEFT JOIN Album al ON t.AlbumId = al.AlbumId
        LEFT JOIN Artist ar ON al.ArtistId = ar.ArtistId
        WHERE t.Name LIKE :p
        ORDER BY t.Name
        LIMIT :lim
        """,
        {"p": _fuzzy(song_title), "lim": 25},
    )
    if not rows:
        return f"No song found matching '{song_title}'."
    lines = [f"- {r['song']} (by {r['artist'] or 'Unknown'})" for r in rows]
    return "Matching songs:\n" + "\n".join(lines)


CATALOG_TOOLS = [
    get_albums_by_artist,
    get_tracks_by_artist,
    get_songs_by_genre,
    check_for_songs,
]

# Names used by create_memory's "music engaged?" gate (decision: grill #7).
CATALOG_TOOL_NAMES = {t.name for t in CATALOG_TOOLS}
