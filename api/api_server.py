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
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'YOUR_USERNAME/randomTube')
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
        print(f"Fetching video pool from {GITHUB_RAW_URL}...")
        response = requests.get(GITHUB_RAW_URL, timeout=10)
        response.raise_for_status()

        data = response.json()
        video_pool = data.get('videos', [])
        pool_last_updated = datetime.utcnow()

        print(f"✓ Loaded {len(video_pool)} videos from pool")
        return True
    except Exception as e:
        print(f"ERROR fetching video pool: {e}")
        return False


def video_rotator():
    """
    Background thread that picks a random video every second.
    This is the core of the "1 video per second" rotation system.
    """
    global current_video, videos_served

    print("Video rotator thread started")
    last_pool_refresh = time.time()

    while True:
        try:
            # Refresh pool periodically
            if time.time() - last_pool_refresh > (POOL_REFRESH_MINUTES * 60):
                fetch_video_pool()
                last_pool_refresh = time.time()

            # Pick random video if pool is available
            if video_pool:
                current_video = random.choice(video_pool)
                videos_served += 1
            else:
                current_video = {
                    'error': 'No videos in pool',
                    'message': 'Video pool is empty. GitHub Actions may be building it.'
                }

            # Wait 1 second before next rotation
            time.sleep(1)

        except Exception as e:
            print(f"ERROR in video rotator: {e}")
            time.sleep(1)


@app.route('/health')
def health():
    """Health check endpoint for Render.com and keepalive pings"""
    return jsonify({
        'status': 'healthy',
        'pool_size': len(video_pool),
        'uptime_seconds': (datetime.utcnow() - server_started).total_seconds()
    })


@app.route('/current-video')
def get_current_video():
    """Get the current random video (changes every second)"""
    if current_video is None:
        return jsonify({
            'error': 'Service starting',
            'message': 'Video pool is loading, please try again in a few seconds'
        }), 503

    return jsonify(current_video)


@app.route('/stats')
def get_stats():
    """Get statistics about the video pool and server"""
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
    print("="*60)
    print("UnseenStream API Server v0.1")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    print(f"GitHub Repo: {GITHUB_REPO}")
    print(f"Pool Refresh: Every {POOL_REFRESH_MINUTES} minutes")
    print("="*60)

    # Initial pool fetch
    print("\nInitializing video pool...")
    if not fetch_video_pool():
        print("WARNING: Could not fetch initial pool. Will retry in background.")
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
    print(f"\n✓ Server starting on port {port}")
    print("✓ Video rotator running (1 video/second)")
    print("\n" + "="*60 + "\n")

    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
