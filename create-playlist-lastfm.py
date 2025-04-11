import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os
import time
import argparse
import json
import re
from pathlib import Path
import hashlib
import random

load_dotenv()

CACHE_DIR = Path('.cache_lastfm')
CACHE_DIR.mkdir(exist_ok=True)

def cache_get(key):
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
    return None

def cache_set(key, data):
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(data))

def sanitize_key(text):
    return re.sub(r'[^a-zA-Z0-9_]+', '_', text.strip().lower())

# === CONFIG ===
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
SPOTIFY_USERNAME = os.getenv('SPOTIFY_USERNAME')
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY')

VIBES = {
    'flow': 'trip hop',
    'park': 'drum and bass',
    'cruise': 'indie electronic',
    'powder': 'lo-fi',
    'sunset': 'ambient'
}

GENRE_TAGS = {
    'flow': ['trip hop', 'downtempo', 'chillout'],
    'park': ['drum and bass', 'breakbeat', 'jungle'],
    'cruise': ['indie electronic', 'indie pop', 'dream pop'],
    'powder': ['lo-fi', 'chillhop', 'instrumental'],
    'sunset': ['ambient', 'post-rock', 'cinematic']
}

SCOPES = 'playlist-read-private playlist-modify-private playlist-modify-public user-library-read'
scope_hash = hashlib.md5(SCOPES.encode()).hexdigest()[:8]
CACHE_PATH = f'.cache-{SPOTIFY_USERNAME}-{scope_hash}'
if os.getenv('DEBUG', 'true').lower() == 'true':
    print(f"[DEBUG] Using cache path: {CACHE_PATH}")

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=SCOPES,
    username=SPOTIFY_USERNAME,
    cache_path=CACHE_PATH
))

# === FETCH FROM LAST.FM ===
def fetch_lastfm_tracks_by_tag(tag, limit=100):
    url = f'https://ws.audioscrobbler.com/2.0/?method=tag.gettoptracks&tag={tag}&limit={limit}&api_key={LASTFM_API_KEY}&format=json'
    response = requests.get(url)
    data = response.json()
    tracks = data.get('tracks', {}).get('track', [])
    return [(track['name'], track['artist']['name']) for track in tracks]

def track_matches_vibe(track_name, artist_name, genre_tags):
    cache_key = f"tags_{sanitize_key(artist_name)}_{sanitize_key(track_name)}"
    data = cache_get(cache_key)
    if not data:
        url = f'http://ws.audioscrobbler.com/2.0/?method=track.gettoptags&artist={artist_name}&track={track_name}&api_key={LASTFM_API_KEY}&format=json'
        response = requests.get(url)
        if response.status_code != 200:
            return False
        data = response.json()
        cache_set(cache_key, data)
    tags = [tag['name'].lower() for tag in data.get('toptags', {}).get('tag', [])]
    if DEBUG_MATCH and any(tag in tags for tag in genre_tags):
        print(f"[DEBUG] ✅ '{track_name}' by {artist_name} matched vibe via genre tags:")
        print(f"[DEBUG] ➤ Track tags: {tags}")
        print(f"[DEBUG] ➤ Matched against: {genre_tags}")
        for tag in tags:
            if tag in genre_tags:
                print(f"[DEBUG]    ✓ {tag}")
    return any(tag in tags for tag in genre_tags)

def get_similar_tracks(track_name, artist_name, limit=5):
    cache_key = f"similar_{sanitize_key(artist_name)}_{sanitize_key(track_name)}"
    data = cache_get(cache_key)
    if not data:
        url = f'http://ws.audioscrobbler.com/2.0/?method=track.getsimilar&artist={artist_name}&track={track_name}&limit={limit}&api_key={LASTFM_API_KEY}&format=json'
        response = requests.get(url)
        if response.status_code != 200:
            return []
        data = response.json()
        cache_set(cache_key, data)
    return [(track['name'], track['artist']['name']) for track in data.get('similartracks', {}).get('track', [])]

