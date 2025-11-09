#!/usr/bin/env python3
"""
YouTube Video Scraper
Scrapes random videos matching camera file patterns (IMG, DSC, MOV, VID, etc.)
Designed to run hourly via GitHub Actions to distribute API quota throughout the day.
"""

import os
import json
import random
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
VIDEOS_FILE = 'videos.json'
MAX_RESULTS_PER_QUERY = 5  # Keep it low to save quota
QUERIES_PER_RUN = 10  # 10 queries * 5 results = ~50 videos per hour
PATTERNS = ['DSC', 'IMG', 'MOV', 'VID', 'GOPR', 'DJI']

# Preferences
MAX_VIEWS = 10000  # Temporarily higher to get initial results
MIN_VIEWS = 0
DATE_RANGE_DAYS = 30  # Temporarily wider range to get initial results

def load_existing_videos():
    """Load existing videos from JSON file"""
    try:
        with open(VIDEOS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('videos', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_videos(videos):
    """Save videos to JSON file"""
    data = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'total_videos': len(videos),
        'videos': videos
    }
    with open(VIDEOS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(videos)} videos to {VIDEOS_FILE}")

def generate_random_query():
    """Generate a random search query based on camera file patterns"""
    pattern = random.choice(PATTERNS)
    number = str(random.randint(0, 9999)).zfill(4)
    # Try both with and without underscore for better results
    if random.random() > 0.5:
        return f"{pattern}_{number}"
    else:
        return f"{pattern} {number}"

def get_published_after_date():
    """Get the date for filtering recent videos"""
    date = datetime.utcnow() - timedelta(days=DATE_RANGE_DAYS)
    return date.isoformat() + 'Z'

def scrape_videos():
    """Scrape random videos from YouTube"""
    if not API_KEY:
        print("ERROR: YOUTUBE_API_KEY environment variable not set")
        return []

    youtube = build('youtube', 'v3', developerKey=API_KEY)
    published_after = get_published_after_date()
    new_videos = []
    existing_ids = set()

    # Load existing videos to avoid duplicates
    existing_videos = load_existing_videos()
    existing_ids = {v['id'] for v in existing_videos}
    print(f"Loaded {len(existing_videos)} existing videos")

    # Perform multiple searches
    for i in range(QUERIES_PER_RUN):
        query = generate_random_query()
        print(f"Query {i+1}/{QUERIES_PER_RUN}: {query}")

        try:
            # Search for videos
            search_response = youtube.search().list(
                q=query,
                type='video',
                part='id,snippet',
                maxResults=MAX_RESULTS_PER_QUERY,
                order='date',
                publishedAfter=published_after
            ).execute()

            if not search_response.get('items'):
                print(f"  No results found")
                continue

            # Get video IDs
            video_ids = [item['id']['videoId'] for item in search_response['items']]

            # Get video details (statistics)
            videos_response = youtube.videos().list(
                part='statistics,contentDetails,snippet',
                id=','.join(video_ids)
            ).execute()

            # Filter and process videos
            for item in videos_response.get('items', []):
                video_id = item['id']

                # Skip if already exists
                if video_id in existing_ids:
                    continue

                # Get view count
                view_count = int(item['statistics'].get('viewCount', 0))

                # Filter by view count
                if view_count < MIN_VIEWS or view_count > MAX_VIEWS:
                    continue

                # Add to new videos
                video_data = {
                    'id': video_id,
                    'title': item['snippet']['title'],
                    'channelTitle': item['snippet']['channelTitle'],
                    'thumbnail': item['snippet']['thumbnails']['medium']['url'],
                    'viewCount': view_count,
                    'publishedAt': item['snippet']['publishedAt'],
                    'scrapedAt': datetime.utcnow().isoformat() + 'Z'
                }
                new_videos.append(video_data)
                existing_ids.add(video_id)
                print(f"  ✓ Added: {video_data['title'][:50]} ({view_count} views)")

        except HttpError as e:
            print(f"  ERROR: {e}")
            if 'quota' in str(e).lower():
                print("  Quota exceeded, stopping scrape")
                break
            continue

    print(f"\nFound {len(new_videos)} new videos in this run")
    return new_videos

def cleanup_old_videos(videos, max_age_days=30):
    """Remove videos older than max_age_days"""
    cutoff_date = datetime.utcnow().replace(tzinfo=None) - timedelta(days=max_age_days)

    cleaned_videos = []
    for video in videos:
        scraped_at = datetime.fromisoformat(video['scrapedAt'].replace('Z', '')).replace(tzinfo=None)
        if scraped_at > cutoff_date:
            cleaned_videos.append(video)

    removed = len(videos) - len(cleaned_videos)
    if removed > 0:
        print(f"Removed {removed} old videos (older than {max_age_days} days)")

    return cleaned_videos

def main():
    """Main function"""
    print("="*60)
    print("YouTube Video Scraper")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    print("="*60)

    # Load existing videos
    existing_videos = load_existing_videos()

    # Scrape new videos
    new_videos = scrape_videos()

    # Combine and deduplicate
    all_videos = existing_videos + new_videos

    # Remove duplicates (shouldn't happen, but just in case)
    seen = set()
    unique_videos = []
    for video in all_videos:
        if video['id'] not in seen:
            seen.add(video['id'])
            unique_videos.append(video)

    # Cleanup old videos
    unique_videos = cleanup_old_videos(unique_videos)

    # Shuffle to randomize order
    random.shuffle(unique_videos)

    # Limit total videos to prevent file from growing too large
    MAX_TOTAL_VIDEOS = 1000
    if len(unique_videos) > MAX_TOTAL_VIDEOS:
        print(f"Limiting to {MAX_TOTAL_VIDEOS} videos (had {len(unique_videos)})")
        unique_videos = unique_videos[:MAX_TOTAL_VIDEOS]

    # Save to file
    save_videos(unique_videos)

    print("="*60)
    print(f"Scrape complete!")
    print(f"Total videos in database: {len(unique_videos)}")
    print("="*60)

if __name__ == '__main__':
    main()
