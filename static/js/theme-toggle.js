(function () {
  if (window.__themeToggleInitialized) {
    return;
  }
  window.__themeToggleInitialized = true;

  var STORAGE_KEY = 'theme_preference';
  var body = document.body;
  if (!body) {
    return;
  }

  var SUN_ICON = '<svg viewBox="0 0 24 24" class="theme-toggle-icon" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v3M12 19v3M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M2 12h3M19 12h3M4.93 19.07l2.12-2.12M16.95 7.05l2.12-2.12"></path></svg>';
  var MOON_ICON = '<svg viewBox="0 0 24 24" class="theme-toggle-icon theme-toggle-icon-moon" aria-hidden="true"><path d="M21 14.5A9 9 0 1 1 9.5 3a7 7 0 1 0 11.5 11.5z"></path></svg>';

  function readTheme() {
    try {
      var value = localStorage.getItem(STORAGE_KEY);
      return value === 'dark' ? 'dark' : 'light';
    } catch (error) {
      return 'light';
    }
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
      // Ignore storage failures (private mode, blocked storage, etc.)
    }
  }

  function getToggleButton() {
    var existing = document.querySelector('[data-theme-toggle], #theme-toggle');
    if (existing) {
      existing.setAttribute('data-theme-toggle', '');
      return existing;
    }

    var button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('data-theme-toggle', '');
    body.appendChild(button);
    return button;
  }

  var toggleButton = getToggleButton();

  function applyTheme(theme) {
    var isDark = theme === 'dark';
    body.classList.toggle('dark-theme', isDark);

    toggleButton.innerHTML = isDark ? SUN_ICON : MOON_ICON;
    toggleButton.setAttribute('aria-pressed', isDark ? 'true' : 'false');
    toggleButton.setAttribute('aria-label', isDark ? 'Ativar tema claro' : 'Ativar tema escuro');
    toggleButton.setAttribute('title', isDark ? 'Tema claro' : 'Tema escuro');
  }

  var currentTheme = readTheme();
  applyTheme(currentTheme);

  toggleButton.addEventListener('click', function () {
    currentTheme = body.classList.contains('dark-theme') ? 'light' : 'dark';
    applyTheme(currentTheme);
    saveTheme(currentTheme);
  });
})();
