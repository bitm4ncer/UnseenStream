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
let currentProvider = 'youtube';

const PROVIDER_LABELS = {
  youtube: 'YouTube',
  archive: 'Archive',
};

const isTouchDevice =
  window.matchMedia('(pointer: coarse)').matches ||
  new URLSearchParams(window.location.search).has('touch');

// Zuletzt gesehene Uploader: verhindert, dass kurz hintereinander mehrere
// Videos derselben Quelle auftauchen.
const CHANNEL_COOLDOWN = 50;
let recentChannels = JSON.parse(
  localStorage.getItem('recent_channels') || '[]'
);

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
        exclude_channels: recentChannels,
        source: sourceParam(),
        sort: sortMode,
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
    return mapApiVideo(video);
  } catch (error) {
    console.warn('Video-Abruf fehlgeschlagen:', error.message);
    return null;
  }
}

function mapApiVideo(video) {
  return {
    id: { videoId: video.id },
    provider: video.provider || 'youtube',
    mediaUrl: video.mediaUrl || null,
    channelId: video.channelId || null,
    snippet: {
      title: video.title,
      channelTitle: video.channelTitle,
      publishedAt: video.publishedAt,
      thumbnails: {
        medium: { url: video.thumbnail },
      },
    },
    statistics: {
      viewCount: String(video.viewCount ?? 0),
    },
  };
}

