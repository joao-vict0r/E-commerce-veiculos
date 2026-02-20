(function () {
  var STORAGE_KEY = 'theme_preference';
  var body = document.body;
  var toggleButton = document.getElementById('theme-toggle');

  function applyTheme(theme) {
    var isDark = theme === 'dark';
    body.classList.toggle('dark-theme', isDark);
    toggleButton.textContent = isDark ? 'Tema claro' : 'Tema escuro';
    toggleButton.setAttribute('aria-pressed', isDark ? 'true' : 'false');
  }

  var savedTheme = localStorage.getItem(STORAGE_KEY);
  if (savedTheme === 'dark' || savedTheme === 'light') {
    applyTheme(savedTheme);
  } else {
    applyTheme('light');
  }

  toggleButton.addEventListener('click', function () {
    var nextTheme = body.classList.contains('dark-theme') ? 'light' : 'dark';
    applyTheme(nextTheme);
    localStorage.setItem(STORAGE_KEY, nextTheme);
  });
})();
