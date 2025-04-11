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
        if not result or not result.get('name') or not result.get('owner'):
            continue
        result_name = result['name'].strip().lower()
        result_owner = result['owner'].get('id', '')
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
def build_playlist_from_lastfm_tag(tag, selected_mode, limit=20, existing=None, skiplist=None):
    print("🎯 Generating recommendations based on your Liked Songs and vibe tag...")
    genre_tags = GENRE_TAGS.get(selected_mode, [tag])
    liked = get_liked_tracks(max_total=200)
    matched_ids = []
    matched_pairs = []
    
    skip_ids = set()
    if skiplist:
        skip_tracks = sp.playlist_items(skiplist['id'])['items']
        skip_ids = {item['track']['id'] for item in skip_tracks if item['track']}
        if DEBUG:
            print(f"[DEBUG] Loaded {len(skip_ids)} track(s) from skiplist")
    artist_skiplist_name = f"Snowboarding Vibe: {selected_mode.title()} ⛔ Artist Skips"
    artist_skiplist = get_existing_playlist(artist_skiplist_name)
    skip_artist_ids = set()
    if artist_skiplist:
        artist_skip_tracks = sp.playlist_items(artist_skiplist['id'])['items']
        for item in artist_skip_tracks:
            if item['track']:
                for artist in item['track']['artists']:
                    skip_artist_ids.add(artist['id'])
        print(f"🚫 Found {len(skip_artist_ids)} skipped artist(s)")

    for item in liked:
        name = item['track']['name']
        artist = item['track']['artists'][0]['name']
        if track_matches_vibe(name, artist, genre_tags):
            track_id = find_spotify_track_id(name, artist)
            if track_id and track_id not in matched_ids:
                matched_ids.append(track_id)
                matched_pairs.append((name, artist))
                if DEBUG_MATCH:
                    print(f"[DEBUG] ✅ Vibe match found in liked songs: {name} by {artist}")
    print(f"🎯 Found {len(matched_ids)} vibe-aligned liked tracks")

    seed_tracks = matched_ids[:]
    for name, artist in matched_pairs[:5]:
        similar = get_similar_tracks(name, artist, limit=5)
        for title, similar_artist in similar:
            track_id = find_spotify_track_id(title, similar_artist)
            if track_id:
                if track_id in skip_ids:
                        print(f"🚫 Skipped (in skiplist): {title} by {similar_artist}")
                elif any(artist['id'] in skip_artist_ids for artist in sp.track(track_id)['artists']):
                        print(f"🚫 Skipped (artist blocked): {title} by {similar_artist}")
                elif track_id not in matched_ids:
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
            if track_id:
                if track_id in skip_ids:
                        print(f"🚫 Skipped (in skiplist): {title} by {artist}")
                elif any(artist_data['id'] in skip_artist_ids for artist_data in sp.track(track_id)['artists']):
                        print(f"🚫 Skipped (artist blocked): {title} by {artist}")
                elif track_id not in matched_ids:
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
            print(f"✅ Added {len(new_tracks)} new track{'s' if len(new_tracks) != 1 else ''} to playlist '{existing['name']}'")
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
        print(f"✅ Created playlist '{playlist_name}' with {len(matched_ids)} track{'s' if len(matched_ids) != 1 else ''}!")
    else:
        print("❌ Operation canceled.")