# === GET LIKED TRACKS ===
def get_liked_tracks(max_total=200):
    offset = 0
    all_tracks = []
    while len(all_tracks) < max_total:
        response = sp.current_user_saved_tracks(limit=50, offset=offset)
        items = response['items']
        if not items:
            break
        all_tracks.extend(items)
        offset += 50
    if DEBUG:
        print(f"[DEBUG] Retrieved {len(all_tracks)} liked songs")
    return all_tracks

# === SEARCH SPOTIFY ===
def find_spotify_track_id(track_name, artist_name):
    query = f'track:{track_name} artist:{artist_name}'
    results = sp.search(q=query, type='track', limit=1)
    items = results.get('tracks', {}).get('items', [])
    if items:
        return items[0]['id']
    return None

# === CHECK FOR EXISTING PLAYLIST ===
def get_existing_playlist(name):
    total_checked = 0
    offset = 0
    while True:
        response = sp.current_user_playlists(limit=50, offset=offset)
        if DEBUG:
            print(f"[DEBUG] Fetching playlists with offset {offset}")
        playlists = response['items']
        for pl in playlists:
            total_checked += 1
            pl_name = pl['name'].strip().lower()
            target_name = name.strip().lower()
            comparison_result = pl_name == target_name
            if DEBUG:
                print(f"[DEBUG] Checking playlist: '{pl['name']}' == '{name}'? ➜ {comparison_result}")
            if comparison_result:
                if DEBUG:
                    print(f"[DEBUG] ✅ Matched playlist: {pl['name']} (ID: {pl['id']})")
                return pl
        if not response.get('next'):
            break
        offset += 50
    if DEBUG:
        print(f"[DEBUG] Finished checking {total_checked} playlists")
    
    # === FALLBACK: Search API ===
    if DEBUG:
        print(f"[DEBUG] Running fallback search for playlist: {name}")
    search_results = sp.search(q=name, type='playlist', limit=10)
    for result in search_results.get('playlists', {}).get('items', []):
        result_name = result['name'].strip().lower()
        result_owner = result['owner']['id']
        if DEBUG:
            print(f"[DEBUG] Fallback result: '{result['name']}' by {result_owner}")
        if result_name == target_name and result_owner == SPOTIFY_USERNAME:
            if DEBUG:
                print(f"[DEBUG] ✅ Fallback matched playlist: {result['name']} (ID: {result['id']})")
            return result

    return None

# === GET LIKED SONGS' TOP ARTISTS ===
def get_top_artists_from_liked(limit=10):
    artists = {}
    offset = 0
    while True:
        response = sp.current_user_saved_tracks(limit=50, offset=offset)
        items = response['items']
        for item in items:
            for artist in item['track']['artists']:
                artists[artist['id']] = artists.get(artist['id'], 0) + 1
        if response['next'] is None:
            break
        offset += 50
    sorted_artists = sorted(artists.items(), key=lambda x: x[1], reverse=True)
    return [artist_id for artist_id, _ in sorted_artists[:limit]]

