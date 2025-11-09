// ============================================
// Configuration & State
// ============================================

// Render.com API Configuration
// Replace with your Render.com URL after deployment
const RENDER_API_URL = localStorage.getItem('render_api_url') || '';
let useRenderAPI = RENDER_API_URL !== '';

// YouTube API Key - User must provide their own key
// Get from localStorage or prompt user to enter
let API_KEY = localStorage.getItem('youtube_api_key') || '';
let player;
let preloadPlayer; // Player for preloading next video
let videoQueue = [];
let currentIndex = 0;
let currentVideo = null;
let touchStartY = 0;
let touchEndY = 0;
let isLoading = false;
let prefetchedVideos = [];
let prefetchedIndex = 0;
let usePrefetched = false;
let isAutoplayEnabled = false;

const DEFAULT_PREFERENCES = {
  maxViews: 1000,
  minViews: 0,
  dateRange: 7,
  patterns: ['DSC', 'IMG', 'MOV', 'VID']
};

let preferences = JSON.parse(localStorage.getItem('preferences')) || DEFAULT_PREFERENCES;

// ============================================
// API Key Management
// ============================================

function checkAndPromptForAPIKey() {
  if (!API_KEY && !useRenderAPI) {
    const apiKeyModal = `
      <div id="api-key-modal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 10000; display: flex; align-items: center; justify-content: center;">
        <div style="background: #1a1a1a; padding: 30px; border-radius: 10px; max-width: 500px; width: 90%;">
          <h2 style="color: #fff; margin-top: 0;">YouTube API Key Required</h2>
          <p style="color: #ccc;">To discover fresh videos, you need a YouTube API key. It's free!</p>
          <ol style="color: #ccc; text-align: left; line-height: 1.6;">
            <li>Go to <a href="https://console.cloud.google.com/" target="_blank" style="color: #4a9eff;">Google Cloud Console</a></li>
            <li>Create a project and enable YouTube Data API v3</li>
            <li>Create credentials → API Key</li>
            <li>Restrict by HTTP referrer (add your domain)</li>
            <li>Paste your key below</li>
          </ol>
          <input type="text" id="api-key-input" placeholder="Enter your YouTube API key" style="width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; border: 1px solid #444; background: #2a2a2a; color: #fff; box-sizing: border-box;">
          <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button onclick="saveAPIKey()" style="flex: 1; padding: 10px; background: #4a9eff; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px;">Save & Start</button>
            <button onclick="skipAPIKey()" style="flex: 1; padding: 10px; background: #444; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px;">Skip (Limited Videos)</button>
          </div>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', apiKeyModal);
  }
}

function saveAPIKey() {
  const input = document.getElementById('api-key-input');
  const key = input.value.trim();
  if (key) {
    localStorage.setItem('youtube_api_key', key);
    API_KEY = key;
    document.getElementById('api-key-modal').remove();
    console.log('API key saved successfully');
    // Reload to start fetching videos
    location.reload();
  } else {
    alert('Please enter a valid API key');
  }
}

function skipAPIKey() {
  document.getElementById('api-key-modal').remove();
  console.log('API key skipped - using pre-fetched videos only');
}

// Make functions globally accessible
window.saveAPIKey = saveAPIKey;
window.skipAPIKey = skipAPIKey;

// ============================================
// Load Pre-fetched Videos
// ============================================

async function loadPrefetchedVideos() {
  try {
    const response = await fetch('videos.json');
    const data = await response.json();
    prefetchedVideos = data.videos || [];

    // Shuffle for randomness
    prefetchedVideos.sort(() => Math.random() - 0.5);

    console.log(`Loaded ${prefetchedVideos.length} pre-fetched videos`);
    console.log(`Last updated: ${data.last_updated}`);

    return prefetchedVideos.length > 0;
  } catch (error) {
    console.error('Error loading pre-fetched videos:', error);
    return false;
  }
}

function getNextPrefetchedVideo() {
  if (prefetchedVideos.length === 0) return null;

  const video = prefetchedVideos[prefetchedIndex % prefetchedVideos.length];
  prefetchedIndex++;

  // Convert to format expected by loadVideo
  return {
    id: { videoId: video.id },
    snippet: {
      title: video.title,
      channelTitle: video.channelTitle,
      thumbnails: {
        medium: { url: video.thumbnail }
      }
    },
    statistics: {
      viewCount: video.viewCount.toString()
    }
  };
}

// ============================================
// Render.com API Integration
// ============================================

async function fetchFromRenderAPI() {
  if (!RENDER_API_URL) {
    console.log('Render API URL not configured');
    return null;
  }

  try {
    console.log('Fetching from Render API...');
    const response = await fetch(`${RENDER_API_URL}/current-video`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      signal: AbortSignal.timeout(5000) // 5 second timeout
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const video = await response.json();

    if (video.error) {
      console.warn('Render API returned error:', video.message);
      return null;
    }

    console.log('✓ Got video from Render API:', video.title);

    // Convert to format expected by loadVideo
    return {
      id: { videoId: video.id },
      snippet: {
        title: video.title,
        channelTitle: video.channelTitle,
        thumbnails: {
          medium: { url: video.thumbnail }
        }
      },
      statistics: {
        viewCount: video.viewCount.toString()
      }
    };

  } catch (error) {
    console.warn('Render API fetch failed:', error.message);
    return null;
  }
}

async function checkRenderAPIHealth() {
  if (!RENDER_API_URL) return false;

  try {
    const response = await fetch(`${RENDER_API_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3000)
    });
    return response.ok;
  } catch (error) {
    console.warn('Render API health check failed:', error.message);
    return false;
  }
}

