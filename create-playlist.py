import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os
import argparse
from urllib.parse import urlencode

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
genre_filter = [g.strip() for g in args.genre.split(',')] if args.genre else ['pop', 'rock', 'indie']
candidates = []

query_params = [
    ('limit', TRACK_LIMIT),
    ('market', 'US'),
    ('target_tempo', TARGET_BPM)
] + [('seed_genres', genre) for genre in genre_filter]

query_string = urlencode(query_params)
url = f"https://api.spotify.com/v1/recommendations?{query_string}"

print(f"📡 Requesting: {url}")

recommendations = sp._get(url)

for item in recommendations['tracks']:
    print(f"🎵 {item['name']} - {item['artists'][0]['name']}")
    candidates.append(item['id'])

# === CREATE PLAYLIST ===
if not candidates:
    print("❌ No tracks matched the BPM criteria. Playlist not created.")
    exit(1)

print("🎧 Creating playlist...")
playlist = sp.user_playlist_create(user=USERNAME, name=PLAYLIST_NAME, public=False)
sp.playlist_add_items(playlist_id=playlist['id'], items=candidates)
print(f"✅ Playlist '{PLAYLIST_NAME}' created with {len(candidates)} tracks!")
