import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os
import time
import argparse

load_dotenv()

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

# === CHECK FOR EXISTING PLAYLIST ===
def get_existing_playlist(name):
    offset = 0
    while True:
        response = sp.current_user_playlists(limit=50, offset=offset)
        playlists = response['items']
        for pl in playlists:
            if pl['name'].lower() == name.lower():
                return pl
        if response['next'] is None:
            break
        offset += 50
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
    existing = get_existing_playlist(playlist_name)

    if existing:
        print(f"ℹ️ Playlist '{playlist_name}' already exists.")
        existing_track_ids = [item['track']['id'] for item in sp.playlist_items(existing['id'])['items'] if item['track']]
        new_tracks = [tid for tid in matched_ids if tid not in existing_track_ids]
        if not new_tracks:
            print("⚠️ All tracks are already in the playlist. Nothing to add.")
            return
        while True:
            confirm = input(f"Add {len(new_tracks)} new tracks to existing playlist '{playlist_name}'? (y/n): ").lower()
            if confirm in ['y', 'n']:
                break
            print("❗ Please enter 'y' or 'n'.")
        if confirm == 'y':
            sp.playlist_add_items(playlist_id=existing['id'], items=new_tracks)
            print(f"✅ Added {len(new_tracks)} new tracks to playlist '{playlist_name}'")
        else:
            print("❌ Operation canceled.")
    else:
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
    args = parser.parse_args()

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

    build_playlist_from_lastfm_tag(selected_tag, args.limit)
