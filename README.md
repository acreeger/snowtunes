# 🎿 Tunes for Snowboarding

A vibe-based playlist generator built for snowboarding sessions. It crafts personalized Spotify playlists using your liked songs, current mood, and fallback genre data from Last.fm.

## 🧠 How It Works

1. **Select a Snowboarding Vibe**
   - Flow (trip hop)
   - Park (drum and bass)
   - Cruise (indie electronic)
   - Powder (lo-fi)
   - Sunset (ambient)

2. **Recommendation Sources**
   - Your liked songs (matched by genre tags)
   - Similar tracks via Last.fm
   - Genre-tag-based fallbacks if needed

3. **Track Filtering**
   - Skips tracks you've blocked
   - Blocks songs by skipped artists
   - Avoids duplicates already in the playlist

4. **Smart Playlists**
   - Automatically creates one playlist per vibe
   - Reuse the playlist to build on it in future runs
   - Maintains a hidden "skiplist" per vibe to remember skips

## 🛠 Management Mode

Run with `--manage` to:
- View your current vibe playlist
- Skip or unskip individual tracks
- Skip or unskip entire artists
- View what's in your skiplists

## ⚙️ Setup

1. Clone the repo
2. Create a `.env` file using the included `.env.sample`
3. Install dependencies

```bash
pip install -r requirements.txt
```

## 🎵 Powered by:
- [Spotify Web API](https://developer.spotify.com/documentation/web-api/)
- [Last.fm API](https://www.last.fm/api)

## 🧪 Example Usage

```bash
python create-playlist-lastfm.py
```

```bash
python create-playlist-lastfm.py --manage
```

---

Built for personal rhythm and perfect turns on the mountain. ❄️⛷️🏂🎧