// ============================================
// API Key Management
// ============================================

function checkApiKey() {
  if (!API_KEY) {
    console.log('No API key available');
    return false;
  }
  return true;
}

// ============================================
// YouTube Player Setup
// ============================================

function onYouTubeIframeAPIReady() {
  player = new YT.Player('player', {
    height: '100%',
    width: '100%',
    playerVars: {
      autoplay: 0,
      controls: 1,
      modestbranding: 1,
      rel: 0,
      playsinline: 1
    },
    events: {
      'onReady': onPlayerReady,
      'onStateChange': onPlayerStateChange
    }
  });

  // Create preload player (hidden, for buffering next video)
  preloadPlayer = new YT.Player('preload-player', {
    height: '100%',
    width: '100%',
    playerVars: {
      autoplay: 0,
      controls: 0,
      modestbranding: 1,
      rel: 0,
      playsinline: 1
    }
  });
}

function onPlayerReady(event) {
  console.log('Player ready');

  // If we're using prefetched videos, load the first one
  if (usePrefetched && videoQueue.length > 0) {
    loadVideo(videoQueue[0]);
    document.getElementById('loading').classList.add('hidden');
  }
  // Don't try API mode - we only use pre-fetched videos
}

function onPlayerStateChange(event) {
  // Preload next video when current video starts playing
  if (event.data === YT.PlayerState.PLAYING) {
    preloadNextVideo();
  }

  // Autoplay: move to next video when current video ends
  if (event.data === YT.PlayerState.ENDED && isAutoplayEnabled) {
    nextVideo();
  }
}

function preloadNextVideo() {
  const nextIndex = currentIndex + 1;

  // Check if there's a next video to preload
  if (nextIndex < videoQueue.length) {
    const nextVideo = videoQueue[nextIndex];
    if (nextVideo && preloadPlayer) {
      try {
        // Use cueVideoById to preload without playing
        preloadPlayer.cueVideoById(nextVideo.id.videoId);
        console.log('Preloading next video:', nextVideo.snippet.title);
      } catch (error) {
        console.error('Error preloading video:', error);
      }
    }
  }
}

// ============================================
// Random Video Generation
// ============================================

function generateRandomQuery() {
  const pattern = preferences.patterns[Math.floor(Math.random() * preferences.patterns.length)];
  const number = String(Math.floor(Math.random() * 10000)).padStart(4, '0');
  return pattern + '_' + number;
}

function getPublishedAfterDate() {
  const date = new Date();
  date.setDate(date.getDate() - preferences.dateRange);
  return date.toISOString();
}