async function fetchSharedVideo(videoId) {
  try {
    const response = await fetch(`/video/${encodeURIComponent(videoId)}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) return null;
    return mapApiVideo(await response.json());
  } catch (error) {
    return null;
  }
}

// ============================================
// Analytics (Umami)
// ============================================

const pendingEvents = [];

function track(event, data) {
  try {
    if (window.umami && typeof window.umami.track === 'function') {
      window.umami.track(event, data);
      return;
    }

    // Umami laedt deferred: fruehe Events kurz puffern.
    if (pendingEvents.length < 20) {
      pendingEvents.push([event, data]);
    }
  } catch (error) {
    /* Analytics darf die App niemals brechen. */
  }
}

window.addEventListener('load', () => {
  if (!window.umami || typeof window.umami.track !== 'function') return;
  pendingEvents.splice(0).forEach(([event, data]) => {
    try {
      window.umami.track(event, data);
    } catch (error) {
      /* egal */
    }
  });
});

// ============================================
// Zeit-Helfer
// ============================================

function formatAge(iso) {
  const timestamp = Date.parse(iso);
  if (Number.isNaN(timestamp)) return '';

  const hours = (Date.now() - timestamp) / 36e5;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;

  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;

  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;

  return `${Math.round(months / 12)}y ago`;
}

// ============================================
// YouTube Player Setup
// ============================================

// Untertitel sind bei allen Videos aus: Modul entladen, damit YouTube sie
// auch bei aktivierten CC nicht wieder einblendet. YouTube laedt das Modul
// nach jedem Videowechsel neu, deshalb mehrfach nachfassen.
function disableCaptions(target) {
  if (!target) return;

  try {
    target.unloadModule('captions');
  } catch (error) {
    /* Player noch nicht bereit */
  }
  try {
    target.unloadModule('cc');
  } catch (error) {
    /* Modul nicht geladen */
  }
  try {
    target.setOption('captions', 'track', {});
  } catch (error) {
    /* aeltere Player-Versionen */
  }
  try {
    target.setOption('cc', 'track', {});
  } catch (error) {
    /* Modul nicht geladen */
  }
}

function suppressCaptions(target) {
  [0, 500, 1500, 3000, 6000].forEach((delay) => {
    setTimeout(() => disableCaptions(target), delay);
  });
}

function onYouTubeIframeAPIReady() {  player = new YT.Player('player', {
    height: '100%',
    width: '100%',
    playerVars: {
      autoplay: 1,
      controls: isTouchDevice ? 0 : 1,
      modestbranding: 1,
      rel: 0,
      playsinline: 1,
      cc_load_policy: 0,
      iv_load_policy: 3,
      disablekb: 1,
      fs: 0
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
  suppressCaptions(event.target);

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
    // YouTube aktiviert CC beim Start gelegentlich wieder.
    disableCaptions(event.target);
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
  let fetched = 0;
  const loadingEl = document.getElementById('loading');
  loadingEl.classList.remove('hidden');
  loadingEl.textContent = 'Loading videos...';
  loadingEl.style.color = 'rgba(255, 255, 255, 0.7)';

  let poolMessage = null;

  try {
    // Auffuellen bis drei Videos voraus gepuffert sind. Jeder Abruf
    // verbraucht serverseitig ein Video, deshalb genau die Tiefe, die
    // wirklich gebraucht wird.
    while (videoQueue.length - currentIndex - 1 < PRELOAD_AHEAD) {
      const video = await fetchNextVideo();
      if (!video) break;

      if (video.status === 503) {
        // Kein Kandidat mehr: das ist kein Video-Objekt, sonst kracht
        // loadVideo() beim Zugriff auf video.id.
        poolMessage = video.message;
        break;
      }

      videoQueue.push(video);
      rememberChannel(video);
      fetched++;

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
        poolMessage ||
        'Noch keine Videos im Pool – der Sammler läuft gerade an.';
    }
  } catch (error) {
    console.error('Error fetching videos:', error);
    loadingEl.textContent = `Error: ${error.message}`;
    loadingEl.style.color = '#ff4444';
  } finally {
    isLoading = false;
    if (fetched) refreshUnseenCount();
  }
}

function rememberChannel(video) {
  const key = video.channelId || video.snippet?.channelTitle;
  if (!key) return;

  recentChannels = [
    key,
    ...recentChannels.filter((entry) => entry !== key),
  ].slice(0, CHANNEL_COOLDOWN);

  localStorage.setItem('recent_channels', JSON.stringify(recentChannels));
}

function renderStats(video) {
  if (!video) return;

  const statsEl = document.getElementById('video-stats');
  if (!statsEl) return;

  const channelName = video.snippet.channelTitle;
  const viewCount = parseInt(video.statistics?.viewCount || 0);
  const publishedAt = video.snippet.publishedAt;
  const age = formatAge(publishedAt);

  statsEl.textContent = age
    ? `${viewCount.toLocaleString()} views • ${age} • ${channelName}`
    : `${viewCount.toLocaleString()} views • ${channelName}`;
  statsEl.title = publishedAt ? new Date(publishedAt).toLocaleString() : '';
}

// Views live nachziehen: YouTube zaehlt weiter, waehrend das Video laeuft.
async function refreshCurrentViews() {
  if (!currentVideo || currentProvider !== 'youtube') return;

  try {
    const response = await fetch(
      `/video/${encodeURIComponent(currentVideo.id.videoId)}?refresh=1`,
      { cache: 'no-store' }
    );
    if (!response.ok) return;

    const data = await response.json();
    if (typeof data.viewCount !== 'number') return;

    currentVideo.statistics = currentVideo.statistics || {};
    currentVideo.statistics.viewCount = String(data.viewCount);
    renderStats(currentVideo);
  } catch (error) {
    /* still: der Zaehler ist kein kritischer Pfad */
  }
}

setInterval(refreshCurrentViews, 60000);

function loadVideo(video, direction = 'next') {
  if (!video) return;

  currentVideo = video;
  const videoId = video.id.videoId;
  const isArchive = video.provider === 'archive';
  const playerElement = document.getElementById('player');
  const nativePlayer = document.getElementById('native-player');
  currentProvider = video.provider || 'youtube';
  resetTimeline();

  track('video', {
    provider: currentProvider,
    age: formatAge(video.snippet.publishedAt),
  });

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
        suppressCaptions(player);
      } catch (error) {
        console.error('Error loading video:', error);
        nextVideo();
        return;
      }
    }

    // Update UI
    const title = video.snippet.title;

    document.getElementById('video-title').textContent = title;
    renderStats(video);

    const sourceEl = document.getElementById('video-source');
    if (sourceEl) {
      sourceEl.textContent = PROVIDER_LABELS[currentProvider] || 'YouTube';
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
    updateDownloadButton();
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

function nextVideo(trigger = 'auto') {
  if (trigger !== 'auto') {
    track('next', { trigger, provider: currentProvider });
  }

  currentIndex++;

  if (currentIndex < videoQueue.length) {
    loadVideo(videoQueue[currentIndex], 'next');
  }

  preloadUpcoming();
  fetchVideos();
  updateNavigationButtons();
}

function previousVideo(trigger = 'auto') {
  if (trigger !== 'auto') {
    track('previous', { trigger, provider: currentProvider });
  }

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

function handleSwipe() {  const swipeDistanceX = touchStartX - touchEndX;
  const swipeDistanceY = touchStartY - touchEndY;
  const threshold = 50;

  // Determine if swipe is more horizontal or vertical
  const absX = Math.abs(swipeDistanceX);
  const absY = Math.abs(swipeDistanceY);

  // Vertical swipe (up/down)
  if (absY > absX && absY > threshold) {
    if (swipeDistanceY > 0) {
      // Swipe up - next video
      nextVideo('swipe');
    } else {
      // Swipe down - previous video
      previousVideo('swipe');
    }
  }
  // Horizontal swipe (left/right)
  else if (absX > absY && absX > threshold) {
    if (swipeDistanceX > 0) {
      // Swipe left - next video
      nextVideo('swipe');
    } else {
      // Swipe right - previous video
      previousVideo('swipe');
    }
  }
}

// Tippen auf das Video: Play/Pause. Die Ebene liegt ueber dem YouTube-iframe,
// damit Swipes ueberhaupt ankommen.
const swipeLayer = document.getElementById('swipe-layer');

if (swipeLayer) {
  let tapStartX = 0;
  let tapStartY = 0;
  let tapStartedAt = 0;

  swipeLayer.addEventListener(
    'touchstart',
    (event) => {
      const touch = event.changedTouches[0];
      tapStartX = touch.screenX;
      tapStartY = touch.screenY;
      tapStartedAt = Date.now();
    },
    { passive: true }
  );

  swipeLayer.addEventListener(
    'touchend',
    (event) => {
      const touch = event.changedTouches[0];
      const movedX = Math.abs(tapStartX - touch.screenX);
      const movedY = Math.abs(tapStartY - touch.screenY);

      if (movedX < 10 && movedY < 10 && Date.now() - tapStartedAt < 400) {
        togglePlayPause('tap');
      }
    },
    { passive: true }
  );
}

// Keyboard support for desktop
document.addEventListener('keydown', (e) => {
  // Prevent default arrow key behavior (scrolling)
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) {
    e.preventDefault();
  }

  if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
    nextVideo('keyboard');
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
    previousVideo('keyboard');
  } else if (e.key === ' ') {
    togglePlayPause('keyboard');
  } else if (e.key === 's' || e.key === 'S') {
    toggleSave('keyboard');
  } else if (e.key === 'h' || e.key === 'H') {
    toggleControls();
  }
});

// ============================================
// Save Functionality
// ============================================

function toggleSave(trigger = 'button') {
  if (!currentVideo) return;

  const savedVideos = getSavedVideos();
  const videoId = currentVideo.id.videoId;
  const existingIndex = savedVideos.findIndex(v => v.id === videoId);

  track(existingIndex >= 0 ? 'unsave' : 'save', {
    trigger,
    provider: currentVideo.provider || 'youtube',
  });

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

// Download: archive.org liefert die Datei direkt (CORS), YouTube nur ueber
// den Server (/download/<id>), weil es keine oeffentliche Datei-URL gibt.
function updateDownloadButton() {
  const button = document.getElementById('download-btn');
  if (!button) return;

  const canDownload =
    !!currentVideo &&
    (currentVideo.provider === 'youtube' ||
      (currentVideo.provider === 'archive' && !!currentVideo.mediaUrl));

  button.disabled = !canDownload;
  button.title = canDownload ? 'Download video' : 'Download not available';
}

function downloadFileName(title) {
  const cleaned = (title || 'video')
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80);
  return `${cleaned || 'video'}.mp4`;
}

async function downloadCurrent() {
  if (!currentVideo) return;

  const button = document.getElementById('download-btn');
  const filename = downloadFileName(currentVideo.snippet.title);

  // YouTube: der Server holt die Datei mit yt-dlp. Als Blob, damit ein
  // Fehler (Bot-Check) als Toast ankommt statt als JSON-Seite im Browser.
  if (currentVideo.provider === 'youtube') {
    if (button) {
      button.disabled = true;
      button.title = 'Preparing download…';
    }

    try {
      const response = await fetch(
        `/download/${encodeURIComponent(currentVideo.id.videoId)}`
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
      track('download', { provider: 'youtube', ok: true });
    } catch (error) {
      console.warn('YouTube-Download fehlgeschlagen:', error);
      showToast('Download failed – YouTube blocked this one');
      track('download', { provider: 'youtube', ok: false });
    } finally {
      updateDownloadButton();
    }

    return;
  }

  if (currentVideo.provider !== 'archive' || !currentVideo.mediaUrl) {
    return;
  }

  const url = currentVideo.mediaUrl;

  if (button) {
    button.disabled = true;
    button.title = 'Downloading…';
  }

  try {
    // CORS erlaubt den direkten Abruf; als Blob speichern erzwingt den
    // Download auch bei fremder Origin.
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    track('download', { provider: 'archive', ok: true });
  } catch (error) {
    console.warn('Download fehlgeschlagen, oeffne Datei direkt:', error);
    track('download', { provider: 'archive', ok: false });
    window.open(url, '_blank', 'noopener');
  } finally {
    updateDownloadButton();
  }
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

  track('autoplay', { enabled: isAutoplayEnabled });

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

  track('controls-toggle', { visible: controlsVisible });
}

// Initialize controls visibility on load
window.addEventListener('DOMContentLoaded', () => {
  document.body.classList.add('controls-visible');
  // Initialize navigation buttons as disabled until videos load
  updateNavigationButtons();
});

function togglePlayPause(trigger = 'button') {
  if (currentProvider === 'archive') {
    const native = document.getElementById('native-player');
    if (!native || !native.src) return;
    if (native.paused) {
      native.play().catch(() => {});
      track('play-pause', { trigger, provider: 'archive', playing: true });
    } else {
      native.pause();
      track('play-pause', { trigger, provider: 'archive', playing: false });
    }
    return;
  }

  if (!player || !player.getPlayerState) return;

  const state = player.getPlayerState();
  const playPauseBtn = document.getElementById('play-pause-btn');

  if (state === YT.PlayerState.PLAYING) {
    player.pauseVideo();
    if (playPauseBtn) playPauseBtn.classList.remove('playing');
    track('play-pause', { trigger, provider: 'youtube', playing: false });
  } else {
    player.playVideo();
    if (playPauseBtn) playPauseBtn.classList.add('playing');
    track('play-pause', { trigger, provider: 'youtube', playing: true });
  }
}

// Update play/pause button state when player state changes
function updatePlayPauseButton() {
  if (currentProvider !== 'youtube') return; // steuern native Player bzw. Embed
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
            ${viewedVideos.has(video.id) ? 'seen' : `${video.viewCount.toLocaleString()} views`} • ${video.channelName}
          </div>
        </div>
      </div>
    `).join('');
  }

  document.getElementById('saved-modal').classList.add('show');
  track('library-open', { saved: savedVideos.length });
}

