/* ============================================
   SHORTLIST - Custom JavaScript
   Animated logo with subtle interactivity
   ============================================ */

// ============ ANIMATED SHORTLIST LOGO ============
// Stylized checkmark/list icon with sparkle effects on hover
(function() {
  'use strict';

  let container = null;
  let isBuilding = false;

  // SVG for the logo icon - a stylized clipboard with checkmark
  const LOGO_ICON_SVG = `
    <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- Clipboard base -->
      <rect x="8" y="6" width="32" height="38" rx="4"
            stroke="currentColor" stroke-width="2.5" fill="none"/>
      <!-- Clipboard clip -->
      <path d="M18 6V4a2 2 0 012-2h8a2 2 0 012 2v2"
            stroke="currentColor" stroke-width="2.5" fill="none"/>
      <!-- List lines -->
      <line x1="14" y1="18" x2="26" y2="18"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
      <line x1="14" y1="26" x2="30" y2="26"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
      <line x1="14" y1="34" x2="24" y2="34"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
      <!-- Checkmark (animated on hover) -->
      <path class="check-path" d="M30 18L34 22L42 12"
            stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
            fill="none"/>
    </svg>
  `;

  function cleanup() {
    if (container && container.parentNode) {
      container.parentNode.removeChild(container);
    }
    container = null;
  }

  function buildLogo() {
    const welcomeScreen = document.querySelector('.welcome-screen');
    if (!welcomeScreen) return false;

    // Prevent multiple builds
    if (isBuilding) return false;

    // Check if our container is still in the DOM
    if (container && !document.body.contains(container)) {
      // Container was removed (e.g., navigation) - reset state
      cleanup();
    }

    // Already built and in DOM
    if (container && document.body.contains(container)) return true;

    // Check if logo already exists (prevents duplicates)
    if (document.getElementById('shortlist-logo')) return true;

    isBuilding = true;

    // Create the logo container
    container = document.createElement('div');
    container.className = 'shortlist-logo-container';
    container.id = 'shortlist-logo';

    // Build logo HTML
    container.innerHTML = `
      <div class="shortlist-logo-wrapper">
        <div class="shortlist-logo-icon">
          ${LOGO_ICON_SVG}
        </div>
        <span class="shortlist-logo-text">Shortlist</span>
      </div>
      <div class="shortlist-sparkles">
        <span class="shortlist-sparkle"></span>
        <span class="shortlist-sparkle"></span>
        <span class="shortlist-sparkle"></span>
        <span class="shortlist-sparkle"></span>
        <span class="shortlist-sparkle"></span>
        <span class="shortlist-sparkle"></span>
      </div>
      <div class="shortlist-tagline">Curate your choices</div>
    `;

    // Insert as first child of welcome screen
    welcomeScreen.insertBefore(container, welcomeScreen.firstChild);

    isBuilding = false;
    return true;
  }

  function checkLogo() {
    const welcomeScreen = document.querySelector('.welcome-screen');

    if (welcomeScreen) {
      // Welcome screen exists - ensure logo is built
      buildLogo();
    } else if (container) {
      // No welcome screen but we have a container - cleanup
      cleanup();
    }
  }

  // Initialize
  function init() {
    // Initial check with slight delay for DOM to settle
    setTimeout(checkLogo, 150);

    // Observe DOM changes for navigation
    const observer = new MutationObserver(() => {
      checkLogo();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

// ============ FAVICON SWITCHER ============
// Switches favicon based on system color scheme
(function() {
  'use strict';

  // Default favicons - update these paths when you add custom favicons
  const FAVICON_LIGHT = '/public/favicon_light.png';
  const FAVICON_DARK = '/public/favicon_dark.png';

  function setFavicon(isDark) {
    let favicon = document.querySelector('link[rel="icon"]');

    if (favicon) {
      favicon.href = isDark ? FAVICON_DARK : FAVICON_LIGHT;
    }
  }

  const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
  setFavicon(darkModeQuery.matches);
  darkModeQuery.addEventListener('change', (e) => setFavicon(e.matches));
})();

// ============ SMOOTH SCROLL FOR TABLES ============
// Adds horizontal scroll hints for wide comparison tables
(function() {
  'use strict';

  function addScrollHints() {
    document.querySelectorAll('.markdown-body table').forEach(table => {
      if (table.dataset.scrollHinted) return;
      table.dataset.scrollHinted = 'true';

      // Check if table overflows
      if (table.scrollWidth > table.clientWidth) {
        const wrapper = document.createElement('div');
        wrapper.style.cssText = `
          overflow-x: auto;
          margin: 1rem 0;
          position: relative;
        `;

        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
      }
    });
  }

  // Run on DOM changes
  const observer = new MutationObserver(addScrollHints);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      observer.observe(document.body, { childList: true, subtree: true });
      addScrollHints();
    });
  } else {
    observer.observe(document.body, { childList: true, subtree: true });
    addScrollHints();
  }
})();