async function fetchVideos() {
  if (isLoading) return;

  isLoading = true;
  document.getElementById('loading').classList.remove('hidden');

  try {
    // Priority 1: Try Render API (0-1 view videos, rotates every second)
    if (useRenderAPI && RENDER_API_URL) {
      const renderVideo = await fetchFromRenderAPI();
      if (renderVideo) {
        videoQueue.push(renderVideo);
        if (!currentVideo && videoQueue.length > 0) {
          loadVideo(videoQueue[0]);
        }
        isLoading = false;
        document.getElementById('loading').classList.add('hidden');
        return;
      }
      console.log('Render API failed, falling back to YouTube API');
    }

    // Priority 2: Try YouTube API (if API key available)
    if (!API_KEY) {
      console.log('No API key, trying prefetched videos');
      throw new Error('No API key available');
    }

    const query = generateRandomQuery();
    const publishedAfter = getPublishedAfterDate();

    // Fetch only 5 videos at a time to save quota
    const searchUrl = `https://www.googleapis.com/youtube/v3/search?` +
      `part=snippet` +
      `&q=${encodeURIComponent(query)}` +
      `&type=video` +
      `&maxResults=5` +
      `&order=date` +
      `&publishedAfter=${publishedAfter}` +
      `&key=${API_KEY}`;

    const response = await fetch(searchUrl);
    const data = await response.json();

    if (!response.ok) {
      const errorMsg = data.error?.message || `API Error: ${response.status}`;
      console.error('YouTube API Error:', data);
      throw new Error(errorMsg);
    }

    if (data.error) {
      console.error('YouTube API Error:', data.error);
      throw new Error(data.error.message || 'API Error');
    }

    if (!data.items || data.items.length === 0) {
      console.log('No videos found, trying again...');
      isLoading = false;
      fetchVideos();
      return;
    }

    // Get video details (including view count)
    const videoIds = data.items.map(item => item.id.videoId).join(',');
    const detailsUrl = `https://www.googleapis.com/youtube/v3/videos?` +
      `part=statistics,contentDetails` +
      `&id=${videoIds}` +
      `&key=${API_KEY}`;

    const detailsResponse = await fetch(detailsUrl);
    const detailsData = await detailsResponse.json();

    // Merge search results with details and filter by view count
    const videosWithDetails = data.items.map(item => {
      const details = detailsData.items.find(d => d.id === item.id.videoId);
      return {
        ...item,
        statistics: details?.statistics,
        contentDetails: details?.contentDetails
      };
    }).filter(video => {
      const viewCount = parseInt(video.statistics?.viewCount || 0);
      return viewCount >= preferences.minViews && viewCount <= preferences.maxViews;
    });

    if (videosWithDetails.length === 0) {
      console.log('No videos within view count range, trying again...');
      isLoading = false;
      fetchVideos();
      return;
    }

    // Shuffle and add to queue
    const shuffled = videosWithDetails.sort(() => Math.random() - 0.5);
    videoQueue.push(...shuffled);

    // Load first video if none is playing
    if (!currentVideo && videoQueue.length > 0) {
      loadVideo(videoQueue[0]);
    }

    document.getElementById('loading').classList.add('hidden');
  } catch (error) {
    console.error('Error fetching videos:', error);
    const loadingEl = document.getElementById('loading');

    // If quota exceeded, switch to prefetched videos
    if (error.message.includes('quota')) {
      console.log('Quota exceeded, switching to pre-fetched videos');
      usePrefetched = true;

      if (prefetchedVideos.length > 0) {
        loadingEl.textContent = 'Using pre-fetched videos (API quota exceeded)';
        loadingEl.style.color = '#ffa500';

        // Load videos from prefetched
        for (let i = 0; i < 5 && i < prefetchedVideos.length; i++) {
          const video = getNextPrefetchedVideo();
          if (video) videoQueue.push(video);
        }

        if (!currentVideo && videoQueue.length > 0) {
          loadVideo(videoQueue[0]);
        }

        setTimeout(() => {
          loadingEl.classList.add('hidden');
        }, 2000);

        isLoading = false;
        return;
      } else {
        loadingEl.textContent = 'Quota exceeded. No pre-fetched videos available.';
        loadingEl.style.color = '#ff4444';
        loadingEl.style.padding = '20px';
        loadingEl.style.maxWidth = '80%';
        isLoading = false;
        return;
      }
    }

    // Other errors
    loadingEl.textContent = `Error: ${error.message}`;
    loadingEl.style.color = '#ff4444';
    loadingEl.style.padding = '20px';
    loadingEl.style.maxWidth = '80%';

    // Don't retry automatically if it's an API key error
    if (error.message.includes('API') || error.message.includes('key')) {
      isLoading = false;
      return;
    }

    // Show error for 3 seconds then retry
    setTimeout(() => {
      loadingEl.style.color = '';
      isLoading = false;
      if (videoQueue.length === 0) {
        fetchVideos();
      }
    }, 3000);
  }

  isLoading = false;
}

function loadVideo(video, direction = 'next') {
  if (!video) return;

  currentVideo = video;
  const videoId = video.id.videoId;
  const playerElement = document.getElementById('player');

  // Determine slide direction
  const slideOutClass = direction === 'next' ? 'slide-out-up' : 'slide-out-down';
  const slideInClass = direction === 'next' ? 'slide-in-up' : 'slide-in-down';

  // Add slide-out animation
  playerElement.className = slideOutClass;

  // Wait for slide-out animation to complete, then load new video
  setTimeout(() => {
    try {
      player.loadVideoById(videoId);
    } catch (error) {
      console.error('Error loading video:', error);
      nextVideo();
      return;
    }

    // Update UI
    const title = video.snippet.title;
    const channelName = video.snippet.channelTitle;
    const viewCount = parseInt(video.statistics?.viewCount || 0);

    document.getElementById('video-title').textContent = title;
    document.getElementById('video-stats').textContent =
      `${viewCount.toLocaleString()} views • ${channelName}`;

    updateHeartButton();

    // Add slide-in animation
    playerElement.className = slideInClass;

    // Remove animation classes after animation completes
    setTimeout(() => {
      playerElement.className = '';
    }, 400);
  }, 400);
}

