// ============================================
// Configuration & State
// ============================================

// Gleiche Origin: Frontend und API laufen hinter demselben Caddy.
const API_BASE = '';

// State
let player;
let videoQueue = [];
let currentIndex = 0;
let currentVideo = null;

// Anzahl der Videos, die im Hintergrund gepuffert werden.
const PRELOAD_AHEAD = 3;
const preloadSlots = [];
let touchStartX = 0;
let touchStartY = 0;
let touchEndX = 0;
let touchEndY = 0;
let isLoading = false;
let isAutoplayEnabled = false;
let sourceFilter = localStorage.getItem('source_filter') || 'all';
let currentProvider = 'youtube';

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
      mediaUrl: video.mediaUrl || null,
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

// Untertitel sind bei allen Videos aus: Modul entladen, damit YouTube sie
// auch bei aktivierten CC nicht wieder einblendet.
function disableCaptions(target) {
  if (!target || typeof target.unloadModule !== 'function') return;
  try {
    target.unloadModule('captions');
  } catch (error) {
    /* Player noch nicht bereit */
  }
  try {
    target.setOption('captions', 'track', {});
  } catch (error) {
    /* aeltere Player-Versionen */
  }
}

function onYouTubeIframeAPIReady() {  player = new YT.Player('player', {
    height: '100%',
    width: '100%',
    playerVars: {
      autoplay: 1,
      controls: 1,
      modestbranding: 1,
      rel: 0,
      playsinline: 1,
      cc_load_policy: 0,
      iv_load_policy: 3
    },
    events: {
      'onReady': onPlayerReady,
      'onStateChange': onPlayerStateChange,
      'onError': onPlayerError
    }
  });

  // Drei versteckte Slots: je ein YouTube-Player und ein natives Video.
  createPreloadSlots();
}

