#!/usr/bin/env python3
"""
Test script to verify search terms are loaded correctly
"""

import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

# Import the function from video_discovery
import importlib.util
spec = importlib.util.spec_from_file_location("video_discovery", "scripts/video_discovery.py")
video_discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_discovery)

print("="*60)
print("Testing Search Terms Loading")
print("="*60)

# Test loading search terms
search_terms = video_discovery.load_search_terms()

print(f"\n✓ Successfully loaded {len(search_terms)} search terms")
print(f"\nFirst 20 terms:")
for i, term in enumerate(search_terms[:20], 1):
    print(f"  {i:2d}. {term}")

print(f"\n... and {len(search_terms) - 20} more terms")

# Test random selection
import random
selected = random.sample(search_terms, 6)
print(f"\n✓ Random sample of 6 terms (simulating SEARCHES_PER_RUN):")
for i, term in enumerate(selected, 1):
    print(f"  {i}. '{term}'")

print("\n" + "="*60)
print("✓ Search terms module working correctly!")
print("="*60)
