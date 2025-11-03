# Render Deployment Checklist

## Pre-Deployment

- [ ] Replace Telegram Bot Token with your own (line 232 in bot.py)
- [ ] Replace GoFile API Token with your own (line 50 in bot.py)
- [ ] Replace YouTube API Key with your own (line 250 in bot.py)
- [ ] Test bot locally first
- [ ] Commit all changes to GitHub

## Deployment Steps

### 1. Create New Web Service on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository

### 2. Configure Service

**Basic Settings:**
- **Name**: musico-telegram-bot
- **Region**: Oregon (US West)
- **Branch**: main
- **Runtime**: Python 3

**Build & Deploy:**
- **Build Command**: 
  ```
  apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
  ```
- **Start Command**: 
  ```
  python bot.py
  ```

**Advanced Settings:**
- **Plan**: Free
- **Environment**: Python 3.11.0
- **Health Check Path**: Leave empty (long-polling bot doesn't need HTTP server)

### 3. Environment Variables (Optional)

If you want to use environment variables instead of hardcoding:

| Key | Value |
|-----|-------|
| TELEGRAM_BOT_TOKEN | Your bot token from @BotFather |
| GOFILE_API_TOKEN | Your GoFile token |
| YOUTUBE_API_KEY | Your YouTube API key |

### 4. Deploy

1. Click "Create Web Service"
2. Wait 3-5 minutes for build to complete
3. Check logs for "Starting Music Telegram Bot..."
4. Test bot in Telegram

## Post-Deployment

### Verify Bot is Running

1. Open Telegram
2. Message your bot: `/start`
3. Send a YouTube URL
4. Check Render logs if issues

### Monitor

- **Logs**: Dashboard → Your Service → Logs
- **Metrics**: Dashboard → Your Service → Metrics
- **Restarts**: Free tier sleeps after 15min inactivity

## Troubleshooting

### Build Fails

**Issue**: FFmpeg installation fails
**Solution**: Check build command has `apt-get install ffmpeg`

**Issue**: Python version mismatch
**Solution**: Set `PYTHON_VERSION=3.11.0` in environment variables

### Bot Not Responding

**Issue**: Bot offline after 15 minutes
**Solution**: Normal for free tier - bot wakes on first message

**Issue**: Telegram "Bot not found"
**Solution**: Check token is correct in bot.py line 232

### Download Failures

**Issue**: "No files were downloaded"
**Solution**: This is now fixed in the updated code (line 1327-1335)

**Issue**: YouTube errors
**Solution**: Update yt-dlp: Add to requirements.txt `yt-dlp>=2024.10.22`

## Maintenance

### Update Dependencies

```bash
# In your local repo
pip list --outdated
pip install --upgrade yt-dlp spotdl
pip freeze > requirements.txt
git commit -am "Update dependencies"
git push
```

Render will auto-deploy on push.

### Check Quotas

- **YouTube API**: [Google Cloud Console](https://console.cloud.google.com/) → Quotas
- **GoFile**: Check your account at gofile.io

### Logs Rotation

Render keeps logs for 7 days on free tier.

## Support

- Render Docs: https://render.com/docs
- Telegram Bot API: https://core.telegram.org/bots/api
- YouTube API: https://developers.google.com/youtube/v3

---

**Ready to deploy? Let's go! 🚀**
