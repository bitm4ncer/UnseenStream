// ============================================
// Configuration & State
// ============================================

// Render.com API Configuration
const RENDER_API_URL = localStorage.getItem('render_api_url') || '';
let useRenderAPI = RENDER_API_URL !== '';

// State
let player;
let preloadPlayer;
let videoQueue = [];
let currentIndex = 0;
let currentVideo = null;
let touchStartY = 0;
let touchEndY = 0;
let isLoading = false;
let prefetchedVideos = [];
let prefetchedIndex = 0;
let isAutoplayEnabled = false;

const DEFAULT_PREFERENCES = {
  maxViews: 1000,
  minViews: 0,
  dateRange: 7,
  patterns: ['DSC', 'IMG', 'MOV', 'VID']
};

let preferences = JSON.parse(localStorage.getItem('preferences')) || DEFAULT_PREFERENCES;

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

  if (videoQueue.length > 0) {
    loadVideo(videoQueue[0]);
    document.getElementById('loading').classList.add('hidden');
  }
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
// Video Fetching
// ============================================

async function fetchVideos() {
  if (isLoading) return;

  isLoading = true;
  document.getElementById('loading').classList.remove('hidden');

  try {
    // Try Render API first (0-1 view videos, rotates every second)
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
      console.log('Render API failed, falling back to prefetched videos');
    }

    // Fallback to prefetched videos
    if (prefetchedVideos.length > 0) {
      for (let i = 0; i < 5; i++) {
        const video = getNextPrefetchedVideo();
        if (video) videoQueue.push(video);
      }

      if (!currentVideo && videoQueue.length > 0) {
        loadVideo(videoQueue[0]);
      }

      document.getElementById('loading').classList.add('hidden');
    } else {
      const loadingEl = document.getElementById('loading');
      loadingEl.textContent = 'No videos available. Please check configuration.';
      loadingEl.style.color = '#ff4444';
    }
  } catch (error) {
    console.error('Error fetching videos:', error);
    const loadingEl = document.getElementById('loading');
    loadingEl.textContent = `Error: ${error.message}`;
    loadingEl.style.color = '#ff4444';
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
    fetchVideos();
  }

  if (currentIndex < videoQueue.length) {
    loadVideo(videoQueue[currentIndex], 'next');
  } else if (!isLoading) {
    fetchVideos();
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
  // Load pre-fetched videos
  const hasVideos = await loadPrefetchedVideos();

  if (hasVideos) {
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
    document.getElementById('loading').textContent = 'No videos available. Please check configuration.';
  }
});
