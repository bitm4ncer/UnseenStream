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
rotator_started = False


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


def select_weighted_video(pool, excluded_ids=None):
    """
    Select a video with weighted randomness based on view count.
    Videos with fewer views have higher probability of being selected.
    0 views = highest weight, 100 views = lowest weight.

    Args:
        pool: List of video objects
        excluded_ids: Set of video IDs to exclude (already viewed)

    Returns:
        Selected video object or None
    """
    if not pool:
        return None

    # Filter out excluded videos
    if excluded_ids:
        available_pool = [v for v in pool if v.get('id') not in excluded_ids]
        if not available_pool:
            # All videos viewed, reset and use full pool
            available_pool = pool
    else:
        available_pool = pool

    # Calculate weights: (101 - viewCount) so 0 views = weight 101, 100 views = weight 1
    weights = []
    for video in available_pool:
        view_count = video.get('viewCount', 0)
        weight = 101 - min(view_count, 100)  # Ensure weight is always positive
        weights.append(weight)

    # Use random.choices() for weighted selection
    selected = random.choices(available_pool, weights=weights, k=1)[0]
    return selected


def video_rotator():
    """
    Background thread that picks a weighted random video every second.
    Videos with lower view counts are more likely to be selected.
    This is the core of the "1 video per second" rotation system.
    """
    global current_video, videos_served

    logger.info("Video rotator thread started with weighted selection")
    last_pool_refresh = time.time()
    rotation_count = 0

    while True:
        try:
            # Refresh pool periodically
            if time.time() - last_pool_refresh > (POOL_REFRESH_MINUTES * 60):
                logger.info("Refreshing video pool (scheduled refresh)")
                fetch_video_pool()
                last_pool_refresh = time.time()

            # Pick weighted random video if pool is available
            if video_pool:
                current_video = select_weighted_video(video_pool)
                videos_served += 1
                rotation_count += 1

                # Log each rotation with video details
                logger.info(f"[Rotation #{rotation_count}] Selected: '{current_video.get('title', 'Unknown')[:60]}' (ID: {current_video.get('id', 'N/A')}, Views: {current_video.get('viewCount', 'N/A')})")

                # Summary log every 100 rotations
                if rotation_count % 100 == 0:
                    logger.info(f"=== Summary: {rotation_count} rotations | Pool size: {len(video_pool)} | Total served: {videos_served} ===")
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


def ensure_rotator_started():
    """Ensure video rotator is running (for Gunicorn compatibility)"""
    global rotator_started
    if not rotator_started:
        logger.info("="*60)
        logger.info("UnseenStream API Server v0.1")
        logger.info(f"GitHub Repo: {GITHUB_REPO}")
        logger.info(f"Pool refresh interval: {POOL_REFRESH_MINUTES} minutes")
        logger.info("="*60)

        # Initial pool fetch
        logger.info("Initializing video pool...")
        fetch_video_pool()

        # Start video rotator in background thread
        rotator_thread = threading.Thread(target=video_rotator, daemon=True)
        rotator_thread.start()
        logger.info("Video rotator started (1 video/second)")

        rotator_started = True


@app.before_request
def before_request():
    """Initialize rotator on first request (Gunicorn compatibility)"""
    ensure_rotator_started()


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


@app.route('/current-video', methods=['GET', 'POST'])
def get_current_video():
    """
    Get a weighted random video from the pool.
    POST method allows sending excluded video IDs to prevent duplicates.

    POST body (optional):
    {
        "excluded_ids": ["video_id_1", "video_id_2", ...]
    }
    """
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not video_pool:
        logger.warning(f"Video request from {client_ip} - pool empty")
        return jsonify({
            'error': 'No videos available',
            'message': 'Video pool is empty. GitHub Actions may be building it.'
        }), 503

    # Get excluded IDs from POST request
    excluded_ids = None
    if request.method == 'POST':
        data = request.get_json() or {}
        excluded_ids = set(data.get('excluded_ids', []))
        logger.debug(f"Client sent {len(excluded_ids)} excluded IDs")

    # Select weighted random video
    selected_video = select_weighted_video(video_pool, excluded_ids)

    if selected_video is None:
        logger.warning(f"Video request from {client_ip} - selection failed")
        return jsonify({
            'error': 'Selection failed',
            'message': 'Could not select a video from the pool'
        }), 500

    logger.debug(f"Served video to {client_ip}: {selected_video.get('title', 'Unknown')[:50]} (Views: {selected_video.get('viewCount', 'N/A')})")
    return jsonify(selected_video)


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