function exportSaved() {
  const saved = getSavedVideos();
  const blob = new Blob([JSON.stringify(saved, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'unseen-bookmarks.json';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  track('library-export', { saved: saved.length });
}

async function copyShareLink() {
  if (!currentVideo) return;

  const id = currentVideo.id.videoId;
  const url =
    currentVideo.provider === 'archive'
      ? `https://archive.org/details/${encodeURIComponent(id)}`
      : `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;

  try {
    await navigator.clipboard.writeText(url);
    showToast('Link copied');
  } catch (error) {
    // Fallback: unsichtbares Feld + execCommand.
    const field = document.createElement('textarea');
    field.value = url;
    field.style.position = 'fixed';
    field.style.opacity = '0';
    document.body.appendChild(field);
    field.select();
    try {
      document.execCommand('copy');
      showToast('Link copied');
    } catch (copyError) {
      showToast('Could not copy link');
    }
    field.remove();
  }

  track('share', { provider: currentProvider });
}

let toastTimer = null;

function showToast(message) {
  let toast = document.getElementById('toast');
  if (!toast) return;

  toast.textContent = message;
  toast.classList.add('show');

  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2000);
}

function closeSaved() {
  document.getElementById('saved-modal').classList.remove('show');
  track('library-close');
}

function playVideo(videoId) {
  closeSaved();
  track('saved-play');

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
      provider: saved.provider,
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

  track('welcome-start');

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
// Source Filter (YouTube / archive.org)
// ============================================

const SOURCES = ['youtube', 'archive'];

function loadEnabledSources() {
  const stored = localStorage.getItem('enabled_sources');
  if (stored) {
    try {
      const list = JSON.parse(stored);
      const valid = list.filter((source) => SOURCES.includes(source));
      if (valid.length) return new Set(valid);
    } catch (error) {
      /* kaputter Wert, unten neu aufbauen */
    }
  }

  // Migration vom alten Einzel-Filter.
  const legacy = localStorage.getItem('source_filter');
  if (legacy === 'youtube') return new Set(['youtube']);
  if (legacy === 'archive') return new Set(['archive']);
  return new Set(SOURCES);
}

let enabledSources = loadEnabledSources();

function sourceParam() {
  if (enabledSources.size === SOURCES.length) return 'all';
  // CSV, damit auch "2 von 3 an" abbildbar ist.
  return SOURCES.filter((source) => enabledSources.has(source)).join(',');
}

function updateSourceButtons() {
  document.querySelectorAll('#source-toggle .source-btn').forEach((button) => {
    const enabled = enabledSources.has(button.dataset.source);
    button.classList.toggle('active', enabled);
    button.setAttribute('aria-pressed', String(enabled));
  });
}

// Quellen, die der Server gar nicht bedient, werden ausgeblendet statt einen
// leeren Feed anzubieten.
async function syncAvailableSources() {
  try {
    const response = await fetch('/sources', { cache: 'no-store' });
    if (!response.ok) return;

    const data = await response.json();
    const available = new Set(data.providers || SOURCES);

    document.querySelectorAll('#source-toggle .source-btn').forEach((button) => {
      const source = button.dataset.source;
      const usable = available.has(source);
      button.hidden = !usable;
      if (!usable) enabledSources.delete(source);
    });

    if (enabledSources.size === 0) {
      available.forEach((source) => enabledSources.add(source));
    }

    localStorage.setItem('enabled_sources', JSON.stringify([...enabledSources]));
    updateSourceButtons();
  } catch (error) {
    /* Quelle bleibt sichtbar, wenn die Abfrage scheitert. */
  }
}

function resetFeed() {
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
  refreshUnseenCount();
}

function toggleSource(source) {
  if (!SOURCES.includes(source)) return;

  if (enabledSources.has(source)) {
    // Mindestens eine Quelle bleibt aktiv.
    if (enabledSources.size === 1) return;
    enabledSources.delete(source);
  } else {
    enabledSources.add(source);
  }

  localStorage.setItem('enabled_sources', JSON.stringify([...enabledSources]));
  localStorage.removeItem('source_filter');
  updateSourceButtons();
  track('source-toggle', {
    source,
    enabled: enabledSources.has(source),
  });
  resetFeed();
}

// ============================================
// Sort order (oldest / newest first)
// ============================================

let sortMode = localStorage.getItem('sort_mode') || 'old';

function updateSortButtons() {
  document.querySelectorAll('#sort-toggle .sort-btn').forEach((button) => {
    const active = button.dataset.sort === sortMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}

function setSort(mode) {
  if (!['old', 'new'].includes(mode) || mode === sortMode) return;

  sortMode = mode;
  localStorage.setItem('sort_mode', mode);
  updateSortButtons();
  track('sort', { mode });
  resetFeed();
}

document.querySelectorAll('#sort-toggle .sort-btn').forEach((button) => {
  button.addEventListener('click', () => setSort(button.dataset.sort));
});

document.querySelectorAll('#source-toggle .source-btn').forEach((button) => {
  button.addEventListener('click', () => toggleSource(button.dataset.source));
});

window.addEventListener('DOMContentLoaded', updateSourceButtons);
window.addEventListener('DOMContentLoaded', updateSortButtons);

// ============================================
// Native player (archive.org files)
// ============================================

const nativePlayerEl = document.getElementById('native-player');

let consecutivePlaybackErrors = 0;

if (nativePlayerEl) {
  nativePlayerEl.addEventListener('play', () => {
    const btn = document.getElementById('play-pause-btn');
    if (btn) btn.classList.add('playing');
  });

  nativePlayerEl.addEventListener('playing', () => {
    consecutivePlaybackErrors = 0;
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

    consecutivePlaybackErrors += 1;
    if (consecutivePlaybackErrors > 3) {
      // Nicht endlos durch den Pool rattern, wenn der Server kaputte
      // Dateien liefert.
      console.warn('Mehrere Archive-Videos fehlgeschlagen, stoppe.');
      consecutivePlaybackErrors = 0;
      return;
    }

    console.warn('Archive-Video konnte nicht geladen werden');
    nextVideo();
  });
}

// ============================================
// Unseen Counter
// ============================================

const unseenCountEl = document.getElementById('unseen-count');

async function refreshUnseenCount() {
  if (!unseenCountEl) return;

  try {
    const source = sourceParam();
    const query = source === 'all' ? '' : `?source=${encodeURIComponent(source)}`;
    const response = await fetch(`/unseen-count${query}`, { cache: 'no-store' });
    if (!response.ok) return;

    const data = await response.json();
    if (typeof data.count !== 'number') return;

    unseenCountEl.innerHTML = `${data.count.toLocaleString('en-US')} <span class="unseen-label">unseen</span>`;
  } catch (error) {
    /* Zaehler ist ein Gimmick, Fehler bleiben still. */
  }
}

setInterval(refreshUnseenCount, 15000);

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
  updateSortButtons();
  await syncAvailableSources();

  // Check for first visit
  checkFirstVisit();

  refreshUnseenCount();

  const sharedId = new URLSearchParams(window.location.search).get('v');
  if (sharedId) {
    const shared = await fetchSharedVideo(sharedId);
    if (shared) {
      currentVideo = null;
      videoQueue = [shared];
      currentIndex = 0;
      loadVideo(shared);
    }
  }

  await fetchVideos();
});