// ============================================
// Navigation
// ============================================

function nextVideo() {
  currentIndex++;

  // Fetch more videos if running low (only 2 videos left)
  if (currentIndex >= videoQueue.length - 2 && !isLoading) {
    if (usePrefetched) {
      // Add more from prefetched
      for (let i = 0; i < 5; i++) {
        const video = getNextPrefetchedVideo();
        if (video) videoQueue.push(video);
      }
    } else {
      fetchVideos();
    }
  }

  if (currentIndex < videoQueue.length) {
    loadVideo(videoQueue[currentIndex], 'next');
  } else if (!isLoading) {
    if (usePrefetched) {
      // Add more from prefetched
      for (let i = 0; i < 5; i++) {
        const video = getNextPrefetchedVideo();
        if (video) videoQueue.push(video);
      }
      if (currentIndex < videoQueue.length) {
        loadVideo(videoQueue[currentIndex], 'next');
      }
    } else {
      fetchVideos();
    }
  }
}

function previousVideo() {
  if (currentIndex > 0) {
    currentIndex--;
    loadVideo(videoQueue[currentIndex], 'prev');
  }
}

// ============================================
// Swipe Detection
// ============================================

const container = document.getElementById('video-container');

container.addEventListener('touchstart', (e) => {
  touchStartY = e.changedTouches[0].screenY;
}, { passive: true });

container.addEventListener('touchend', (e) => {
  touchEndY = e.changedTouches[0].screenY;
  handleSwipe();
}, { passive: true });

function handleSwipe() {
  const swipeDistance = touchStartY - touchEndY;
  const threshold = 50;

  if (swipeDistance > threshold) {
    // Swipe up - next video
    nextVideo();
  } else if (swipeDistance < -threshold) {
    // Swipe down - previous video
    previousVideo();
  }
}

// Keyboard support for desktop
document.addEventListener('keydown', (e) => {
  // Prevent default arrow key behavior (scrolling)
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault();
  }

  if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
    nextVideo();
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
    previousVideo();
  } else if (e.key === 's' || e.key === 'S') {
    toggleSave();
  }
});

// ============================================
// Save Functionality
// ============================================

function toggleSave() {
  if (!currentVideo) return;

  const savedVideos = getSavedVideos();
  const videoId = currentVideo.id.videoId;
  const existingIndex = savedVideos.findIndex(v => v.id === videoId);

  if (existingIndex >= 0) {
    // Remove from saved
    savedVideos.splice(existingIndex, 1);
  } else {
    // Add to saved
    savedVideos.push({
      id: videoId,
      title: currentVideo.snippet.title,
      channelName: currentVideo.snippet.channelTitle,
      thumbnail: currentVideo.snippet.thumbnails.medium.url,
      viewCount: parseInt(currentVideo.statistics?.viewCount || 0),
      savedAt: new Date().toISOString()
    });
  }

  localStorage.setItem('savedVideos', JSON.stringify(savedVideos));
  updateHeartButton();
}

function updateHeartButton() {
  if (!currentVideo) return;

  const savedVideos = getSavedVideos();
  const videoId = currentVideo.id.videoId;
  const isSaved = savedVideos.some(v => v.id === videoId);

  const heartBtn = document.getElementById('heart-btn');
  heartBtn.textContent = isSaved ? '♥' : '♡';
  heartBtn.classList.toggle('saved', isSaved);
}

function getSavedVideos() {
  return JSON.parse(localStorage.getItem('savedVideos') || '[]');
}

// ============================================
// Autoplay Functionality
// ============================================

function toggleAutoplay() {
  isAutoplayEnabled = !isAutoplayEnabled;
  const autoplayBtn = document.getElementById('autoplay-btn');
  autoplayBtn.classList.toggle('active', isAutoplayEnabled);

  // Save preference to localStorage
  localStorage.setItem('autoplayEnabled', isAutoplayEnabled);

  console.log('Autoplay:', isAutoplayEnabled ? 'enabled' : 'disabled');
}

