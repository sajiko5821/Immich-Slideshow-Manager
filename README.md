# Immich Digital Photo Frame Manager

A beautiful, glassmorphism-styled web application to manage slideshow integrations between [Immich](https://immich.app/) and digital photo frames or Home Assistant dashboards.

## Features

- **Multi-Device Support**: Manage different slideshow configurations (e.g., Office, Living Room) from a single web interface.
- **Direct API Downloads**: Photos are fetched directly from your Immich server over the network (no local disk mapping required for the source files!).
- **Smart Image Processing**: Automatically resizes images, adds blurred backgrounds for mismatched aspect ratios, and corrects EXIF orientations.
- **Automated Scheduling**: Runs all your slideshow sync jobs automatically every night at 2:00 AM using `APScheduler`.

## Docker Installation

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  immich_frame_manager:
    build: .
    container_name: immich_frame_manager
    ports:
      - "5050:5050"
    volumes:
      # Persistent config folder
      - ./config:/app/config
      # Map your Home Assistant WWW paths
      - /path/to/homeassistant/www/slideshow/office:/slideshow/office:rw
      - /path/to/homeassistant/www/slideshow/livingroom:/slideshow/livingroom:rw
    restart: unless-stopped
```

2. Run `docker-compose up -d`.
3. Open your browser to `http://<your-server-ip>:5050`.
4. Click **New Configuration** to add a job (e.g., Living Room).
   - Provide the specific Immich Album URL.
   - Provide your API Key.
   - Destination Directory (mapped in Docker) e.g., `/slideshow/livingroom`.

5. Click **Sync Now** to process immediately, or let the background scheduler handle it every night at 2:00 AM!

## Running Locally (Mac/Linux)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
PORT=5050 python app.py
```
Open `http://localhost:5050` in your browser.
