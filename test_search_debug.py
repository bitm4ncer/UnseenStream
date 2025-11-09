#!/usr/bin/env python3
"""
Debug script to test different search approaches
"""

import os
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

if not API_KEY:
    print("❌ ERROR: YOUTUBE_API_KEY not set")
    exit(1)

youtube = build('youtube', 'v3', developerKey=API_KEY)
published_after = (datetime.utcnow() - timedelta(hours=6)).isoformat() + 'Z'

print("="*60)
print("Testing YouTube Search Approaches")
print(f"Published after: {published_after}")
print("="*60)

# Test 1: No query parameter (current approach)
print("\n1. Testing WITHOUT query parameter (current approach)...")
try:
    response = youtube.search().list(
        type='video',
        part='id,snippet',
        maxResults=50,
        order='date',
        publishedAfter=published_after
    ).execute()

    items = response.get('items', [])
    print(f"   ✓ Found {len(items)} videos")
    if items:
        print(f"   Sample: {items[0]['snippet']['title'][:50]}")
except HttpError as e:
    print(f"   ✗ Error: {e}")

# Test 2: With generic query
print("\n2. Testing WITH generic query 'a'...")
try:
    response = youtube.search().list(
        q='a',
        type='video',
        part='id,snippet',
        maxResults=50,
        order='date',
        publishedAfter=published_after
    ).execute()

    items = response.get('items', [])
    print(f"   ✓ Found {len(items)} videos")
    if items:
        print(f"   Sample: {items[0]['snippet']['title'][:50]}")
except HttpError as e:
    print(f"   ✗ Error: {e}")

# Test 3: With relevanceLanguage
print("\n3. Testing WITH relevanceLanguage='en'...")
try:
    response = youtube.search().list(
        type='video',
        part='id,snippet',
        maxResults=50,
        order='date',
        publishedAfter=published_after,
        relevanceLanguage='en'
    ).execute()

    items = response.get('items', [])
    print(f"   ✓ Found {len(items)} videos")
    if items:
        print(f"   Sample: {items[0]['snippet']['title'][:50]}")
except HttpError as e:
    print(f"   ✗ Error: {e}")

# Test 4: With videoDuration (short videos only)
print("\n4. Testing WITH videoDuration='short'...")
try:
    response = youtube.search().list(
        type='video',
        part='id,snippet',
        maxResults=50,
        order='date',
        publishedAfter=published_after,
        videoDuration='short'
    ).execute()

    items = response.get('items', [])
    print(f"   ✓ Found {len(items)} videos")
    if items:
        print(f"   Sample: {items[0]['snippet']['title'][:50]}")
except HttpError as e:
    print(f"   ✗ Error: {e}")

print("\n" + "="*60)
print("Test complete!")
print("="*60)
