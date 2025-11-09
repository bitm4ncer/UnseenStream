// ============================================
// Configuration & State
// ============================================

// Render.com API Configuration
const RENDER_API_URL = localStorage.getItem('render_api_url') || 'https://unseenstream.onrender.com';

// State
let player;
let preloadPlayer;
let videoQueue = [];
let currentIndex = 0;
let currentVideo = null;
let touchStartY = 0;
let touchEndY = 0;
let isLoading = false;
let isAutoplayEnabled = false;
let isColdStarting = false;

// Viewed videos tracking (to prevent duplicates)
let viewedVideos = new Set(JSON.parse(localStorage.getItem('viewed_videos') || '[]'));

// Controls visibility state
let controlsVisible = true;

// ============================================
// Cold Start Detection & UI
// ============================================

async function checkServerStatus() {
  if (!RENDER_API_URL) {
    return { status: 'no_url', message: 'No API URL configured' };
  }

  try {
    console.log('Checking server status...');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000); // 10 second timeout

    const response = await fetch(`${RENDER_API_URL}/health`, {
      method: 'GET',
      signal: controller.signal
    });

    clearTimeout(timeout);

    if (response.ok) {
      return { status: 'ready', message: 'Server is ready' };
    } else {
      return { status: 'cold_start', message: 'Server is waking up' };
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      return { status: 'cold_start', message: 'Server is starting (timeout)' };
    }
    return { status: 'cold_start', message: 'Server needs to wake up' };
  }
}

function showColdStartUI(remainingSeconds) {
  const loadingEl = document.getElementById('loading');
  loadingEl.classList.remove('hidden');
  loadingEl.innerHTML = `
    <div style="text-align: center;">
      <div style="font-size: 1.2em; margin-bottom: 10px;">Server is waking up...</div>
      <div style="font-size: 2em; font-weight: bold; margin: 20px 0;">${remainingSeconds}s</div>
      <div style="width: 80%; max-width: 300px; height: 4px; background: rgba(255,255,255,0.2); border-radius: 2px; margin: 0 auto; overflow: hidden;">
        <div id="progress-bar" style="height: 100%; background: #4CAF50; border-radius: 2px; transition: width 1s linear;"></div>
      </div>
    </div>
  `;
}

async function waitForColdStart() {
  const MAX_WAIT_TIME = 90; // 90 seconds max wait
  const CHECK_INTERVAL = 2; // Check every 2 seconds
  let elapsed = 0;

  isColdStarting = true;

  while (elapsed < MAX_WAIT_TIME) {
    const remaining = MAX_WAIT_TIME - elapsed;
    showColdStartUI(remaining);

    // Update progress bar
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
      const progress = (elapsed / MAX_WAIT_TIME) * 100;
      progressBar.style.width = `${progress}%`;
    }

    // Check server status
    const status = await checkServerStatus();
    if (status.status === 'ready') {
      console.log('Server is ready!');
      isColdStarting = false;
      return true;
    }

    // Wait before next check
    await new Promise(resolve => setTimeout(resolve, CHECK_INTERVAL * 1000));
    elapsed += CHECK_INTERVAL;
  }

  isColdStarting = false;
  return false; // Timeout
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

    // Prepare request with excluded video IDs
    const excludedIds = Array.from(viewedVideos);
    const requestOptions = {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        excluded_ids: excludedIds
      }),
      signal: AbortSignal.timeout(5000) // 5 second timeout
    };

    console.log(`Excluding ${excludedIds.length} already viewed videos`);

    const response = await fetch(`${RENDER_API_URL}/current-video`, requestOptions);

    if (response.status === 503) {
      // Service not ready (pool loading)
      const data = await response.json();
      console.warn('Server pool loading:', data.message);
      return { status: 503, message: data.message };
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const video = await response.json();

    if (video.error) {
      console.warn('Render API returned error:', video.message);
      return null;
    }

    console.log('✓ Got video from Render API:', video.title, `(${video.viewCount} views)`);

    // Mark this video as viewed
    viewedVideos.add(video.id);
    localStorage.setItem('viewed_videos', JSON.stringify(Array.from(viewedVideos)));

    // Auto-reset if we've viewed too many videos (keep last 1000)
    if (viewedVideos.size > 1000) {
      const viewedArray = Array.from(viewedVideos);
      viewedVideos = new Set(viewedArray.slice(-1000));
      localStorage.setItem('viewed_videos', JSON.stringify(Array.from(viewedVideos)));
      console.log('Reset viewed videos cache (kept last 1000)');
    }

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
      autoplay: 1,
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
  } else {
    // Fetch first video if queue is empty
    fetchVideos();
  }
}

