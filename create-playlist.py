import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os
import argparse

load_dotenv()

# === CONFIGURATION ===
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
USERNAME = None  # Initialize USERNAME

# Argument parser
parser = argparse.ArgumentParser(description="Generate a Spotify playlist by BPM and genre.")
parser.add_argument('--genre', type=str, help='Genre to filter by (e.g. "hip-hop", "indie")', default=None)
parser.add_argument('--years', type=str, help='Year range (e.g. "2015-2023")', default='1995-2025')
parser.add_argument('--limit', type=int, help='Max number of tracks', default=50)
parser.add_argument('--bpm', type=int, help='Target BPM for track filtering', default=90)
parser.add_argument('--username', type=str, help='Spotify username (overrides .env)', default=os.getenv('SPOTIFY_USERNAME'))
args = parser.parse_args()

USERNAME = args.username  # Update USERNAME with args.username

# Scope for playlist creation
SCOPE = 'playlist-modify-public playlist-modify-private'

# Playlist settings
TARGET_BPM = args.bpm
BPM_TOLERANCE = 2
TRACK_LIMIT = args.limit
PLAYLIST_NAME = f"Snowboard Flow {TARGET_BPM} BPM" + (f" - {args.genre.title()}" if args.genre else "")

# === AUTHENTICATION ===
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=SCOPE,
    username=USERNAME,
    cache_path=f'.cache-{USERNAME}'
))

token_info = sp.auth_manager.get_cached_token()
print("🛂 Scopes granted:", token_info.get('scope'))

# === FETCH & FILTER TRACKS ===
print("🔍 Searching for tracks...")
genre_filter = args.genre
year_range = args.years
query = f'genre:\"{genre_filter}\" year:{year_range}' if genre_filter else f'year:{year_range}'
results = sp.search(q=query, type='track', limit=50, market='US')
print(f"🔍 Found {len(results['tracks']['items'])} tracks matching the criteria.")
candidates = []

for item in results['tracks']['items']:
    track_id = item['id']
    try:
        audio = sp.gi(track_id)[0]
        if audio and TARGET_BPM - BPM_TOLERANCE <= audio['tempo'] <= TARGET_BPM + BPM_TOLERANCE:
            print(f"🎵 {item['name']} - {item['artists'][0]['name']} ({round(audio['tempo'])} BPM)")
            candidates.append(track_id)
            if len(candidates) >= TRACK_LIMIT:
                break
    except spotipy.exceptions.SpotifyException as e:
        print(f"⚠️  Skipping track '{item['name']}' due to API error: {e}")

# === CREATE PLAYLIST ===
if not candidates:
    print("❌ No tracks matched the BPM criteria. Playlist not created.")
    exit(1)

print("🎧 Creating playlist...")
playlist = sp.user_playlist_create(user=USERNAME, name=PLAYLIST_NAME, public=False)
sp.playlist_add_items(playlist_id=playlist['id'], items=candidates)
print(f"✅ Playlist '{PLAYLIST_NAME}' created with {len(candidates)} tracks!")
