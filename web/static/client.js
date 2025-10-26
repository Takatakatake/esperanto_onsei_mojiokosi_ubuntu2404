(() => {
  const STORAGE_KEY = 'esperanto-caption-settings-v1';
  const MAX_HISTORY = 500;
  const LANG_LABELS = {
    ja: '日本語',
    ko: '한국어',
    en: 'English',
    eo: 'Esperanto',
  };

  const finalEl = document.getElementById('final');
  const translationsEl = document.getElementById('translations');
  const partialEl = document.getElementById('partial');
  const showPartialEl = document.getElementById('showPartial');
  const fontSizeEl = document.getElementById('fontSize');
  const historyEl = document.getElementById('history');
  const darkModeEl = document.getElementById('darkMode');
  const translationControlsEl = document.getElementById('translationControls');
  const copyHistoryBtn = document.getElementById('copyHistory');
  const downloadHistoryBtn = document.getElementById('downloadHistory');
  const clearHistoryBtn = document.getElementById('clearHistory');

  let translationTargets = [];
  let translationDefaultVisibility = {};
  let translationVisibility = {};
  let lastTranslations = {};
  const historyEntries = [];

  function labelForLang(code) {
    return LANG_LABELS[code] || code.toUpperCase();
  }

  function loadSettings() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch (err) {
      console.warn('Failed to parse stored settings', err);
      return {};
    }
  }

  const settings = loadSettings();

  function saveSettings() {
    const payload = {
      fontSize: fontSizeEl.value,
      darkMode: darkModeEl.checked,
      showPartial: showPartialEl.checked,
      translationVisibility,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }

  function setTheme() {
    document.body.classList.remove('dark', 'light');
    document.body.classList.add(darkModeEl.checked ? 'dark' : 'light');
    saveSettings();
  }

  function updateFontSizes() {
    const v = Number(fontSizeEl.value);
    finalEl.style.fontSize = `${v}px`;
    translationsEl.style.fontSize = `${Math.max(24, Math.floor(v * 0.6))}px`;
    partialEl.style.fontSize = `${Math.max(24, Math.floor(v * 0.68))}px`;
    saveSettings();
  }

  function applyPartialVisibility() {
    partialEl.style.display = showPartialEl.checked ? 'block' : 'none';
    saveSettings();
  }

  function initControlsFromSettings() {
    if (settings.fontSize) {
      fontSizeEl.value = settings.fontSize;
    }
    if (typeof settings.darkMode === 'boolean') {
      darkModeEl.checked = settings.darkMode;
    }
    if (typeof settings.showPartial === 'boolean') {
      showPartialEl.checked = settings.showPartial;
    }
    setTheme();
    updateFontSizes();
    applyPartialVisibility();
  }

  async function fetchUiConfig() {
    try {
      const res = await fetch('/config', { cache: 'no-store' });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      translationTargets = Array.isArray(data.targets) ? data.targets : [];
      translationDefaultVisibility =
        typeof data.defaultVisibility === 'object' && data.defaultVisibility
          ? data.defaultVisibility
          : {};
    } catch (err) {
      console.warn('Failed to load UI config:', err);
      translationTargets = [];
      translationDefaultVisibility = {};
    }
    initTranslationVisibility();
    renderTranslationToggles();
  }

  function initialVisibilityFor(lang) {
    if (settings.translationVisibility && typeof settings.translationVisibility[lang] === 'boolean') {
      return settings.translationVisibility[lang];
    }
    if (typeof translationDefaultVisibility[lang] === 'boolean') {
      return translationDefaultVisibility[lang];
    }
    return true;
  }

  function initTranslationVisibility() {
    translationVisibility = {};
    translationTargets.forEach((lang) => {
      translationVisibility[lang] = initialVisibilityFor(lang);
    });
  }

  function renderTranslationToggles() {
    translationControlsEl.innerHTML = '';
    if (!translationTargets.length) {
      const note = document.createElement('span');
      note.className = 'status-note';
      note.textContent = '翻訳は有効化されていません。';
      translationControlsEl.appendChild(note);
      return;
    }
    translationTargets.forEach((lang) => ensureToggle(lang));
  }

  function ensureToggle(lang) {
    if (translationControlsEl.querySelector(`[data-toggle="${lang}"]`)) {
      return;
    }
    if (!(lang in translationVisibility)) {
      translationVisibility[lang] = initialVisibilityFor(lang);
    }

    const wrapper = document.createElement('label');
    wrapper.className = 'translation-toggle';
    wrapper.dataset.toggle = lang;

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = translationVisibility[lang];
    checkbox.addEventListener('change', () => {
      translationVisibility[lang] = checkbox.checked;
      applyTranslationVisibility(lang);
      renderFinalTranslations(lastTranslations);
      saveSettings();
    });

    const text = document.createElement('span');
    text.textContent = labelForLang(lang);

    wrapper.appendChild(checkbox);
    wrapper.appendChild(text);
    translationControlsEl.appendChild(wrapper);
  }

  function applyTranslationVisibility(lang) {
    const visible = translationVisibility[lang];
    document.querySelectorAll(`[data-translation-lang="${lang}"]`).forEach((el) => {
      el.classList.toggle('hidden', !visible);
    });
  }

  function applyAllVisibility() {
    Object.keys(translationVisibility).forEach(applyTranslationVisibility);
  }

  function createTranslationLine(lang, text, options = {}) {
    const line = document.createElement('div');
    line.className = 'translation-line';
    line.dataset.translationLang = lang;

    const label = document.createElement('span');
    label.className = `translation-label badge ${lang}`;
    label.textContent = labelForLang(lang);

    const body = document.createElement('span');
    body.className = 'translation-text';
    body.textContent = text;
    if (options.placeholder) {
      body.classList.add('faint');
    }

    line.appendChild(label);
    line.appendChild(body);
    if (!translationVisibility[lang]) {
      line.classList.add('hidden');
    }
    return line;
  }

  function renderFinalTranslations(translations) {
    lastTranslations = translations || {};
    translationsEl.innerHTML = '';

    const langs = translationTargets.length
      ? Array.from(new Set([...translationTargets, ...Object.keys(lastTranslations)]))
      : Object.keys(lastTranslations);

    let visibleCount = 0;
    langs.forEach((lang) => {
      ensureToggle(lang);
      const value = lastTranslations[lang];
      const hasText = typeof value === 'string' && value.trim().length > 0;
      const text = hasText ? value : '翻訳待ち／取得できませんでした';
      const line = createTranslationLine(lang, text, { placeholder: !hasText });
      if (!(translationVisibility[lang] === false)) {
        visibleCount += 1;
      }
      translationsEl.appendChild(line);
    });
    translationsEl.style.display = visibleCount ? 'flex' : 'none';
    applyAllVisibility();
  }

  function formatHistoryEntry(speaker, text, translations) {
    const lines = [];
    lines.push(`${speaker}${text}`);
    const langs = translationTargets.length
      ? Array.from(new Set([...translationTargets, ...Object.keys(translations || {})]))
      : Object.keys(translations || {});
    langs.forEach((lang) => {
      const value = translations?.[lang];
      if (value && value.trim()) {
        lines.push(`${labelForLang(lang)}: ${value}`);
      }
    });
    return lines.join('\n');
  }

  function appendToHistory(speaker, text, translations) {
    const row = document.createElement('div');
    row.className = 'row';

    const original = document.createElement('div');
    original.className = 'history-original';
    original.innerHTML = `<span class="badge eo">Esperanto</span> ${speaker}${text}`;
    row.appendChild(original);

    const langs = translationTargets.length
      ? translationTargets
      : Object.keys(translations || {});

    if (langs.length) {
      const list = document.createElement('div');
      list.className = 'history-translations';
      langs.forEach((lang) => {
        const value = translations?.[lang];
        if (!value || !value.trim()) {
          return;
        }
        ensureToggle(lang);
        const line = createTranslationLine(lang, value);
        list.appendChild(line);
      });
      if (list.childElementCount) {
        row.appendChild(list);
      }
    }

    historyEl.prepend(row);
    historyEntries.push(formatHistoryEntry(speaker, text, translations));
    trimHistory();
    applyAllVisibility();
  }

  function trimHistory() {
    while (historyEntries.length > MAX_HISTORY) {
      historyEntries.shift();
      const lastNode = historyEl.lastChild;
      if (lastNode) historyEl.removeChild(lastNode);
    }
  }

  function clearHistory() {
    historyEntries.length = 0;
    historyEl.innerHTML = '';
  }

  function copyHistory() {
    if (!historyEntries.length) return;
    const text = historyEntries.slice().reverse().join('\n\n');
    navigator.clipboard
      .writeText(text)
      .then(() => {
        console.log('History copied to clipboard.');
      })
      .catch((err) => console.warn('Failed to copy history', err));
  }

  function downloadHistory() {
    if (!historyEntries.length) return;
    const blob = new Blob([historyEntries.slice().reverse().join('\n\n')], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    a.download = `esperanto-captions-${timestamp}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${protocol}://${location.host}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => console.log('[WS] connected');
    ws.onclose = () => {
      console.log('[WS] closed, retrying...');
      setTimeout(connectWebSocket, 1500);
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const speakerPrefix = msg.speaker ? `[${msg.speaker}] ` : '';
        if (msg.type === 'partial') {
          if (showPartialEl.checked) {
            partialEl.textContent = speakerPrefix + (msg.text || '');
          }
        } else if (msg.type === 'final') {
          const text = (msg.text || '').trim();
          finalEl.textContent = speakerPrefix + text;
          renderFinalTranslations(msg.translations || {});
          if (text) {
            appendToHistory(speakerPrefix, text, msg.translations || {});
          }
          partialEl.textContent = '';
        }
      } catch (err) {
        console.warn('Invalid WS payload', err);
      }
    };
  }

  // Event bindings
  fontSizeEl.addEventListener('input', updateFontSizes);
  darkModeEl.addEventListener('change', setTheme);
  showPartialEl.addEventListener('change', applyPartialVisibility);
  copyHistoryBtn.addEventListener('click', copyHistory);
  downloadHistoryBtn.addEventListener('click', downloadHistory);
  clearHistoryBtn.addEventListener('click', clearHistory);

  initControlsFromSettings();
  fetchUiConfig().then(() => {
    connectWebSocket();
  });
})();
