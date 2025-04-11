import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os
import time

load_dotenv()

# === CONFIG ===
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
SPOTIFY_USERNAME = os.getenv('SPOTIFY_USERNAME')
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY')

TAG = 'chillhop'
TRACK_LIMIT = 20

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope='playlist-modify-private playlist-modify-public',
    username=SPOTIFY_USERNAME,
    cache_path=f'.cache-{SPOTIFY_USERNAME}'
))

# === FETCH FROM LAST.FM ===
def fetch_lastfm_tracks_by_tag(tag, limit=20):
    url = f'https://ws.audioscrobbler.com/2.0/?method=tag.gettoptracks&tag={tag}&limit={limit}&api_key={LASTFM_API_KEY}&format=json'
    response = requests.get(url)
    data = response.json()
    tracks = data.get('tracks', {}).get('track', [])
    return [(track['name'], track['artist']['name']) for track in tracks]

# === SEARCH SPOTIFY ===
def find_spotify_track_id(track_name, artist_name):
    query = f'track:{track_name} artist:{artist_name}'
    results = sp.search(q=query, type='track', limit=1)
    items = results.get('tracks', {}).get('items', [])
    if items:
        return items[0]['id']
    return None

# === PIPELINE ===
def build_playlist_from_lastfm_tag(tag, limit=20):
    print(f"🔍 Searching Last.fm for top tracks tagged '{tag}'...")
    lastfm_tracks = fetch_lastfm_tracks_by_tag(tag, limit)
    print(f"🎯 Found {len(lastfm_tracks)} candidates from Last.fm")

    matched_ids = []
    for title, artist in lastfm_tracks:
        track_id = find_spotify_track_id(title, artist)
        if track_id:
            print(f"✅ Matched: {title} by {artist}")
            matched_ids.append(track_id)
        else:
            print(f"❌ No match: {title} by {artist}")
        time.sleep(0.2)  # avoid rate limits

    if not matched_ids:
        print("No matches found. Playlist not created.")
        return

    playlist_name = f"Snowboarding Vibe: {tag.title()}"
    playlist = sp.user_playlist_create(user=SPOTIFY_USERNAME, name=playlist_name, public=False)
    sp.playlist_add_items(playlist_id=playlist['id'], items=matched_ids)
    print(f"✅ Created playlist '{playlist_name}' with {len(matched_ids)} tracks!")

# === RUN IT ===
if __name__ == '__main__':
    build_playlist_from_lastfm_tag(TAG, TRACK_LIMIT)