function onPlayerStateChange(event) {
  // Update play/pause button
  updatePlayPauseButton();

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
  if (isLoading || isColdStarting) return;

  if (!RENDER_API_URL) {
    const loadingEl = document.getElementById('loading');
    loadingEl.classList.remove('hidden');
    loadingEl.textContent = 'No API URL configured. Please set Render API URL in settings.';
    loadingEl.style.color = '#ff4444';
    return;
  }

  isLoading = true;
  const loadingEl = document.getElementById('loading');
  loadingEl.classList.remove('hidden');
  loadingEl.textContent = 'Loading videos...';

  try {
    const renderVideo = await fetchFromRenderAPI();

    // Handle 503 (pool loading)
    if (renderVideo && renderVideo.status === 503) {
      loadingEl.textContent = 'Server is loading video pool... Retrying in 3 seconds';
      loadingEl.style.color = 'rgba(255, 255, 255, 0.7)';
      isLoading = false;

      // Retry after 3 seconds
      setTimeout(() => fetchVideos(), 3000);
      return;
    }

    if (renderVideo) {
      videoQueue.push(renderVideo);
      if (!currentVideo && videoQueue.length > 0) {
        loadVideo(videoQueue[0]);
      }
      loadingEl.classList.add('hidden');
    } else {
      // API failed, show error
      loadingEl.textContent = 'Failed to fetch video from server. Please try again.';
      loadingEl.style.color = '#ff4444';
    }
  } catch (error) {
    console.error('Error fetching videos:', error);
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
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) {
    e.preventDefault();
  }

  if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
    nextVideo();
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
    previousVideo();
  } else if (e.key === ' ') {
    togglePlayPause();
  } else if (e.key === 's' || e.key === 'S') {
    toggleSave();
  } else if (e.key === 'h' || e.key === 'H') {
    toggleControls();
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

  // If autoplay was just enabled and video has ended, start next video
  if (isAutoplayEnabled && player && player.getPlayerState) {
    const state = player.getPlayerState();
    if (state === YT.PlayerState.ENDED) {
      nextVideo();
    }
  }
}

// Load autoplay preference on startup
function loadAutoplayPreference() {
  const savedPreference = localStorage.getItem('autoplayEnabled');
  if (savedPreference === 'true') {
    isAutoplayEnabled = true;
    const autoplayBtn = document.getElementById('autoplay-btn');
    if (autoplayBtn) {
      autoplayBtn.classList.add('active');
    }
  }
}

// Call this when the page loads
window.addEventListener('DOMContentLoaded', loadAutoplayPreference);

// ============================================
// UI Controls
// ============================================

function toggleControls() {
  controlsVisible = !controlsVisible;
  const controls = document.getElementById('controls');
  const fadeBtn = document.getElementById('fade-btn');

  controls.classList.toggle('hidden', !controlsVisible);
  fadeBtn.classList.toggle('rotated', !controlsVisible);
  document.body.classList.toggle('controls-visible', controlsVisible);
}

// Initialize controls visibility on load
window.addEventListener('DOMContentLoaded', () => {
  document.body.classList.add('controls-visible');
});

function togglePlayPause() {
  if (!player || !player.getPlayerState) return;

  const state = player.getPlayerState();
  const playPauseBtn = document.getElementById('play-pause-btn');

  if (state === YT.PlayerState.PLAYING) {
    player.pauseVideo();
    playPauseBtn.classList.remove('playing');
  } else {
    player.playVideo();
    playPauseBtn.classList.add('playing');
  }
}

// Update play/pause button state when player state changes
function updatePlayPauseButton() {
  if (!player || !player.getPlayerState) return;

  const state = player.getPlayerState();
  const playPauseBtn = document.getElementById('play-pause-btn');

  if (state === YT.PlayerState.PLAYING) {
    playPauseBtn.classList.add('playing');
  } else {
    playPauseBtn.classList.remove('playing');
  }
}

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
// Welcome Modal (First Visit)
// ============================================

function showWelcome() {
  document.getElementById('welcome-modal').classList.add('show');
}

function closeWelcome() {
  document.getElementById('welcome-modal').classList.remove('show');
  localStorage.setItem('hasVisited', 'true');

  // Start playing the first video if it's loaded
  if (player && player.playVideo && currentVideo) {
    player.playVideo();
  }
}

// Check if first visit
function checkFirstVisit() {
  const hasVisited = localStorage.getItem('hasVisited');
  if (!hasVisited) {
    // Wait a moment for the page to settle, then show welcome
    setTimeout(() => {
      showWelcome();
    }, 500);
  }
}

// ============================================
// Initialization
// ============================================

window.addEventListener('load', async () => {
  const loadingEl = document.getElementById('loading');
  loadingEl.classList.remove('hidden');

  // Check for first visit
  checkFirstVisit();

  if (!RENDER_API_URL) {
    loadingEl.textContent = 'No API URL configured. Please set Render API URL in settings.';
    loadingEl.style.color = '#ff4444';
    return;
  }

  loadingEl.textContent = 'Checking server status...';

  // Check if server is ready or needs cold start
  const status = await checkServerStatus();

  if (status.status === 'ready') {
    // Server is ready, fetch videos immediately
    console.log('Server is ready, fetching videos...');
    loadingEl.textContent = 'Loading videos...';
    await fetchVideos();
  } else if (status.status === 'cold_start') {
    // Server needs to wake up
    console.log('Server is cold starting...');
    const success = await waitForColdStart();

    if (success) {
      loadingEl.textContent = 'Loading videos...';
      await fetchVideos();
    } else {
      loadingEl.textContent = 'Server startup timeout. Please refresh the page.';
      loadingEl.style.color = '#ff4444';
    }
  } else {
    loadingEl.textContent = status.message;
    loadingEl.style.color = '#ff4444';
  }
});
