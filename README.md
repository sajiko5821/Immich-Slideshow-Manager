<p align="center">
  <img src="static/favicon.svg" width="200" />
</p>

<h1 align="center">Immich Slideshow Manager</h1>

[![Docker Image Version](https://img.shields.io/github/v/tag/sajiko5821/Immich-Digital-Photo-Frame?label=version&logo=docker&color=2496ED)](https://github.com/sajiko5821/Immich-Digital-Photo-Frame/pkgs/container/immich-digital-photo-frame)
[![Build Status](https://img.shields.io/github/actions/workflow/status/sajiko5821/Immich-Digital-Photo-Frame/docker-publish.yml?branch=main&label=build&logo=github)](https://github.com/sajiko5821/Immich-Digital-Photo-Frame/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Automates the fetching and management of images from an Immich album to serve them locally as a beautiful slideshow. Perfect for digital photo frames (or Home Assistant dashboards) where you want a locally cached, offline-tolerant, and lightweight viewer.

## Features

- 🖼️ Syncs photos seamlessly from a specific Immich album
- 🗂️ Saves configuration directly to a persistent data directory
- 🐳 Docker support with standard Unraid appdata mapping
- ⏱️ Fully configurable scheduled sync jobs via a web UI
- ✨ Modern, responsive web interface

## Quick Start with Docker

### Prerequisites

- Docker & Docker Compose
- An Immich Server running
- Your Immich API Key

### 1. Get your Immich API Key

Find your API Key in Immich by navigating to **Account Settings > API Keys** and generating a new key.

> [!IMPORTANT]
> Ensure that the generated API Key has at least **Album (Read)** and **Asset (Download)** permissions so that it can fetch the photos for your slideshow.

### 2. Edit `docker-compose.yml`

Update the ports or volume mappings as needed:

```yaml
version: '3.8'

services:
  immich_slideshow_manager:
    build: .
    container_name: immich_slideshow_manager
    # Optional: Set your Immich API Key securely via environment variables
    # environment:
    #   - IMMICH_API_KEY=your_api_key_here
    ports:
      - "5050:5050"
    volumes:
      # Map the Unraid appdata folder to store configuration
      - /mnt/user/appdata/immich-slideshow-manager:/app/data
      # Map your local paths for the slideshow destinations
      - /mnt/user/appdata/homeassistant/www/slideshow/office:/slideshow/office:rw
      - /mnt/user/appdata/homeassistant/www/slideshow/livingroom:/slideshow/livingroom:rw
    restart: unless-stopped
```

### 3. Start the container

```bash
docker-compose up -d
docker-compose logs -f immich_slideshow_manager
```

### 4. Configure via Web UI

Navigate to `http://YOUR_SERVER_IP:5050` in your browser. From here, you can:
- Input your Immich URL and API Key
- Provide the Album ID you want to sync
- Specify the destination folder path (mapped in docker-compose)
- Add a scheduled job by specifying a specific time (e.g., `03:00` for 3 AM daily)

## Local Development

### Requirements

- Python 3.11+

### Installation

```bash
# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
# Start the Flask development server
python app.py
```

## Troubleshooting

### Config not saving
Ensure the `/app/data` directory mapping is correctly bound to a persistent folder on your host machine, and that Docker has write permissions to that directory.

### Sync failing
Check the Flask server logs or Docker logs. Ensure that your Immich URL includes `http://` or `https://` and does not end with a trailing slash, and that the API key has album read permissions.

## License

MIT
