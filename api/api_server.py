#!/usr/bin/env python3
"""
UnseenStream API Server v0.1
Serves random videos from the pool with 1-second rotation.
Designed to run on Render.com free tier.
"""

import os
import json
import random
import threading
import time
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

# Configure advanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Disable Flask's default request logging (we'll do it manually)
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

# Configuration
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'bitm4ncer/UnseenStream')
POOL_REFRESH_MINUTES = int(os.environ.get('POOL_REFRESH_MINUTES', 60))
GITHUB_RAW_URL = f'https://raw.githubusercontent.com/{GITHUB_REPO}/main/videos_pool.json'

# Global state
current_video = None
video_pool = []
pool_last_updated = None
videos_served = 0
server_started = datetime.utcnow()


def fetch_video_pool():
    """Fetch the video pool from GitHub"""
    global video_pool, pool_last_updated

    try:
        logger.info(f"Fetching video pool from {GITHUB_RAW_URL}")
        response = requests.get(GITHUB_RAW_URL, timeout=10)
        response.raise_for_status()

        data = response.json()
        video_pool = data.get('videos', [])
        pool_last_updated = datetime.utcnow()

        logger.info(f"Successfully loaded {len(video_pool)} videos from pool")
        return True
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching video pool (>10s)")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching video pool: {e}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in video pool: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error fetching video pool: {e}", exc_info=True)
        return False


def video_rotator():
    """
    Background thread that picks a random video every second.
    This is the core of the "1 video per second" rotation system.
    """
    global current_video, videos_served

    logger.info("Video rotator thread started")
    last_pool_refresh = time.time()
    rotation_count = 0

    while True:
        try:
            # Refresh pool periodically
            if time.time() - last_pool_refresh > (POOL_REFRESH_MINUTES * 60):
                logger.info("Refreshing video pool (scheduled refresh)")
                fetch_video_pool()
                last_pool_refresh = time.time()

            # Pick random video if pool is available
            if video_pool:
                current_video = random.choice(video_pool)
                videos_served += 1
                rotation_count += 1

                # Log every 100 rotations
                if rotation_count % 100 == 0:
                    logger.info(f"Rotated {rotation_count} videos | Pool size: {len(video_pool)} | Total served: {videos_served}")
            else:
                logger.warning("Video pool is empty")
                current_video = {
                    'error': 'No videos in pool',
                    'message': 'Video pool is empty. GitHub Actions may be building it.'
                }

            # Wait 1 second before next rotation
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error in video rotator: {e}", exc_info=True)
            time.sleep(1)


@app.route('/health')
def health():
    """Health check endpoint for Render.com and keepalive pings"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    logger.debug(f"Health check from {client_ip}")

    return jsonify({
        'status': 'healthy',
        'pool_size': len(video_pool),
        'uptime_seconds': (datetime.utcnow() - server_started).total_seconds()
    })


@app.route('/current-video')
def get_current_video():
    """Get the current random video (changes every second)"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if current_video is None:
        logger.warning(f"Video request from {client_ip} - service not ready")
        return jsonify({
            'error': 'Service starting',
            'message': 'Video pool is loading, please try again in a few seconds'
        }), 503

    logger.debug(f"Served video to {client_ip}: {current_video.get('title', 'Unknown')[:50]}")
    return jsonify(current_video)


@app.route('/stats')
def get_stats():
    """Get statistics about the video pool and server"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    logger.info(f"Stats request from {client_ip}")

    return jsonify({
        'pool_size': len(video_pool),
        'pool_last_updated': pool_last_updated.isoformat() + 'Z' if pool_last_updated else None,
        'videos_served': videos_served,
        'server_started': server_started.isoformat() + 'Z',
        'uptime_seconds': (datetime.utcnow() - server_started).total_seconds(),
        'github_repo': GITHUB_REPO
    })


@app.route('/')
def index():
    """Root endpoint with API documentation"""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    logger.info(f"API root accessed from {client_ip}")

    return jsonify({
        'name': 'UnseenStream API',
        'version': '0.1.0',
        'endpoints': {
            '/current-video': 'Get current random video (rotates every second)',
            '/stats': 'Get pool statistics',
            '/health': 'Health check'
        },
        'pool_size': len(video_pool),
        'status': 'running'
    })


def main():
    """Initialize and start the server"""
    logger.info("="*60)
    logger.info("UnseenStream API Server v0.1")
    logger.info(f"Started at: {datetime.utcnow().isoformat()}")
    logger.info(f"GitHub Repo: {GITHUB_REPO}")
    logger.info(f"Pool Refresh: Every {POOL_REFRESH_MINUTES} minutes")
    logger.info("="*60)

    # Initial pool fetch
    logger.info("Initializing video pool...")
    if not fetch_video_pool():
        logger.warning("Could not fetch initial pool. Will retry in background.")
        # Create a minimal pool to prevent errors
        global video_pool
        video_pool = [{
            'id': 'dQw4w9WgXcQ',
            'title': 'Loading...',
            'channelTitle': 'UnseenStream',
            'thumbnail': 'https://via.placeholder.com/320x180',
            'viewCount': 0,
            'publishedAt': datetime.utcnow().isoformat() + 'Z'
        }]

    # Start video rotator in background thread
    rotator_thread = threading.Thread(target=video_rotator, daemon=True)
    rotator_thread.start()

    # Start Flask server
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Server starting on port {port}")
    logger.info("Video rotator running (1 video/second)")
    logger.info("="*60)

    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