# === PIPELINE ===
def build_playlist_from_lastfm_tag(tag, selected_mode, limit=20, existing=None):
    print("🎯 Generating recommendations based on your Liked Songs and vibe tag...")
    genre_tags = GENRE_TAGS.get(selected_mode, [tag])
    liked = get_liked_tracks(max_total=200)
    seed_tracks = []
    for item in liked:
        name = item['track']['name']
        artist = item['track']['artists'][0]['name']
        if track_matches_vibe(name, artist, genre_tags):
            seed_tracks.append((name, artist))
            if DEBUG_MATCH:
                print(f"[DEBUG] ✅ Vibe match found in liked songs: {name} by {artist}")
    print(f"🎯 Found {len(seed_tracks)} vibe-aligned liked tracks")

    matched_ids = []
    for name, artist in seed_tracks[:5]:
        similar = get_similar_tracks(name, artist, limit=5)
        for title, similar_artist in similar:
            track_id = find_spotify_track_id(title, similar_artist)
            if track_id and track_id not in matched_ids:
                print(f"🎧 Similar: {title} by {similar_artist}")
                matched_ids.append(track_id)
            if len(matched_ids) >= limit:
                break
        if len(matched_ids) >= limit:
            break

    if len(matched_ids) < limit:
        print(f"🔄 Adding fallback tracks from Last.fm for tag '{tag}'...")
        lastfm_tracks = fetch_lastfm_tracks_by_tag(tag, limit * 5)
        random.shuffle(lastfm_tracks)
        lastfm_tracks = list(reversed(lastfm_tracks))
        for title, artist in lastfm_tracks:
            if len(matched_ids) >= limit:
                break
            track_id = find_spotify_track_id(title, artist)
            if track_id and track_id not in matched_ids:
                print(f"✨ Fallback: {title} by {artist}")
                matched_ids.append(track_id)
            time.sleep(0.2)

    if not matched_ids:
        print("No tracks found. Playlist not created.")
        return

    if existing:
        print(f"ℹ️ Playlist '{existing['name']}' already exists.")
        existing_track_ids = [item['track']['id'] for item in sp.playlist_items(existing['id'])['items'] if item['track']]
        new_tracks = [tid for tid in matched_ids if tid not in existing_track_ids]
        if not new_tracks:
            print("⚠️ All tracks are already in the playlist. Nothing to add.")
            return
        while True:
            confirm = input(f"Add {len(new_tracks)} new tracks to existing playlist '{existing['name']}'? (y/n): ").lower()
            if confirm in ['y', 'n']:
                break
            print("❗ Please enter 'y' or 'n'.")
        if confirm == 'y':
            sp.playlist_add_items(playlist_id=existing['id'], items=new_tracks)
            print(f"✅ Added {len(new_tracks)} new tracks to playlist '{existing['name']}'")
        else:
            print("❌ Operation canceled.")
        return
    
    # Only reach this if playlist didn't exist
    playlist_name = f"Snowboarding Vibe: {selected_mode.title()}"
    while True:
        confirm = input(f"Create new playlist '{playlist_name}' with {len(matched_ids)} tracks? (y/n): ").lower()
        if confirm in ['y', 'n']:
            break
        print("❗ Please enter 'y' or 'n'.")
    if confirm == 'y':
        playlist = sp.user_playlist_create(user=SPOTIFY_USERNAME, name=playlist_name, public=False)
        sp.playlist_add_items(playlist_id=playlist['id'], items=matched_ids)
        print(f"✅ Created playlist '{playlist_name}' with {len(matched_ids)} tracks!")
    else:
        print("❌ Operation canceled.")

# === RUN ===
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build a Spotify playlist from Last.fm vibe tag.")
    parser.add_argument('--limit', type=int, default=20, help='Number of tracks to fetch (default: 20)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--debug-match', action='store_true', help='Enable detailed match logging')
    args = parser.parse_args()
    DEBUG = args.debug or True
    DEBUG_MATCH = args.debug_match

    print("🎿 Choose a riding mode:")
    for i, mode in enumerate(VIBES.keys(), 1):
        print(f"{i}. {mode.title()} ({VIBES[mode]})")
    
    while True:
        try:
            choice = int(input("Enter your choice: "))
            if 1 <= choice <= len(VIBES):
                break
            else:
                print("❗ Please choose a number from the list above.")
        except ValueError:
            print("❗ Invalid input. Please enter a number.")

    selected_mode = list(VIBES.keys())[choice - 1]
    selected_tag = VIBES[selected_mode]
    
    playlist_name = f"Snowboarding Vibe: {selected_mode.title()}"
    existing = get_existing_playlist(playlist_name)
    if DEBUG:
        print(f"[DEBUG] Playlist lookup for '{playlist_name}': {'FOUND' if existing else 'NOT FOUND'}")

    build_playlist_from_lastfm_tag(selected_tag, selected_mode, args.limit, existing)
