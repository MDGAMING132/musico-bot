#!/bin/bash

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y ffmpeg

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run the bot
echo "Starting Musico Telegram Bot..."
python -u bot.py
