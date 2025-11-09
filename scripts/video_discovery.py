#!/usr/bin/env python3
"""
UnseenStream Video Discovery Script v0.1
Discovers ultra-fresh YouTube videos (uploaded within last hour) with 0-1 views.
Runs hourly via GitHub Actions.
Uses efficient batching to minimize API quota usage.
"""

import os
import json
import random
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
POOL_FILE = 'videos_pool.json'
MAX_POOL_SIZE = 10000
MIN_POOL_SIZE = 1000  # Never delete videos if pool is below this

# Search Configuration
SEARCH_WINDOW_HOURS = 1  # Look for videos uploaded in last 1 hour
MAX_RESULTS_PER_SEARCH = 50
SEARCHES_PER_RUN = 1  # One search per hour = 24 searches/day

# Filter Configuration
MAX_VIEW_COUNT = 1  # Only videos with 0-1 views
MAX_VIDEO_AGE_HOURS = 48  # Remove videos older than 48 hours
VIEW_CHECK_BATCH_SIZE = 50  # Check up to 50 videos per API call


def load_pool():
    """Load existing video pool from JSON file"""
    try:
        with open(POOL_FILE, 'r') as f:
            data = json.load(f)
            return data.get('videos', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_pool(videos, stats=None):
    """Save video pool to JSON file"""
    data = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'total_videos': len(videos),
        'videos': videos
    }

    if stats:
        data['stats'] = stats

    with open(POOL_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✓ Saved {len(videos)} videos to {POOL_FILE}")


def get_published_after():
    """Get the timestamp for filtering recent videos"""
    date = datetime.utcnow() - timedelta(hours=SEARCH_WINDOW_HOURS)
    return date.isoformat() + 'Z'


def search_recent_videos(youtube):
    """
    Search for videos uploaded in the last hour.
    Uses random region/language for diversity.
    """
    published_after = get_published_after()

    # Randomize for diversity
    regions = ['US', 'GB', 'CA', 'AU', 'IN', 'BR', 'JP', 'DE', 'FR', 'KR',
               'MX', 'ES', 'IT', 'RU', 'NL', 'SE', 'NO', 'PL', 'ID', 'TH']
    languages = ['en', 'es', 'pt', 'ja', 'ko', 'hi', 'fr', 'de', 'it',
                 'ru', 'ar', 'zh', 'th', 'vi', 'id', 'tr', 'pl', 'nl']

    region = random.choice(regions)
    language = random.choice(languages)

    print(f"\nSearching for videos:")
    print(f"  Region: {region}")
    print(f"  Language: {language}")
    print(f"  Published after: {published_after}")
    print(f"  Max results: {MAX_RESULTS_PER_SEARCH}")

    try:
        search_response = youtube.search().list(
            type='video',
            part='id,snippet',
            maxResults=MAX_RESULTS_PER_SEARCH,
            order='date',
            publishedAfter=published_after,
            regionCode=region,
            relevanceLanguage=language
        ).execute()

        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        print(f"✓ Found {len(video_ids)} videos")
        return video_ids

    except HttpError as e:
        print(f"ERROR in search: {e}")
        if 'quota' in str(e).lower():
            print("QUOTA EXCEEDED - stopping")
        return []


def batch_check_view_counts(youtube, video_ids):
    """
    Check view counts for multiple videos in a single API call.
    Filters for videos with 0-1 views only.
    """
    if not video_ids:
        return []

    print(f"\nChecking view counts for {len(video_ids)} videos (batched)...")

    low_view_videos = []

    try:
        # API allows up to 50 IDs per call
        videos_response = youtube.videos().list(
            part='statistics,snippet',
            id=','.join(video_ids[:VIEW_CHECK_BATCH_SIZE])
        ).execute()

        for item in videos_response.get('items', []):
            video_id = item['id']
            view_count = int(item['statistics'].get('viewCount', 0))

            # Filter for 0-1 views
            if view_count <= MAX_VIEW_COUNT:
                video_data = {
                    'id': video_id,
                    'title': item['snippet']['title'],
                    'channelTitle': item['snippet']['channelTitle'],
                    'thumbnail': item['snippet']['thumbnails']['medium']['url'],
                    'viewCount': view_count,
                    'publishedAt': item['snippet']['publishedAt'],
                    'discoveredAt': datetime.utcnow().isoformat() + 'Z'
                }
                low_view_videos.append(video_data)
                print(f"  ✓ {video_data['title'][:50]} ({view_count} views)")

        print(f"✓ Found {len(low_view_videos)} videos with 0-1 views")
        return low_view_videos

    except HttpError as e:
        print(f"ERROR checking view counts: {e}")
        return []


def update_existing_videos(youtube, existing_videos):
    """
    Update view counts for existing videos in the pool.
    Uses smart batching to minimize API calls.
    """
    if not existing_videos:
        return []

    print(f"\nUpdating view counts for {len(existing_videos)} existing videos...")

    # Calculate age of each video
    now = datetime.utcnow()
    fresh_videos = []

    for video in existing_videos:
        discovered_at = datetime.fromisoformat(video['discoveredAt'].replace('Z', ''))
        age_hours = (now - discovered_at).total_seconds() / 3600

        # Remove videos older than MAX_VIDEO_AGE_HOURS
        if age_hours > MAX_VIDEO_AGE_HOURS:
            continue

        fresh_videos.append(video)

    if len(fresh_videos) < len(existing_videos):
        removed = len(existing_videos) - len(fresh_videos)
        print(f"  Removed {removed} videos older than {MAX_VIDEO_AGE_HOURS} hours")

    # Batch check view counts for a sample of fresh videos
    # To save quota, we only check a portion each run
    if len(fresh_videos) > 200:
        # Sample random videos to check
        sample_size = min(200, len(fresh_videos))
        videos_to_check = random.sample(fresh_videos, sample_size)
    else:
        videos_to_check = fresh_videos

    print(f"  Checking view counts for {len(videos_to_check)} sampled videos...")

    video_ids = [v['id'] for v in videos_to_check]
    updated_views = {}

    try:
        # Batch check in groups of 50
        for i in range(0, len(video_ids), VIEW_CHECK_BATCH_SIZE):
            batch = video_ids[i:i + VIEW_CHECK_BATCH_SIZE]

            videos_response = youtube.videos().list(
                part='statistics',
                id=','.join(batch)
            ).execute()

            for item in videos_response.get('items', []):
                video_id = item['id']
                view_count = int(item['statistics'].get('viewCount', 0))
                updated_views[video_id] = view_count

        print(f"  ✓ Updated view counts for {len(updated_views)} videos")

    except HttpError as e:
        print(f"  ERROR updating view counts: {e}")

    # Filter out videos that now have > MAX_VIEW_COUNT views
    final_videos = []
    removed_count = 0

    for video in fresh_videos:
        if video['id'] in updated_views:
            new_view_count = updated_views[video['id']]
            if new_view_count > MAX_VIEW_COUNT:
                removed_count += 1
                continue
            video['viewCount'] = new_view_count

        final_videos.append(video)

    if removed_count > 0:
        print(f"  Removed {removed_count} videos that exceeded {MAX_VIEW_COUNT} views")

    return final_videos


def main():
    """Main function"""
    print("="*60)
    print("UnseenStream Video Discovery v0.1")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    print("="*60)

    if not API_KEY:
        print("ERROR: YOUTUBE_API_KEY environment variable not set")
        return

    youtube = build('youtube', 'v3', developerKey=API_KEY)

    # Load existing pool
    existing_videos = load_pool()
    print(f"\nLoaded {len(existing_videos)} existing videos from pool")

    # Search for new videos
    print(f"\nSearching for videos uploaded in last {SEARCH_WINDOW_HOURS} hour(s)...")
    new_video_ids = search_recent_videos(youtube)

    # Filter existing IDs
    existing_ids = {v['id'] for v in existing_videos}
    fresh_video_ids = [vid for vid in new_video_ids if vid not in existing_ids]

    if fresh_video_ids:
        print(f"Found {len(fresh_video_ids)} new videos (not in pool)")
        new_videos = batch_check_view_counts(youtube, fresh_video_ids)
    else:
        print("No new videos found")
        new_videos = []

    # Update existing videos (check view counts, remove old/popular)
    updated_existing = update_existing_videos(youtube, existing_videos)

    # Combine and deduplicate
    all_videos = updated_existing + new_videos

    # Deduplicate just in case
    seen = set()
    unique_videos = []
    for video in all_videos:
        if video['id'] not in seen:
            seen.add(video['id'])
            unique_videos.append(video)

    # Safety check: Never delete if pool is too small
    if len(unique_videos) < MIN_POOL_SIZE and len(existing_videos) >= MIN_POOL_SIZE:
        print(f"\n⚠️  WARNING: Pool would drop below {MIN_POOL_SIZE} videos")
        print(f"   Keeping existing pool to prevent data loss")
        unique_videos = existing_videos

    # Shuffle for randomness
    random.shuffle(unique_videos)

    # Limit to MAX_POOL_SIZE
    if len(unique_videos) > MAX_POOL_SIZE:
        print(f"\nLimiting pool to {MAX_POOL_SIZE} videos (had {len(unique_videos)})")
        unique_videos = unique_videos[:MAX_POOL_SIZE]

    # Save to file
    stats = {
        'new_videos_added': len(new_videos),
        'videos_removed': len(existing_videos) - len(updated_existing),
        'total_in_pool': len(unique_videos)
    }

    save_pool(unique_videos, stats)

    print("\n" + "="*60)
    print("Discovery Complete!")
    print(f"  New videos added: {stats['new_videos_added']}")
    print(f"  Videos removed: {stats['videos_removed']}")
    print(f"  Total in pool: {stats['total_in_pool']}")
    print("="*60)


if __name__ == '__main__':
    main()
