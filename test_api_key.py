#!/usr/bin/env python3
"""
Quick test script to verify YouTube API key works correctly.
Run with: YOUTUBE_API_KEY=your_key_here python test_api_key.py
"""

import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta

API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

if not API_KEY:
    print("❌ ERROR: YOUTUBE_API_KEY environment variable not set")
    print("   Run: export YOUTUBE_API_KEY='your_key_here'")
    exit(1)

print("Testing YouTube API key...")
print(f"Key: {API_KEY[:8]}...{API_KEY[-4:]}")
print()

try:
    youtube = build('youtube', 'v3', developerKey=API_KEY)

    # Try a simple search
    published_after = (datetime.utcnow() - timedelta(hours=6)).isoformat() + 'Z'

    print("Attempting search...")
    search_response = youtube.search().list(
        type='video',
        part='id,snippet',
        maxResults=5,
        order='date',
        publishedAfter=published_after,
        regionCode='US'
    ).execute()

    videos_found = len(search_response.get('items', []))
    print(f"✅ SUCCESS! Found {videos_found} videos")
    print()

    if videos_found > 0:
        print("Sample videos:")
        for item in search_response['items'][:3]:
            print(f"  - {item['snippet']['title']}")

    print()
    print("✅ Your API key is working correctly!")
    print("   The issue must be something else.")

except HttpError as e:
    print(f"❌ API ERROR: {e}")
    print()

    if 'quota' in str(e).lower():
        print("💡 DIAGNOSIS: You've exceeded your YouTube API quota")
        print("   Wait until tomorrow (resets at midnight Pacific Time)")
    elif 'referer' in str(e).lower() or '403' in str(e):
        print("💡 DIAGNOSIS: HTTP referrer restriction is blocking the request")
        print()
        print("   FIX THIS:")
        print("   1. Go to: https://console.cloud.google.com/apis/credentials")
        print("   2. Click on your API key")
        print("   3. Under 'API restrictions', keep 'YouTube Data API v3'")
        print("   4. Under 'Application restrictions':")
        print("      - Either select 'None' (least secure but easiest)")
        print("      - Or select 'HTTP referrers' and add these:")
        print("        - https://bitm4ncer.github.io/*")
        print("        - https://*.github.io/*")
        print("        - Leave one blank entry for GitHub Actions")
        print("   5. Click Save")
    else:
        print("💡 DIAGNOSIS: Unknown API error")
        print("   Check your API key is valid and YouTube Data API v3 is enabled")

except Exception as e:
    print(f"❌ UNEXPECTED ERROR: {e}")
    print("   Check that google-api-python-client is installed:")
    print("   pip install -r scripts/requirements.txt")
