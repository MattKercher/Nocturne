# sql_instance.py

import sqlite3, os
from ..constants import CACHE_DIR

def get_cache_connection() -> tuple:
    conn = sqlite3.connect(os.path.join(CACHE_DIR, 'cache_database.db'))
    cursor = conn.cursor()
    return conn, cursor

def ensure_cache_schema():
    conn, cursor = get_cache_connection()
    schema_dict = {
        'images': {
            'integration': 'TEXT NOT NULL',
            'model': 'TEXT NOT NULL',
            'size': 'INTEGER DEFAULT 1',
            'image': 'BLOB',
            'UNIQUE': '(integration, model, size)'
        }
    }
    try:
        for table_name, columns in schema_dict.items():
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if not cursor.fetchone():
                column_defs = ", ".join([f"{name} {props}" for name, props in columns.items()])
                query = f"CREATE TABLE {table_name} ({column_defs});"
                cursor.execute(query)
        conn.commit()
    except sqlite3.Error as e:
        print("Error", e)
        return

def get_connection(integration) -> tuple:
    conn = sqlite3.connect(os.path.join(integration.getIntegrationDir(), 'database.db'))
    cursor = conn.cursor()
    return conn, cursor

def ensure_schema(integration):
    conn, cursor = get_connection(integration)
    schema_dict = integration.get_sql_schema()
    try:
        for table_name, columns in schema_dict.items():
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )

            if not cursor.fetchone():
                column_defs = ", ".join([f"{name} {props}" for name, props in columns.items()])
                query = f"CREATE TABLE {table_name} ({column_defs});"
                cursor.execute(query)
        conn.commit()
    except sqlite3.Error as e:
        print("Error", e)
        return

    # JSON Migration

    cursor = conn.cursor()

    ## Playlist Resume (Base)
    if 'playlist_resume' in schema_dict:
        if playlist_resume_dict := integration.open_json('playlist_resume.json'):
            to_insert = []
            for playlistId, songId in playlist_resume_dict.items():
                to_insert.append((playlistId, songId))

            query = """
            INSERT INTO playlist_resume (id, song_id)
            VALUES (?, ?)
            ON CONFLICT (id) DO UPDATE SET
                song_id = excluded.song_id;
            """
            cursor.executemany(query, to_insert)
            os.remove(os.path.join(integration.getIntegrationDir(), 'playlist_resume.json'))

    ## Playback (Base)
    if 'playback_scrobble' in schema_dict:
        if playback_dict := integration.open_json('playback.json'):
            to_insert = []
            for month, data in playback_dict.items():
                for songId, amount in data.items():
                    to_insert.append((month, songId, amount))

            query = """
            INSERT INTO playback_scrobble (month, song_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT (month, song_id) DO UPDATE SET
                amount = excluded.amount;
            """
            cursor.executemany(query, to_insert)
            os.remove(os.path.join(integration.getIntegrationDir(), 'playback.json'))

    ## Stars (Local)
    if 'stars' in schema_dict:
        if stars_dict := integration.open_json('stars.json'):
            to_insert = []
            for songId, value in stars_dict.items():
                if value:
                    to_insert.append((songId,))

            query = """
            INSERT OR IGNORE INTO stars (id)
            VALUES (?)
            """
            cursor.executemany(query, to_insert)
            os.remove(os.path.join(integration.getIntegrationDir(), 'stars.json'))

    ## Radios (Local)
    if 'radios' in schema_dict:
        if radios_dict := integration.open_json('radios.json'):
            to_insert = []
            for radioId, data in radios_dict.items():
                row = (radioId, data.get('name'), data.get('streamUrl'))
                if all(row):
                    to_insert.append(row)
            query = """
            INSERT INTO radios (id, name, stream_url)`
            VALUES (?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name,
                stream_url = excluded.stream_url
            """
            cursor.executemany(query, to_insert)
            os.remove(os.path.join(integration.getIntegrationDir(), 'radios.json'))

    ## Ratings (Local and Jellyfin)
    if 'ratings' in schema_dict:
        if ratings_dict := integration.open_json('ratings.json'):
            to_insert = [(songId, rating) for songId, rating in ratings_dict.items() if rating > 0]
            query = """
            INSERT INTO ratings (id, rating)
            VALUES (?, ?)
            ON CONFLICT (id) DO UPDATE SET
                rating = excluded.rating
            """
            cursor.executemany(query, to_insert)
            os.remove(os.path.join(integration.getIntegrationDir(), 'ratings.json'))

    ## Scrobble (Local)
    if 'scrobble' in schema_dict:
        if scrobble_dict := integration.open_json('scrobble.json'):
            to_insert = []
            for songId, data in scrobble_dict.items():
                to_insert.append((songId, data.get("plays"), data.get("last_play"), data.get("album", ""), data.get("artist", "")))
            query = """
            INSERT INTO scrobble (id, plays, last_play, album_id, artist_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                plays = excluded.plays,
                last_play = excluded.last_play,
                album_id = excluded.album_id,
                artist_id = excluded.artist_id
            """
            cursor.executemany(query, to_insert)
            os.remove(os.path.join(integration.getIntegrationDir(), 'scrobble.json'))

    conn.commit()
    conn.close()