def run_management_mode(selected_mode, playlist_name, skiplist_name):
    while True:
        print(f"\n🎛️  Vibe Playlist Manager — '{selected_mode.title()}'")
        print("1. View current playlist")
        print("2. Select tracks to skip")
        print("3. View ⛔ Skips list")
        print("4. Unskip a track")
        print("5. View ⛔ Artist Skiplist")
        print("6. Unskip an artist")
        print("7. Exit")
        choice = input("Choose an action: ")
        # === Option 1: View current playlist ===
        if choice == '1':
            pl = get_existing_playlist(playlist_name)
            if pl:
                items = sp.playlist_items(pl['id'])['items']
                print(f"\n🎵 {len(items)} tracks in '{pl['name']}':")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item['track']['name']} by {item['track']['artists'][0]['name']}")
            else:
                print("⚠️ Playlist not found.")
        # === Option 2: Select tracks to skip ===
        elif choice == '2':
            pl = get_existing_playlist(playlist_name)
            skiplist = get_existing_playlist(skiplist_name)
            if not skiplist:
                skiplist = sp.user_playlist_create(user=SPOTIFY_USERNAME, name=skiplist_name, public=False)
                print(f"✅ Created skiplist '{skiplist_name}'")
            if pl:
                items = sp.playlist_items(pl['id'])['items']
                print("\nSelect tracks to skip (comma-separated numbers):")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item['track']['name']} by {item['track']['artists'][0]['name']}")
                indices = input("Tracks to skip: ")
                try:
                    selected = [int(i.strip()) - 1 for i in indices.split(',')]
                    tracks_to_skip = [items[i]['track']['id'] for i in selected if 0 <= i < len(items)]
                    if tracks_to_skip:
                        print("❓ Skip just these track(s) or all songs by these artist(s)?")
                        print("1. Just these track(s)")
                        print("2. All tracks by these artist(s)")
                        scope_choice = input("Enter choice (1 or 2): ")
                        if scope_choice == '2':
                            artist_skiplist_name = f"{playlist_name} ⛔ Artist Skips"
                            artist_skiplist = get_existing_playlist(artist_skiplist_name)
                            if not artist_skiplist:
                                artist_skiplist = sp.user_playlist_create(user=SPOTIFY_USERNAME, name=artist_skiplist_name, public=False)
                                print(f"✅ Created artist skiplist '{artist_skiplist_name}'")
                            artist_track_ids = []
                            for i in selected:
                                if 0 <= i < len(items):
                                    artist_track_ids.append(items[i]['track']['id'])
                            sp.playlist_add_items(artist_skiplist['id'], artist_track_ids)
                            print(f"✅ Added {len(artist_track_ids)} artist sample track{'s' if len(artist_track_ids) != 1 else ''} to artist skiplist.")
                            sp.playlist_remove_all_occurrences_of_items(pl['id'], artist_track_ids)
                            print(f"🗑️ Removed {len(artist_track_ids)} track{'s' if len(artist_track_ids) != 1 else ''} from '{playlist_name}'")
                            continue  # Skip the track-level skip logic
                        else:
                            sp.playlist_add_items(skiplist['id'], tracks_to_skip)
                            print(f"✅ Added {len(tracks_to_skip)} track{'s' if len(tracks_to_skip) != 1 else ''} to skiplist.")
                            sp.playlist_remove_all_occurrences_of_items(pl['id'], tracks_to_skip)
                            print(f"🗑️ Removed {len(tracks_to_skip)} track{'s' if len(tracks_to_skip) != 1 else ''} from '{playlist_name}'")
                except ValueError:
                    print("❗ Invalid input.")
            else:
                print("⚠️ Playlist not found.")
        # === Option 3: View skiplist contents ===
        elif choice == '3':
            skiplist = get_existing_playlist(skiplist_name)
            if skiplist:
                items = sp.playlist_items(skiplist['id'])['items']
                print(f"\n⛔ {len(items)} tracks in skiplist '{skiplist_name}':")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item['track']['name']} by {item['track']['artists'][0]['name']}")
            else:
                print("⚠️ Skiplist not found.")
        # === Option 4: Unskip a track ===
        elif choice == '4':
            skiplist = get_existing_playlist(skiplist_name)
            if skiplist:
                items = sp.playlist_items(skiplist['id'])['items']
                print("\nSelect tracks to unskip (comma-separated numbers):")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item['track']['name']} by {item['track']['artists'][0]['name']}")
                indices = input("Tracks to remove: ")
                try:
                    selected = [int(i.strip()) - 1 for i in indices.split(',')]
                    tracks_to_remove = [items[i]['track']['uri'] for i in selected if 0 <= i < len(items)]
                    if tracks_to_remove:
                        sp.playlist_remove_all_occurrences_of_items(skiplist['id'], tracks_to_remove)
                        print(f"✅ Removed {len(tracks_to_remove)} track{'s' if len(tracks_to_remove) != 1 else ''} from skiplist.")
                        sp.playlist_add_items(pl['id'], tracks_to_remove)
                        print(f"🎵 Restored {len(tracks_to_remove)} track{'s' if len(tracks_to_remove) != 1 else ''} to playlist '{playlist_name}'")
                except ValueError:
                    print("❗ Invalid input.")
            else:
                print("⚠️ Skiplist not found.")
        # === Option 5: View artist skiplist ===
        elif choice == '5':
            artist_skiplist_name = f"{playlist_name} ⛔ Artist Skips"
            artist_skiplist = get_existing_playlist(artist_skiplist_name)
            if artist_skiplist:
                items = sp.playlist_items(artist_skiplist['id'])['items']
                print(f"\n⛔ {len(items)} artist sample track{'s' if len(items) != 1 else ''} in artist skiplist '{artist_skiplist_name}':")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item['track']['name']} by {item['track']['artists'][0]['name']}")
            else:
                print("⚠️ Artist skiplist not found.")
        # === Option 6: Unskip an artist ===
        elif choice == '6':
            artist_skiplist_name = f"{playlist_name} ⛔ Artist Skips"
            artist_skiplist = get_existing_playlist(artist_skiplist_name)
            if artist_skiplist:
                items = sp.playlist_items(artist_skiplist['id'])['items']
                print("\nSelect artist sample tracks to remove (comma-separated numbers):")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item['track']['name']} by {item['track']['artists'][0]['name']}")
                indices = input("Tracks to remove: ")
                try:
                    selected = [int(i.strip()) - 1 for i in indices.split(',')]
                    tracks_to_remove = [items[i]['track']['uri'] for i in selected if 0 <= i < len(items)]
                    if tracks_to_remove:
                        sp.playlist_remove_all_occurrences_of_items(artist_skiplist['id'], tracks_to_remove)
                        print(f"✅ Removed {len(tracks_to_remove)} artist sample track{'s' if len(tracks_to_remove) != 1 else ''} from artist skiplist.")
                except ValueError:
                    print("❗ Invalid input.")
            else:
                print("⚠️ Artist skiplist not found.")
        # === Option 7: Exit management mode ===
        elif choice == '7':
            print("👋 Exiting management mode.")
            exit(0)
        else:
            print("❗ Invalid option. Please try again.")

# === RUN ===
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build a Spotify playlist from Last.fm vibe tag.")
    parser.add_argument('--limit', type=int, default=20, help='Number of tracks to fetch (default: 20)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--debug-match', action='store_true', help='Enable detailed match logging')
    parser.add_argument('--manage', action='store_true', help='Enter playlist management mode for the selected vibe')
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
    skiplist_name = f"{playlist_name} ⛔ Skips"
    skiplist = get_existing_playlist(skiplist_name)
    if DEBUG:
        print(f"[DEBUG] Skiplist lookup for '{skiplist_name}': {'FOUND' if skiplist else 'NOT FOUND'}")
    
    existing = get_existing_playlist(playlist_name)
    if DEBUG:
        print(f"[DEBUG] Playlist lookup for '{playlist_name}': {'FOUND' if existing else 'NOT FOUND'}")

    if args.manage:
        run_management_mode(selected_mode, playlist_name, skiplist_name)

    build_playlist_from_lastfm_tag(selected_tag, selected_mode, args.limit, existing, skiplist)