// Load autoplay preference on startup
function loadAutoplayPreference() {
  const savedPreference = localStorage.getItem('autoplayEnabled');
  if (savedPreference === 'true') {
    isAutoplayEnabled = true;
    document.getElementById('autoplay-btn')?.classList.add('active');
  }
}

// Call this when the page loads
window.addEventListener('DOMContentLoaded', loadAutoplayPreference);

// ============================================
// Settings Modal
// ============================================

function openSettings() {
  // Load current preferences
  document.getElementById('max-views').value = preferences.maxViews;
  document.getElementById('min-views').value = preferences.minViews;
  document.getElementById('date-range').value = preferences.dateRange;

  // Update checkboxes
  const checkboxes = document.querySelectorAll('#patterns-group input[type="checkbox"]');
  checkboxes.forEach(cb => {
    cb.checked = preferences.patterns.includes(cb.value);
    cb.parentElement.classList.toggle('checked', cb.checked);
  });

  document.getElementById('settings-modal').classList.add('show');
}

function closeSettings() {
  document.getElementById('settings-modal').classList.remove('show');
}

function saveSettings() {
  // Get selected patterns
  const checkedBoxes = document.querySelectorAll('#patterns-group input[type="checkbox"]:checked');
  const patterns = Array.from(checkedBoxes).map(cb => cb.value);

  if (patterns.length === 0) {
    alert('Please select at least one title pattern');
    return;
  }

  preferences = {
    maxViews: parseInt(document.getElementById('max-views').value),
    minViews: parseInt(document.getElementById('min-views').value),
    dateRange: parseInt(document.getElementById('date-range').value),
    patterns: patterns
  };

  localStorage.setItem('preferences', JSON.stringify(preferences));

  // Clear queue and fetch new videos with new preferences
  videoQueue = [];
  currentIndex = 0;
  closeSettings();
  fetchVideos();
}

// Checkbox styling
document.getElementById('patterns-group').addEventListener('change', (e) => {
  if (e.target.type === 'checkbox') {
    e.target.parentElement.classList.toggle('checked', e.target.checked);
  }
});

// ============================================
// Saved Videos Modal
// ============================================

function openSaved() {
  const savedVideos = getSavedVideos();
  const listContainer = document.getElementById('saved-list');

  document.getElementById('saved-count').textContent = savedVideos.length;

  if (savedVideos.length === 0) {
    listContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">♡</div>
        <p>No saved videos yet</p>
        <p style="font-size: 14px; margin-top: 10px;">Heart videos to save them here</p>
      </div>
    `;
  } else {
    listContainer.innerHTML = savedVideos.reverse().map(video => `
      <div class="video-item" onclick="playVideo('${video.id}')">
        <img src="${video.thumbnail}" alt="${video.title}">
        <div class="video-item-info">
          <div class="video-item-title">${video.title}</div>
          <div class="video-item-stats">
            ${video.viewCount.toLocaleString()} views • ${video.channelName}
          </div>
        </div>
      </div>
    `).join('');
  }

  document.getElementById('saved-modal').classList.add('show');
}

function closeSaved() {
  document.getElementById('saved-modal').classList.remove('show');
}

function playVideo(videoId) {
  closeSaved();

  // Find video in queue or load directly
  const video = videoQueue.find(v => v.id.videoId === videoId);
  if (video) {
    currentIndex = videoQueue.indexOf(video);
    loadVideo(video);
  } else {
    player.loadVideoById(videoId);
  }
}

// Close modals on background click
document.querySelectorAll('.modal').forEach(modal => {
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.classList.remove('show');
    }
  });
});

// ============================================
// Initialization
// ============================================

window.addEventListener('load', async () => {
  // Check if user needs to provide API key
  checkAndPromptForAPIKey();

  // Load pre-fetched videos first
  const hasVideos = await loadPrefetchedVideos();

  if (hasVideos) {
    // Start with pre-fetched videos immediately
    usePrefetched = true;
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('loading').textContent = 'Loading videos...';

    // Load initial videos from prefetched
    for (let i = 0; i < 5 && i < prefetchedVideos.length; i++) {
      const video = getNextPrefetchedVideo();
      if (video) videoQueue.push(video);
    }

    // Wait for player to be ready
    if (player && player.loadVideoById) {
      if (videoQueue.length > 0) {
        loadVideo(videoQueue[0]);
        document.getElementById('loading').classList.add('hidden');
      }
    }
  } else {
    // No pre-fetched videos, check for API key
    if (!API_KEY && !useRenderAPI) {
      document.getElementById('loading').textContent = 'Please provide a YouTube API key to discover videos';
    } else {
      document.getElementById('loading').textContent = 'No videos available. Please add videos.json or configure API key.';
    }
  }
});