function onPlayerReady(event) {
  console.log('Player ready');
  disableCaptions(event.target);

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

  // Queue nachfuellen, sobald das Video laeuft
  if (event.data === YT.PlayerState.PLAYING) {
    preloadUpcoming();
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

function createPreloadSlots() {
  for (let index = 0; index < PRELOAD_AHEAD; index++) {
    const host = document.createElement('div');
    host.id = `preload-yt-${index}`;
    host.style.cssText =
      'position:fixed;left:-9999px;top:0;width:2px;height:2px;opacity:0;pointer-events:none;';
    document.body.appendChild(host);

    const video = document.createElement('video');
    video.muted = true;
    video.preload = 'auto';
    video.playsInline = true;
    video.style.cssText =
      'position:fixed;left:-9999px;top:0;width:2px;height:2px;opacity:0;pointer-events:none;';
    document.body.appendChild(video);

    const slot = {
      yt: null,
      ready: false,
      pendingId: null,
      video,
      currentId: null,
      currentUrl: null,
    };

    try {
      slot.yt = new YT.Player(host.id, {
      height: '1',
      width: '1',
      playerVars: {
        autoplay: 0,
        controls: 0,
        disablekb: 1,
        modestbranding: 1,
        rel: 0,
        playsinline: 1,
        cc_load_policy: 0,
      },
      events: {
        onReady: () => {
          slot.ready = true;
          if (slot.pendingId) {
            const id = slot.pendingId;
            slot.pendingId = null;
            try {
              slot.yt.cueVideoById(id);
            } catch (error) {
              /* Slot bleibt leer */
            }
          }
        },
      },
    });
    } catch (error) {
      console.warn('Preload-Slot konnte nicht erstellt werden:', error);
    }

    preloadSlots.push(slot);
  }
}

function clearPreloadSlot(slot) {
  if (!slot) return;

  if (slot.currentUrl) {
    slot.video.pause();
    slot.video.removeAttribute('src');
    slot.video.load();
    slot.currentUrl = null;
  }

  if (slot.currentId) {
    if (slot.yt) {
      try {
        slot.yt.stopVideo();
      } catch (error) {
        /* Player evtl. noch nicht bereit */
      }
    }
    slot.currentId = null;
  }
}

function preloadUpcoming() {
  for (let offset = 0; offset < PRELOAD_AHEAD; offset++) {
    const slot = preloadSlots[offset];
    if (!slot) continue;

    const video = videoQueue[currentIndex + 1 + offset];
    if (!video) {
      clearPreloadSlot(slot);
      continue;
    }

    if (video.provider === 'archive') {
      if (!video.mediaUrl) {
        clearPreloadSlot(slot);
        continue;
      }
      if (slot.currentUrl === video.mediaUrl) continue;

      if (slot.currentId) {
        if (slot.yt) {
          try {
            slot.yt.stopVideo();
          } catch (error) {
            /* ignorieren */
          }
        }
        slot.currentId = null;
      }

      slot.video.src = video.mediaUrl;
      slot.video.load();
      slot.currentUrl = video.mediaUrl;
      continue;
    }

    const id = video.id.videoId;
    if (slot.currentId === id) continue;

    if (slot.currentUrl) {
      slot.video.pause();
      slot.video.removeAttribute('src');
      slot.video.load();
      slot.currentUrl = null;
    }

    slot.currentId = id;
    if (!slot.yt) continue;
    if (slot.ready) {
      try {
        slot.yt.cueVideoById(id);
      } catch (error) {
        /* ignorieren */
      }
    } else {
      slot.pendingId = id;
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
    // Auffuellen bis drei Videos voraus gepuffert sind. Jeder Abruf
    // verbraucht serverseitig ein Video, deshalb genau die Tiefe, die
    // wirklich gebraucht wird.
    while (videoQueue.length - currentIndex - 1 < PRELOAD_AHEAD) {
      const video = await fetchNextVideo();
      if (!video) break;

      videoQueue.push(video);

      if (!currentVideo) {
        currentIndex = 0;
        loadVideo(videoQueue[0]);
      }

      updateNavigationButtons();
      preloadUpcoming();
    }

    if (videoQueue.length > 0) {
      loadingEl.classList.add('hidden');
    } else {
      loadingEl.textContent =
        'Noch keine Videos im Pool – der Sammler läuft gerade an.';
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
  const nativePlayer = document.getElementById('native-player');
  currentProvider = video.provider || 'youtube';
  resetTimeline();

  const playPauseBtn = document.getElementById('play-pause-btn');
  if (playPauseBtn) {
    playPauseBtn.classList.remove('playing');
  }

  // Determine slide direction
  const slideOutClass = direction === 'next' ? 'slide-out-up' : 'slide-out-down';
  const slideInClass = direction === 'next' ? 'slide-in-up' : 'slide-in-down';

  // Add slide-out animation
  playerElement.className = slideOutClass;

  // Wait for slide-out animation to complete, then load new video
  setTimeout(() => {
    if (isArchive) {
      if (!video.mediaUrl) {
        console.warn('Archive-Item ohne Medien-URL:', videoId);
        nextVideo();
        return;
      }
      // YouTube-iframe weiterspielen lassen waere ein Ton-Bug: hart stoppen.
      if (player && player.stopVideo) {
        try {
          player.stopVideo();
        } catch (error) {
          console.warn('stopVideo fehlgeschlagen:', error);
        }
      }
      document.body.classList.add('archive-mode');
      if (nativePlayer) {
        nativePlayer.src = video.mediaUrl;
        nativePlayer.play().catch(() => {});
      }
    } else {
      document.body.classList.remove('archive-mode');
      if (nativePlayer) {
        nativePlayer.pause();
        nativePlayer.removeAttribute('src');
        nativePlayer.load();
      }
      playerElement.style.visibility = 'visible';
      try {
        player.loadVideoById(videoId);
        disableCaptions(player);
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

    const sourceEl = document.getElementById('video-source');
    if (sourceEl) {
      sourceEl.textContent = isArchive ? 'Archive' : 'YouTube';
    }

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
    preloadUpcoming();

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

  if (currentIndex < videoQueue.length) {
    loadVideo(videoQueue[currentIndex], 'next');
  }

  preloadUpcoming();
  fetchVideos();
  updateNavigationButtons();
}

function previousVideo() {
  if (currentIndex > 0) {
    currentIndex--;
    loadVideo(videoQueue[currentIndex], 'prev');
  }

  preloadUpcoming();
  updateNavigationButtons();
}

// ============================================
// Swipe Detection
// ============================================

const container = document.getElementById('video-container');

container.addEventListener('touchstart', (e) => {
  // Beruehrungen in der Fussleiste (Timeline, Buttons) sind keine Swipes.
  if (e.target.closest('#controls')) return;
  touchStartX = e.changedTouches[0].screenX;
  touchStartY = e.changedTouches[0].screenY;
}, { passive: true });

container.addEventListener('touchend', (e) => {
  if (e.target.closest('#controls')) return;
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
      provider: currentVideo.provider || 'youtube',
      mediaUrl: currentVideo.mediaUrl || null,
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
  if (currentProvider === 'archive') {
    const native = document.getElementById('native-player');
    if (!native || !native.src) return;
    if (native.paused) {
      native.play().catch(() => {});
    } else {
      native.pause();
    }
    return;
  }

  if (!player || !player.getPlayerState) return;

  const state = player.getPlayerState();
  const playPauseBtn = document.getElementById('play-pause-btn');

  if (state === YT.PlayerState.PLAYING) {
    player.pauseVideo();
    if (playPauseBtn) playPauseBtn.classList.remove('playing');
  } else {
    player.playVideo();
    if (playPauseBtn) playPauseBtn.classList.add('playing');
  }
}

// Update play/pause button state when player state changes
function updatePlayPauseButton() {
  if (currentProvider === 'archive') return; // steuert der native Player
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
    return;
  }

  const saved = getSavedVideos().find(v => v.id === videoId);
  if (saved && saved.provider === 'archive') {
    loadVideo({
      id: { videoId: saved.id },
      provider: 'archive',
      mediaUrl: saved.mediaUrl || null,
      snippet: {
        title: saved.title,
        channelTitle: saved.channelName,
        thumbnails: { medium: { url: saved.thumbnail } },
      },
      statistics: { viewCount: String(saved.viewCount || 0) },
    });
    return;
  }

  player.loadVideoById(videoId);
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
  // Direktlink ohne Willkommensdialog, z. B. zum Teilen eines Einstiegs.
  if (new URLSearchParams(location.search).get('welcome') === '0') return;

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

  preloadSlots.forEach(clearPreloadSlot);

  document.body.classList.remove('archive-mode');
  const nativePlayer = document.getElementById('native-player');
  if (nativePlayer) {
    nativePlayer.pause();
    nativePlayer.removeAttribute('src');
    nativePlayer.load();
  }

  fetchVideos();
}

document.querySelectorAll('#source-toggle button').forEach((button) => {
  button.addEventListener('click', () => setSource(button.dataset.source));
});

window.addEventListener('DOMContentLoaded', updateSourceButtons);

// ============================================
// Native player (archive.org files)
// ============================================

const nativePlayerEl = document.getElementById('native-player');

if (nativePlayerEl) {
  nativePlayerEl.addEventListener('play', () => {
    const btn = document.getElementById('play-pause-btn');
    if (btn) btn.classList.add('playing');
  });

  nativePlayerEl.addEventListener('pause', () => {
    const btn = document.getElementById('play-pause-btn');
    if (btn) btn.classList.remove('playing');
  });

  nativePlayerEl.addEventListener('ended', () => {
    if (isAutoplayEnabled) nextVideo();
  });

  nativePlayerEl.addEventListener('error', () => {
    if (!nativePlayerEl.currentSrc) return;
    console.warn('Archive-Video konnte nicht geladen werden');
    nextVideo();
  });
}

// ============================================
// Timeline / Scrubber
// ============================================

const timelineEl = document.getElementById('timeline');
const timelineFill = document.getElementById('timeline-fill');
const timelineHead = document.getElementById('timeline-head');
let isScrubbing = false;

function mediaTime() {
  if (currentProvider === 'archive') {
    const video = document.getElementById('native-player');
    if (!video || !isFinite(video.duration) || video.duration <= 0) return null;
    return { current: video.currentTime, duration: video.duration };
  }

  if (!player || typeof player.getDuration !== 'function') return null;
  const duration = player.getDuration();
  if (!isFinite(duration) || duration <= 0) return null;
  return { current: player.getCurrentTime() || 0, duration };
}

function paintTimeline(fraction) {
  const percent = `${Math.min(1, Math.max(0, fraction)) * 100}%`;
  timelineFill.style.width = percent;
  timelineHead.style.left = percent;
  if (timelineEl) {
    timelineEl.setAttribute('aria-valuenow', String(Math.round(fraction * 100)));
  }
}

function updateTimeline() {
  if (isScrubbing) return;
  const time = mediaTime();
  if (!time) return;
  paintTimeline(time.current / time.duration);
}

function resetTimeline() {
  paintTimeline(0);
}

function seekToFraction(fraction) {
  const time = mediaTime();
  if (!time) return;

  const clamped = Math.min(0.999, Math.max(0, fraction));
  const target = clamped * time.duration;

  if (currentProvider === 'archive') {
    const video = document.getElementById('native-player');
    if (video) video.currentTime = target;
  } else if (player && typeof player.seekTo === 'function') {
    player.seekTo(target, true);
  }

  paintTimeline(clamped);
}

function fractionFromPointer(event) {
  const rect = timelineEl.getBoundingClientRect();
  if (!rect.width) return 0;
  return Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
}

if (timelineEl) {
  timelineEl.addEventListener('pointerdown', (event) => {
    if (!mediaTime()) return;
    isScrubbing = true;
    timelineEl.classList.add('dragging');
    timelineEl.setPointerCapture(event.pointerId);
    seekToFraction(fractionFromPointer(event));
  });

  timelineEl.addEventListener('pointermove', (event) => {
    if (!isScrubbing) return;
    seekToFraction(fractionFromPointer(event));
  });

  const endScrub = (event) => {
    if (!isScrubbing) return;
    isScrubbing = false;
    timelineEl.classList.remove('dragging');
    seekToFraction(fractionFromPointer(event));
  };

  timelineEl.addEventListener('pointerup', endScrub);
  timelineEl.addEventListener('pointercancel', () => {
    isScrubbing = false;
    timelineEl.classList.remove('dragging');
  });

  timelineEl.addEventListener('keydown', (event) => {
    const time = mediaTime();
    if (!time) return;
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;

    event.preventDefault();
    event.stopPropagation();
    const delta = event.key === 'ArrowRight' ? 5 : -5;
    seekToFraction((time.current + delta) / time.duration);
  });
}

setInterval(updateTimeline, 250);

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
