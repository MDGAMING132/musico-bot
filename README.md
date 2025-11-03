# Musico Telegram Bot - Render Deployment

A powerful Telegram bot for downloading music and videos from Spotify and YouTube with cloud upload support.

## 🚀 Features

- **Spotify Downloads**: Tracks, albums, playlists, and artists
- **YouTube Downloads**: 
  - Audio formats: MP3 (320kbps), FLAC (lossless)
  - Video formats: Multiple resolutions (144p to 4K)
- **YouTube API v3 Integration**: Rich metadata display (title, channel, views, duration)
- **Smart File Handling**: 
  - Direct send for small files (<50MB)
  - Cloud upload for large files and playlists
- **Live Progress Tracking**: Real-time download and upload progress
- **Password-Protected ZIPs**: Secure file compression
- **Unicode Filename Support**: Handles all languages and special characters

## 🔧 Fixed Issues

- ✅ Fixed file detection for YouTube video downloads (1080p, 720p, etc.)
- ✅ Added YouTube Data API v3 for rich metadata
- ✅ Improved Unicode filename handling
- ✅ Enhanced error messages and logging

## 📦 Dependencies

- Python 3.11+
- FFmpeg
- yt-dlp (latest version)
- spotdl
- aiohttp
- pyzipper

## 🌐 Deploy on Render

### Option 1: Using render.yaml (Recommended)

1. Fork/clone this repository
2. Connect your GitHub repo to Render
3. Render will automatically detect `render.yaml`
4. Click "Apply" to deploy

### Option 2: Manual Setup

1. Create a new **Web Service** on Render
2. Connect your repository
3. Set the following:
   - **Environment**: Python 3
   - **Build Command**: 
     ```bash
     apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
     ```
   - **Start Command**: 
     ```bash
     python bot.py
     ```

### Option 3: Using Dockerfile

1. Render will auto-detect the `Dockerfile`
2. No additional configuration needed

## 🔐 Configuration

The bot is pre-configured with API keys and tokens. For production:

1. **Telegram Bot Token**: Replace in `bot.py` line 232
2. **GoFile API Token**: Replace in `bot.py` line 50
3. **YouTube API Key**: Replace in `bot.py` line 250

**Environment Variables** (optional, for security):
```bash
TELEGRAM_BOT_TOKEN=your_telegram_token
GOFILE_API_TOKEN=your_gofile_token
YOUTUBE_API_KEY=your_youtube_api_key
```

## 📱 Usage

1. Start the bot: `/start`
2. Send a Spotify or YouTube URL
3. For YouTube:
   - Choose Audio (MP3/FLAC) or Video (MP4)
   - Select quality/resolution
4. Wait for download and receive:
   - Small files: Direct Telegram message
   - Large files/playlists: Cloud download link with ZIP password

## 🛠️ Local Development

```bash
# Clone the repository
git clone <your-repo-url>
cd musico_bot_render

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg
# Windows: Download from https://ffmpeg.org/download.html
# Mac: brew install ffmpeg
# Linux: sudo apt-get install ffmpeg

# Run the bot
python bot.py
```

## 📊 System Requirements (Render Free Tier)

- **RAM**: 512MB (sufficient for bot operation)
- **Storage**: Temporary files are auto-cleaned
- **Build Time**: ~3-5 minutes
- **Cold Start**: ~15-30 seconds

## 🐛 Troubleshooting

### Bot not responding
- Check Render logs for errors
- Verify Telegram token is correct
- Ensure FFmpeg installed successfully

### Download failures
- YouTube: yt-dlp may need update (`pip install --upgrade yt-dlp`)
- Spotify: Check SpotDL logs for API issues

### File detection issues
- Fixed in this version (line 1327-1335 in bot.py)
- Logs will show all files found in download directory

## 📝 API Keys

### YouTube Data API v3
- **Current Key**: AIzaSyAnHq_a1HOrRanQAfTbXZww9Jo3ztM7tF8
- **Quota**: 10,000 units/day
- **Get yours**: [Google Cloud Console](https://console.cloud.google.com/)

### GoFile API
- **Current Token**: 9k87oUoh6ljjoTv6VblzLABCD8t07SIL
- **Storage**: Unlimited
- **Get yours**: [GoFile.io](https://gofile.io/api)

## 📄 License

MIT License - Feel free to use and modify

## 🤝 Contributing

Pull requests welcome! Please test locally before submitting.

## 🔗 Links

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [YouTube Data API](https://developers.google.com/youtube/v3)
- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)
- [SpotDL Documentation](https://github.com/spotDL/spotify-downloader)

## ⚠️ Disclaimer

This bot is for educational purposes. Ensure you comply with:
- Spotify Terms of Service
- YouTube Terms of Service
- Copyright laws in your jurisdiction
- Telegram Bot Guidelines

---

**Made with ❤️ for music lovers**
