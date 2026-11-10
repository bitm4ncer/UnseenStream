// ============================================
// Configuration & State
// ============================================

// Gleiche Origin: Frontend und API laufen hinter demselben Caddy.
const API_BASE = '';

// State
let player;
let preloadPlayer;
let videoQueue = [];
let currentIndex = 0;
let currentVideo = null;
let touchStartX = 0;
let touchStartY = 0;
let touchEndX = 0;
let touchEndY = 0;
let isLoading = false;
let isAutoplayEnabled = false;
let sourceFilter = localStorage.getItem('source_filter') || 'all';

// Viewed videos tracking (to prevent duplicates)
let viewedVideos = new Set(JSON.parse(localStorage.getItem('viewed_videos') || '[]'));

// Controls visibility state
let controlsVisible = true;

// ============================================
// API Integration
// ============================================

async function fetchNextVideo() {
  try {
    const excludedIds = Array.from(viewedVideos);

    const response = await fetch(`${API_BASE}/current-video`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        excluded_ids: excludedIds,
        source: sourceFilter,
      }),
      signal: AbortSignal.timeout(8000),
    });

    if (response.status === 503) {
      const data = await response.json().catch(() => ({}));
      return { status: 503, message: data.message || 'Pool wird gefüllt' };
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const video = await response.json();

    return {
      id: { videoId: video.id },
      provider: video.provider || 'youtube',
      snippet: {
        title: video.title,
        channelTitle: video.channelTitle,
        thumbnails: {
          medium: { url: video.thumbnail },
        },
      },
      statistics: {
        viewCount: String(video.viewCount ?? 0),
      },
    };
  } catch (error) {
    console.warn('Video-Abruf fehlgeschlagen:', error.message);
    return null;
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
      'onStateChange': onPlayerStateChange,
      'onError': onPlayerError
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

function onPlayerError(event) {
  // 101/150: Embedding nicht erlaubt, 2/5/100: Video weg oder kaputt.
  console.warn(`Video nicht abspielbar (Code ${event.data}), weiter zum naechsten`);
  setTimeout(() => nextVideo(), 300);
}

function preloadNextVideo() {
  const nextIndex = currentIndex + 1;

  // Check if there's a next video to preload
  if (nextIndex < videoQueue.length) {
    const nextVideo = videoQueue[nextIndex];
    if (nextVideo && preloadPlayer && nextVideo.provider !== 'archive') {
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
  const loadingEl = document.getElementById('loading');
  loadingEl.classList.remove('hidden');
  loadingEl.textContent = 'Loading videos...';
  loadingEl.style.color = 'rgba(255, 255, 255, 0.7)';

  try {
    const video = await fetchNextVideo();

    if (video && video.status === 503) {
      loadingEl.textContent =
        'Noch keine Videos im Pool – der Sammler läuft gerade an.';
      setTimeout(() => fetchVideos(), 5000);
      return;
    }

    if (video) {
      videoQueue.push(video);
      if (!currentVideo && videoQueue.length > 0) {
        loadVideo(videoQueue[0]);
      }
      updateNavigationButtons();
      loadingEl.classList.add('hidden');
    } else {
      loadingEl.textContent = 'Video konnte nicht geladen werden. Nochmal versuchen?';
      loadingEl.style.color = '#ff4444';
    }
  } catch (error) {
    console.error('Error fetching videos:', error);
    loadingEl.textContent = `Error: ${error.message}`;
    loadingEl.style.color = '#ff4444';
  } finally {
    isLoading = false;
  }
}

function loadVideo(video, direction = 'next') {
  if (!video) return;

  currentVideo = video;
  const videoId = video.id.videoId;
  const isArchive = video.provider === 'archive';
  const playerElement = document.getElementById('player');
  const archivePlayer = document.getElementById('archive-player');

  // Determine slide direction
  const slideOutClass = direction === 'next' ? 'slide-out-up' : 'slide-out-down';
  const slideInClass = direction === 'next' ? 'slide-in-up' : 'slide-in-down';

  // Add slide-out animation
  playerElement.className = slideOutClass;

  // Wait for slide-out animation to complete, then load new video
  setTimeout(() => {
    if (isArchive) {
      document.body.classList.add('archive-mode');
      if (archivePlayer) {
        archivePlayer.src = `https://archive.org/embed/${encodeURIComponent(videoId)}?autoplay=1`;
      }
    } else {
      document.body.classList.remove('archive-mode');
      if (archivePlayer) {
        archivePlayer.src = 'about:blank';
      }
      playerElement.style.visibility = 'visible';
      try {
        player.loadVideoById(videoId);
      } catch (error) {
        console.error('Error loading video:', error);
        nextVideo();
        return;
      }
    }

    // Update UI
    const title = video.snippet.title;
    const channelName = video.snippet.channelTitle;
    const viewCount = parseInt(video.statistics?.viewCount || 0);

    document.getElementById('video-title').textContent = title;
    document.getElementById('video-stats').textContent =
      `${viewCount.toLocaleString()} views • ${channelName}`;

    // Mark this video as viewed (for cache/deduplication)
    viewedVideos.add(videoId);
    localStorage.setItem('viewed_videos', JSON.stringify(Array.from(viewedVideos)));

    // Auto-reset if we've viewed too many videos (keep last 1000)
    if (viewedVideos.size > 1000) {
      const viewedArray = Array.from(viewedVideos);
      viewedVideos = new Set(viewedArray.slice(-1000));
      localStorage.setItem('viewed_videos', JSON.stringify(Array.from(viewedVideos)));
      console.log('Reset viewed videos cache (kept last 1000)');
    }

    updateHeartButton();
    updateNavigationButtons();

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

function updateNavigationButtons() {
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');

  if (prevBtn) {
    prevBtn.disabled = currentIndex <= 0;
  }

  if (nextBtn) {
    // Disable next only if we're at the end of queue AND currently loading
    // This allows fetching more videos when needed
    nextBtn.disabled = (currentIndex >= videoQueue.length - 1) && isLoading;
  }
}

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

  updateNavigationButtons();
}

function previousVideo() {
  if (currentIndex > 0) {
    currentIndex--;
    loadVideo(videoQueue[currentIndex], 'prev');
  }

  updateNavigationButtons();
}

// ============================================
// Swipe Detection
// ============================================

const container = document.getElementById('video-container');

container.addEventListener('touchstart', (e) => {
  touchStartX = e.changedTouches[0].screenX;
  touchStartY = e.changedTouches[0].screenY;
}, { passive: true });

container.addEventListener('touchend', (e) => {
  touchEndX = e.changedTouches[0].screenX;
  touchEndY = e.changedTouches[0].screenY;
  handleSwipe();
}, { passive: true });

function handleSwipe() {
  const swipeDistanceX = touchStartX - touchEndX;
  const swipeDistanceY = touchStartY - touchEndY;
  const threshold = 50;

  // Determine if swipe is more horizontal or vertical
  const absX = Math.abs(swipeDistanceX);
  const absY = Math.abs(swipeDistanceY);

  // Vertical swipe (up/down)
  if (absY > absX && absY > threshold) {
    if (swipeDistanceY > 0) {
      // Swipe up - next video
      nextVideo();
    } else {
      // Swipe down - previous video
      previousVideo();
    }
  }
  // Horizontal swipe (left/right)
  else if (absX > absY && absX > threshold) {
    if (swipeDistanceX > 0) {
      // Swipe left - next video
      nextVideo();
    } else {
      // Swipe right - previous video
      previousVideo();
    }
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
  // Initialize navigation buttons as disabled until videos load
  updateNavigationButtons();
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
  if (!playPauseBtn) return;

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
// Source Filter (Alle / YouTube / Archive)
// ============================================

function updateSourceButtons() {
  document.querySelectorAll('#source-toggle button').forEach((button) => {
    button.classList.toggle('active', button.dataset.source === sourceFilter);
  });
}

function setSource(source) {
  if (!['all', 'youtube', 'archive'].includes(source)) return;
  if (source === sourceFilter) return;

  sourceFilter = source;
  localStorage.setItem('source_filter', source);
  updateSourceButtons();

  // Warteschlange verwerfen, damit der Filter sofort greift.
  videoQueue = [];
  currentIndex = 0;
  currentVideo = null;
  isLoading = false;

  document.body.classList.remove('archive-mode');
  const archivePlayer = document.getElementById('archive-player');
  if (archivePlayer) {
    archivePlayer.src = 'about:blank';
  }

  fetchVideos();
}

document.querySelectorAll('#source-toggle button').forEach((button) => {
  button.addEventListener('click', () => setSource(button.dataset.source));
});

window.addEventListener('DOMContentLoaded', updateSourceButtons);

// ============================================
// Initialization
// ============================================

window.addEventListener('load', async () => {
  const loadingEl = document.getElementById('loading');
  loadingEl.classList.remove('hidden');
  loadingEl.textContent = 'Loading videos...';

  updateSourceButtons();

  // Check for first visit
  checkFirstVisit();

  await fetchVideos();
});
