const state = {
  config: [],
  categories: [],
  activeTab: "story",
  outputs: [],
  outputFilter: "all",
  stories: [],
  lightboxImages: [],
  lightboxIndex: 0,
  playingTrack: "",
  musicToken: 0,
  remixTarget: null,
  remixTrack: "",
  publishTarget: null,
  insightsTarget: null,
  poemMode: "generate",
  poemNarrate: false,
  poemDelivery: "recitation",
  poemProvider: "edge",
  elevenVoices: null,
  poemVoiceTouched: false,
  poemBackground: null,
  poemUndrawable: [],
  imageProvider: "local",
  promptCategory: null,
  promptBaseline: "",
  settingsBaseline: {},
  settingsSection: "",
  dirty: false,
};

const STYLE_PRESETS = [
  { label: "Anime / Manga", value: "anime/manga style" },
  { label: "Realistic Historical", value: "realistic historical illustration, 7th century Arabian setting, warm earthy tones, cinematic historical drama, painterly realism" },
  { label: "Watercolor Storybook", value: "soft watercolor storybook illustration, gentle colors, hand-painted texture" },
  { label: "3D Pixar-style", value: "3D animated, Pixar-like rendering, soft global illumination, expressive characters" },
  { label: "Cinematic Realistic", value: "cinematic realistic photography style, dramatic lighting, shallow depth of field" },
  { label: "Cyberpunk", value: "cyberpunk digital art, neon lighting, futuristic cityscape, high contrast" },
  { label: "Oil Painting", value: "classical oil painting, rich brush strokes, museum lighting, renaissance palette" },
  { label: "Comic Book", value: "bold comic book art, heavy ink outlines, halftone shading, dynamic angles" },
  { label: "Minimal Vector", value: "flat minimal vector illustration, limited palette, clean geometric shapes" },
];

const SETTINGS_GROUP_META = {
  "Story & Scene Planning": { icon: "layers", description: "Turns your story text into scenes: narration lines plus image prompts." },
  "Images": { icon: "image", description: "Which service draws each scene, and which model it uses." },
  "Voice-over": { icon: "mic", description: "Text-to-speech engine used to narrate your story." },
  "Instagram": { icon: "camera", description: "Optional. Lets the app check your posting credentials. Needs a Business or Creator account." },
  "YouTube": { icon: "monitor-play", description: "Optional. Connect once to post reels as Shorts and read back their view counts." },
  "Advanced": { icon: "sliders-horizontal", description: "Low-level paths. Most people never need to touch these." },
};

const LANGUAGE_VOICE = {
  English: "en-US-AriaNeural",
  Hindi: "hi-IN-SwaraNeural",
  Hinglish: "hi-IN-SwaraNeural",
  Urdu: "ur-PK-UzmaNeural",
  Arabic: "ar-SA-ZariyahNeural",
  Bengali: "bn-IN-TanishaaNeural",
  Tamil: "ta-IN-PallaviNeural",
  Telugu: "te-IN-ShrutiNeural",
  Spanish: "es-ES-ElviraNeural",
  French: "fr-FR-DeniseNeural",
};

const ADVANCED_DEFAULTS = {
  "opt-voice-rate-range": 0,
  "opt-voice-pitch-range": 0,
  "opt-sarvam-pace": 0.9,
  "opt-sarvam-temperature": 0.9,
  "opt-size": "1920x1080",
  "opt-transition": 0.6,
  "opt-scene-pause": 0.6,
  "opt-ambience-volume": 0.1,
  "opt-music-volume": 0,
  "opt-music-preset": "",
};

function $(id) { return document.getElementById(id); }

function icon(name, size) {
  const s = size || 16;
  return `<i data-lucide="${name}" style="width:${s}px;height:${s}px"></i>`;
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function titleCase(name) {
  return name.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function toast(message, kind) {
  const el = document.createElement("div");
  el.className = kind === "error" ? "toast error" : "toast";
  el.innerHTML = `${icon(kind === "error" ? "circle-alert" : "circle-check", 16)}<span>${message}</span>`;
  $("toast-stack").appendChild(el);
  refreshIcons();
  setTimeout(() => el.remove(), 3200);
}

/* ---------------- Confirm dialog ---------------- */

let confirmResolver = null;

function closeConfirm(result) {
  $("confirm-overlay").classList.add("hidden");
  $("confirm-modal").classList.add("hidden");
  const resolve = confirmResolver;
  confirmResolver = null;
  if (resolve) resolve(result);
}

function confirmAction({ title, message, confirmLabel }) {
  if (confirmResolver) closeConfirm(false);
  $("confirm-title").textContent = title;
  $("confirm-message").textContent = message;
  $("confirm-accept").textContent = confirmLabel || "Confirm";
  $("confirm-overlay").classList.remove("hidden");
  $("confirm-modal").classList.remove("hidden");
  refreshIcons();
  $("confirm-accept").focus();
  return new Promise((resolve) => {
    confirmResolver = resolve;
  });
}

function setupConfirm() {
  $("confirm-accept").addEventListener("click", () => closeConfirm(true));
  $("confirm-cancel").addEventListener("click", () => closeConfirm(false));
  $("confirm-overlay").addEventListener("click", () => closeConfirm(false));
}

/* ---------------- Custom select ---------------- */

function enhanceSelect(select) {
  if (select.dataset.enhanced) {
    renderSelect(select);
    return;
  }
  select.dataset.enhanced = "1";

  const wrap = document.createElement("div");
  wrap.className = "select-wrap";
  select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(select);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "select-button";
  button.setAttribute("aria-expanded", "false");
  button.innerHTML = `<span class="select-value"></span>${icon("chevron-down", 15)}`;
  button.querySelector("svg, i").classList.add("chevron");

  const panel = document.createElement("div");
  panel.className = "select-panel hidden";

  wrap.appendChild(button);
  wrap.appendChild(panel);

  button.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = !panel.classList.contains("hidden");
    closeAllSelects();
    if (!isOpen) {
      panel.classList.remove("hidden");
      button.setAttribute("aria-expanded", "true");
      const active = panel.querySelector(".selected");
      if (active) active.scrollIntoView({ block: "nearest" });
    }
  });

  new MutationObserver(() => renderSelect(select)).observe(select, { childList: true });
  renderSelect(select);
}

function renderSelect(select) {
  const wrap = select.closest(".select-wrap");
  if (!wrap) return;
  const button = wrap.querySelector(".select-button");
  const panel = wrap.querySelector(".select-panel");
  const selected = select.options[select.selectedIndex];

  button.querySelector(".select-value").textContent = selected ? selected.textContent : "";

  panel.innerHTML = "";
  Array.from(select.options).forEach((option) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = option.selected ? "select-option selected" : "select-option";
    item.innerHTML = `<span>${option.textContent}</span>${option.selected ? icon("check", 14) : ""}`;
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      closeAllSelects();
      renderSelect(select);
    });
    panel.appendChild(item);
  });

  const chevron = button.querySelector(".chevron");
  if (!chevron) {
    const svg = button.querySelector("svg");
    if (svg) svg.classList.add("chevron");
  }
  refreshIcons();
  const svg = button.querySelector("svg:last-of-type");
  if (svg) svg.classList.add("chevron");
}

function closeAllSelects() {
  document.querySelectorAll(".select-panel").forEach((p) => p.classList.add("hidden"));
  document.querySelectorAll(".select-button").forEach((b) => b.setAttribute("aria-expanded", "false"));
}

function enhanceAllSelects(root) {
  (root || document).querySelectorAll("select:not(.visually-hidden)").forEach(enhanceSelect);
}

document.addEventListener("click", closeAllSelects);
document.addEventListener("click", closeAllCardMenus);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAllSelects(); });

/* ---------------- Tabs ---------------- */

const TABS = ["story", "poetry", "prompts", "settings", "outputs"];

function setupTabs() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  window.addEventListener("hashchange", () => {
    const tab = location.hash.replace("#", "");
    if (!TABS.includes(tab)) {
      history.replaceState(null, "", `#${state.activeTab}`);
      return;
    }
    if (tab !== state.activeTab) switchTab(tab);
  });
}

function switchTab(tab) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((t) => t.classList.add("hidden"));
  $(`tab-${tab}`).classList.remove("hidden");
  state.activeTab = tab;
  if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  setDirty(false);
  if (tab === "settings") loadSettings();
  if (tab === "prompts") loadPromptCategories();
  if (tab === "outputs") loadOutputs();
  window.scrollTo({ top: 0, behavior: "instant" });
}

/* ---------------- Save bar ---------------- */

function setDirty(value) {
  state.dirty = value;
  $("save-bar").classList.toggle("hidden", !value);
}

function setupSaveBar() {
  $("save-btn").addEventListener("click", async () => {
    if (state.activeTab === "prompts") await savePromptVersion();
    if (state.activeTab === "settings") await saveSettings();
  });
  $("discard-btn").addEventListener("click", () => {
    if (state.activeTab === "prompts") loadPrompt(state.promptCategory);
    if (state.activeTab === "settings") loadSettings();
    setDirty(false);
    toast("Changes discarded");
  });
}

/* ---------------- Create page ---------------- */

function setupProviderToggle() {
  document.querySelectorAll("#tts-segmented .segment").forEach((seg) => {
    seg.addEventListener("click", () => {
      document.querySelectorAll("#tts-segmented .segment").forEach((s) => s.classList.remove("active"));
      seg.classList.add("active");
      const provider = seg.dataset.value;
      $("opt-tts-provider").value = provider;

      $("edge-fields").hidden = provider !== "edge";
      $("sarvam-fields").hidden = provider !== "sarvam";
      $("indicf5-fields").hidden = provider !== "indicf5";
      $("edge-advanced-fields").hidden = provider !== "edge";
      $("sarvam-advanced-fields").hidden = provider !== "sarvam";

      previewRequestId += 1;
      stopPreviewAudio();
      $("voice-preview-panel").hidden = true;

      updateSummary();
    });
  });
}

function setupAdvancedDrawer() {
  const open = () => {
    $("advanced-drawer").classList.remove("hidden");
    $("advanced-overlay").classList.remove("hidden");
  };
  const close = () => {
    $("advanced-drawer").classList.add("hidden");
    $("advanced-overlay").classList.add("hidden");
  };
  $("open-advanced-btn").addEventListener("click", open);
  $("summary-advanced-btn").addEventListener("click", open);
  $("close-advanced-btn").addEventListener("click", close);
  $("advanced-done-btn").addEventListener("click", close);
  $("advanced-overlay").addEventListener("click", close);
  $("advanced-reset-btn").addEventListener("click", () => {
    Object.entries(ADVANCED_DEFAULTS).forEach(([id, value]) => {
      const el = $(id);
      if (!el) return;
      el.value = value;
      if (el.tagName === "SELECT") renderSelect(el);
    });
    $("opt-force-replan").checked = false;
    $("opt-force-images").checked = false;
    syncRangeOutputs();
    updateSummary();
    toast("Advanced settings reset to defaults");
  });
}

function syncRangeOutputs() {
  const rate = Number($("opt-voice-rate-range").value);
  const pitch = Number($("opt-voice-pitch-range").value);
  $("voice-rate-out").textContent = `${rate >= 0 ? "+" : ""}${rate}%`;
  $("voice-pitch-out").textContent = `${pitch >= 0 ? "+" : ""}${pitch}Hz`;
  $("opt-voice-rate").value = `${rate >= 0 ? "+" : ""}${rate}%`;
  $("opt-voice-pitch").value = `${pitch >= 0 ? "+" : ""}${pitch}Hz`;

  $("sarvam-pace-out").textContent = `${Number($("opt-sarvam-pace").value).toFixed(2)}×`;
  $("sarvam-temp-out").textContent = Number($("opt-sarvam-temperature").value).toFixed(2);
  $("transition-out").textContent = `${Number($("opt-transition").value).toFixed(1)}s`;
  $("scene-pause-out").textContent = `${Number($("opt-scene-pause").value).toFixed(1)}s`;

  const ambience = Number($("opt-ambience-volume").value);
  const music = Number($("opt-music-volume").value);
  $("ambience-out").textContent = ambience === 0 ? "Off" : `${Math.round(ambience * 100)}%`;
  $("music-out").textContent = music === 0 ? "Off" : `${Math.round(music * 100)}%`;
}

function setupRanges() {
  ["opt-voice-rate-range", "opt-voice-pitch-range", "opt-sarvam-pace", "opt-sarvam-temperature",
   "opt-transition", "opt-scene-pause", "opt-ambience-volume", "opt-music-volume"].forEach((id) => {
    $(id).addEventListener("input", () => { syncRangeOutputs(); updateSummary(); });
  });
  syncRangeOutputs();
}

function setupStylePresets() {
  const row = $("style-presets");
  STYLE_PRESETS.forEach((preset) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = preset.label;
    chip.addEventListener("click", () => {
      $("opt-style").value = preset.value;
      row.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      updateSummary();
    });
    row.appendChild(chip);
  });
  row.firstChild.classList.add("active");
}

function updateSummary() {
  const provider = $("opt-tts-provider").value;
  const musicPath = $("opt-music-preset").value;
  const voiceLabel = {
    sarvam: () => `Sarvam · ${$("opt-sarvam-speaker").value}`,
    indicf5: () => `IndicF5 · ${$("opt-indicf5-voice").value}`,
  }[provider]?.() ?? $("opt-voice").value;

  const rows = [
    ["Category", titleCase($("opt-category").value || "—")],
    ["Language", $("opt-language").value],
    ["Style", $("opt-style").value.split(",")[0]],
    ["Voice", voiceLabel],
    ["Resolution", $("opt-size").value],
    ["Music", musicPath ? musicPath.split("/").pop() : "None"],
  ];
  $("summary-list").innerHTML = rows
    .map(([k, v]) => `<div><dt>${k}</dt><dd title="${v}">${v}</dd></div>`)
    .join("");

  const words = $("story-text").value.trim().split(/\s+/).filter(Boolean).length;
  $("story-counter").textContent = `${words} word${words === 1 ? "" : "s"}`;
}

function setupSummaryWatchers() {
  ["opt-category", "opt-language", "opt-style", "opt-voice", "opt-sarvam-speaker",
   "opt-indicf5-voice", "opt-size", "opt-music-preset", "story-text"].forEach((id) => {
    $(id).addEventListener("input", updateSummary);
    $(id).addEventListener("change", updateSummary);
  });

  $("opt-language").addEventListener("change", () => {
    const match = LANGUAGE_VOICE[$("opt-language").value];
    const voice = $("opt-voice");
    if (!match || voice.value === match) return;
    if (!Array.from(voice.options).some((o) => o.value === match)) return;
    voice.value = match;
    renderSelect(voice);
    updateSummary();
    toast(`Voice switched to ${match} to match ${$("opt-language").value}`);
  });
}

/* ---------------- Data loading ---------------- */

async function loadCategoriesIntoSelect(selectEl) {
  const res = await fetch("/api/prompts");
  const data = await res.json();
  state.categories = data.categories;
  const previous = selectEl.value;
  selectEl.innerHTML = "";
  data.categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = titleCase(cat);
    selectEl.appendChild(opt);
  });
  if (previous && data.categories.includes(previous)) selectEl.value = previous;
  enhanceSelect(selectEl);
}

async function loadStoriesList() {
  const res = await fetch("/api/stories");
  const data = await res.json();
  state.stories = data.stories;
  const select = $("story-select");
  select.innerHTML = '<option value="">New story</option>';
  data.stories.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = titleCase(name);
    select.appendChild(opt);
  });
  enhanceSelect(select);
}

function setupStorySelect() {
  $("story-select").addEventListener("change", async (e) => {
    if (!e.target.value) {
      $("story-name").value = "";
      $("story-text").value = "";
      updateSummary();
      return;
    }
    const r = await fetch(`/api/stories/${e.target.value}`);
    const d = await r.json();
    $("story-name").value = d.name;
    $("story-text").value = d.text;
    updateSummary();
  });
}

async function loadMusicAssets(selectedPath) {
  const res = await fetch("/api/assets");
  const data = await res.json();
  const select = $("opt-music-preset");
  select.innerHTML = '<option value="">No music track</option>';
  data.assets.forEach((filename) => {
    const opt = document.createElement("option");
    opt.value = `assets/${filename}`;
    opt.textContent = filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
    select.appendChild(opt);
  });
  if (selectedPath) select.value = selectedPath;
  renderMusicBrowser(data.assets);
  renderPoemMusic(data.assets);
  updateSummary();
}

function renderMusicBrowser(assets) {
  const browser = $("music-browser");
  const selected = $("opt-music-preset").value;
  browser.innerHTML = "";

  const entries = [{ path: "", label: "No music track" }].concat(
    assets.map((f) => ({ path: `assets/${f}`, label: titleCase(f.replace(/\.[^.]+$/, "")) }))
  );

  entries.forEach(({ path, label }) => {
    const item = document.createElement("div");
    item.className = path === selected ? "music-item selected" : "music-item";

    const play = document.createElement("button");
    play.type = "button";
    play.className = "music-play";
    play.dataset.path = path;
    play.disabled = !path;
    play.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMusicPlayback(path);
    });

    const name = document.createElement("span");
    name.className = "music-name";
    name.textContent = label;

    item.appendChild(play);
    item.appendChild(name);
    if (path === selected) {
      const check = document.createElement("span");
      check.className = "music-check";
      check.innerHTML = icon("check", 15);
      item.appendChild(check);
    }

    item.addEventListener("click", () => {
      $("opt-music-preset").value = path;
      renderMusicBrowser(assets);
      updateSummary();
    });

    browser.appendChild(item);
  });
  syncMusicIcons();
}

function musicPlayerEl() {
  const el = $("music-preview");
  if (!el.dataset.wired) {
    el.dataset.wired = "1";
    el.addEventListener("ended", () => setPlayingTrack(""));
  }
  return el;
}

function setPlayingTrack(path) {
  state.playingTrack = path;
  syncMusicIcons();
}

function syncMusicIcons() {
  document.querySelectorAll(".music-play").forEach((btn) => {
    const path = btn.dataset.path || "";
    const playing = Boolean(path) && path === state.playingTrack;
    const wanted = path ? (playing ? "pause" : "play") : "ban";
    btn.classList.toggle("playing", playing);
    btn.title = path ? (playing ? "Stop preview" : "Play preview") : "No track to preview";
    btn.setAttribute("aria-label", btn.title);
    if (btn.dataset.icon !== wanted) {
      btn.dataset.icon = wanted;
      btn.innerHTML = icon(wanted, 13);
    }
  });
  refreshIcons();
}

function stopMusicPreview() {
  state.musicToken += 1;
  musicPlayerEl().pause();
  setPlayingTrack("");
}

function toggleMusicPlayback(path) {
  if (!path) return;
  const el = musicPlayerEl();
  if (state.playingTrack === path && !el.paused) {
    stopMusicPreview();
    return;
  }
  const token = ++state.musicToken;
  el.pause();
  el.src = `/${path}`;
  el.play()
    .then(() => {
      if (token === state.musicToken) setPlayingTrack(path);
    })
    .catch(() => {
      if (token !== state.musicToken) return;
      setPlayingTrack("");
      toast("Could not play that track", "error");
    });
}

function setupMusicUpload() {
  $("music-upload-btn").addEventListener("click", () => $("music-upload-input").click());
  $("music-upload-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    $("music-upload-btn").innerHTML = `${icon("loader-circle", 14)} Uploading...`;
    refreshIcons();
    const res = await fetch("/api/assets/upload", { method: "POST", body: formData });
    const data = await res.json();
    $("music-upload-btn").innerHTML = `${icon("upload", 14)} Upload your own track`;
    refreshIcons();
    await loadMusicAssets(data.path);
    toast("Music track uploaded");
  });
}

const PREVIEW_LANGUAGES = ["English", "Hindi", "Urdu", "Arabic", "Bengali", "Tamil", "Telugu"];

// An edge-tts voice only speaks its own locale; anything else returns no audio.
const EDGE_LOCALE_LANGUAGE = {
  en: "English",
  hi: "Hindi",
  ur: "Urdu",
  ar: "Arabic",
  bn: "Bengali",
  ta: "Tamil",
  te: "Telugu",
  es: "Spanish",
  fr: "French",
};

// Verified against the running services: these combinations return usable audio.
const PROVIDER_LANGUAGES = {
  sarvam: ["English", "Hindi", "Bengali", "Tamil", "Telugu"],
  indicf5: ["Hindi", "Bengali", "Tamil", "Telugu"],
};

// A reader is only offered when it can actually read the script on screen.
// Romanised text is read by all of them, so "latin" matches everything.
const POEM_READERS = [
  { value: "ur-PK-AsadNeural", label: "Urdu (Pakistan) \u2014 Asad, male", script: "arabic" },
  { value: "ur-PK-UzmaNeural", label: "Urdu (Pakistan) \u2014 Uzma, female", script: "arabic" },
  { value: "ur-IN-SalmanNeural", label: "Urdu (India) \u2014 Salman, male", script: "arabic" },
  { value: "ur-IN-GulNeural", label: "Urdu (India) \u2014 Gul, female", script: "arabic" },
  { value: "hi-IN-MadhurNeural", label: "Hindi \u2014 Madhur, male", script: "devanagari" },
  { value: "hi-IN-SwaraNeural", label: "Hindi \u2014 Swara, female", script: "devanagari" },
  { value: "bn-IN-BashkarNeural", label: "Bengali \u2014 Bashkar, male", script: "bengali" },
  { value: "bn-IN-TanishaaNeural", label: "Bengali \u2014 Tanishaa, female", script: "bengali" },
  { value: "en-IN-PrabhatNeural", label: "English (India) \u2014 Prabhat, male", script: "latin" },
  { value: "en-IN-NeerjaNeural", label: "English (India) \u2014 Neerja, female", script: "latin" },
];

const LANGUAGE_DEFAULT_READER = {
  Urdu: "ur-PK-AsadNeural", Hindi: "hi-IN-MadhurNeural", Hinglish: "hi-IN-MadhurNeural",
  Punjabi: "hi-IN-MadhurNeural", Bengali: "bn-IN-BashkarNeural", English: "en-IN-PrabhatNeural",
};

function previewLanguagesFor(provider) {
  if (provider === "edge") {
    const spoken = EDGE_LOCALE_LANGUAGE[currentVoiceFor("edge").split("-")[0]];
    return spoken && spoken !== "English" ? [spoken, "English"] : ["English"];
  }
  return PROVIDER_LANGUAGES[provider] || PREVIEW_LANGUAGES;
}

let previewRequestId = 0;

function stopPreviewAudio() {
  const audio = $("preview-audio");
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}

function currentVoiceFor(provider) {
  return {
    edge: () => $("opt-voice").value,
    sarvam: () => $("opt-sarvam-speaker").value,
    indicf5: () => $("opt-indicf5-voice").value,
  }[provider]();
}

function voiceLabelFor(provider) {
  const select = { edge: "opt-voice", sarvam: "opt-sarvam-speaker", indicf5: "opt-indicf5-voice" }[provider];
  const el = $(select);
  return el.options[el.selectedIndex]?.textContent || currentVoiceFor(provider);
}

function setupVoicePreview() {
  $("preview-close").addEventListener("click", () => {
    previewRequestId += 1;
    stopPreviewAudio();
    $("voice-preview-panel").hidden = true;
  });

  document.querySelectorAll(".preview-btn").forEach((btn) => {
    btn.addEventListener("click", () => openVoicePreview(btn.dataset.preview));
  });

  // Changing the selected voice invalidates whatever sample is loaded.
  ["opt-voice", "opt-sarvam-speaker", "opt-indicf5-voice"].forEach((id) => {
    $(id).addEventListener("change", () => {
      previewRequestId += 1;
      stopPreviewAudio();
      $("voice-preview-panel").hidden = true;
    });
  });
}

function openVoicePreview(provider) {
  previewRequestId += 1;
  stopPreviewAudio();

  const panel = $("voice-preview-panel");
  panel.hidden = false;
  $("preview-voice-name").textContent = voiceLabelFor(provider);

  // Only offer languages this voice can actually speak, narration language first.
  const supported = previewLanguagesFor(provider);
  const chosen = $("opt-language").value;
  const langs = supported.includes(chosen)
    ? [chosen, ...supported.filter((l) => l !== chosen)]
    : supported.slice();

  const row = $("preview-langs");
  row.innerHTML = "";
  langs.forEach((lang, i) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = i === 0 ? "chip active" : "chip";
    chip.textContent = lang;
    chip.addEventListener("click", () => {
      row.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      playVoiceSample(provider, lang);
    });
    row.appendChild(chip);
  });

  $("preview-mismatch").hidden = supported.includes(chosen);
  $("preview-mismatch-text").textContent =
    `This voice cannot narrate ${chosen}. Pick a voice that speaks ${chosen}, or change the narration language.`;

  playVoiceSample(provider, langs[0]);
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  refreshIcons();
}

async function playVoiceSample(provider, language) {
  const voice = currentVoiceFor(provider);
  const status = $("preview-status");

  previewRequestId += 1;
  const requestId = previewRequestId;
  stopPreviewAudio();
  status.textContent = `Generating a ${language} sample\u2026`;

  try {
    const res = await fetch("/api/voice-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, voice, language }),
    });
    if (requestId !== previewRequestId) return;
    if (!res.ok) throw new Error(`This voice could not produce a ${language} sample.`);
    const { url } = await res.json();
    if (requestId !== previewRequestId) return;

    const audio = $("preview-audio");
    audio.src = url;
    audio.play().catch(() => {});
    status.textContent = `${language} sample \u00b7 ${voice}`;
  } catch (err) {
    if (requestId !== previewRequestId) return;
    status.textContent = err.message;
  }
}

/* ---------------- Error banners ---------------- */

const SETTINGS_HINTS = ["settings", "api key", "token", "credits", "not set", "unauthorized", "pollinations", "gemini"];

function showErrorBanner(id, message) {
  const box = $(id);
  const text = message || "Something went wrong.";
  box.querySelector(".error-text").textContent = text;
  box.hidden = false;

  const settingsBtn = box.querySelector(".error-settings");
  settingsBtn.hidden = !SETTINGS_HINTS.some((hint) => text.toLowerCase().includes(hint));

  if (!box.dataset.wired) {
    box.dataset.wired = "1";
    settingsBtn.addEventListener("click", () => switchTab("settings"));
    box.querySelector(".error-copy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(box.querySelector(".error-text").textContent);
        toast("Error details copied");
      } catch {
        toast("Could not copy", "error");
      }
    });
  }
  refreshIcons();
}

/* ---------------- Instagram publishing ---------------- */

function setupPublish() {
  const close = () => {
    $("publish-overlay").classList.add("hidden");
    $("publish-modal").classList.add("hidden");
  };
  $("publish-close").addEventListener("click", close);
  $("publish-cancel").addEventListener("click", close);
  $("publish-overlay").addEventListener("click", close);
  $("publish-start").addEventListener("click", startPublish);
  $("publish-open-settings").addEventListener("click", () => {
    close();
    switchTab("settings");
  });
  $("publish-caption").addEventListener("input", (e) => {
    const n = e.target.value.length;
    $("publish-caption-count").textContent = `${n} / 2200`;
    $("publish-caption-count").classList.toggle("over", n > 2200);
  });
  $("publish-yt-description").addEventListener("input", (e) => {
    const n = e.target.value.length;
    $("publish-yt-description-count").textContent = `${n} / 5000`;
    $("publish-yt-description-count").classList.toggle("over", n > 5000);
  });

  const closeInsights = () => {
    $("insights-overlay").classList.add("hidden");
    $("insights-modal").classList.add("hidden");
  };
  $("insights-close").addEventListener("click", closeInsights);
  $("insights-overlay").addEventListener("click", closeInsights);
  $("insights-refresh").addEventListener("click", () => loadInsights(state.insightsTarget, true));
}

function setPublishAccount(kind, title, detail) {
  $("publish-account").className = `publish-account ${kind}`;
  $("publish-account-icon").innerHTML = icon(
    { ok: "circle-check", error: "circle-alert", loading: "loader-circle" }[kind] || "circle",
    16
  );
  $("publish-account-title").textContent = title;
  $("publish-account-detail").textContent = detail || "";
  $("publish-open-settings").hidden = kind !== "error";
  refreshIcons();
}

async function openPublishModal(name, caption, platform = "instagram") {
  state.publishTarget = name;
  state.publishPlatform = platform;
  const isYoutube = platform === "youtube";

  $("publish-title").textContent = isYoutube ? "Post as YouTube Short" : "Post to Instagram";
  $("publish-target").textContent = titleCase(name);
  $("publish-caption-row").hidden = isYoutube;
  $("publish-title-row").hidden = !isYoutube;
  $("publish-desc-row").hidden = !isYoutube;
  $("publish-privacy-row").hidden = !isYoutube;
  $("publish-warning-ig").hidden = isYoutube;
  $("publish-warning-yt").hidden = !isYoutube;

  if (isYoutube) {
    $("publish-yt-title").value = titleCase(name);
    $("publish-yt-description").value = caption || "";
    $("publish-yt-description").dispatchEvent(new Event("input"));
    $("publish-yt-privacy").value = "public";
  } else {
    $("publish-caption").value = caption || "";
    $("publish-caption").dispatchEvent(new Event("input"));
  }

  $("publish-progress-track").hidden = true;
  $("publish-status").hidden = true;
  $("publish-start").disabled = true;
  setPublishAccount("loading", "Checking your account…", "");
  $("publish-overlay").classList.remove("hidden");
  $("publish-modal").classList.remove("hidden");
  refreshIcons();

  try {
    if (isYoutube) {
      const res = await fetch("/api/youtube/test");
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not verify your connection.");
      setPublishAccount("ok", `Posting to ${data.title}`, data.subscriber_count ? `${data.subscriber_count} subscribers` : "");
    } else {
      const res = await fetch("/api/instagram/test", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not verify your credentials.");
      if (!data.can_publish) {
        throw new Error(`@${data.username} is a ${data.account_type} account. Only Business or Creator accounts can publish.`);
      }
      const quota = data.quota_total ? `${data.quota_used ?? 0} of ${data.quota_total} posts used today` : "Ready to publish";
      setPublishAccount("ok", `Posting as @${data.username}`, quota);
    }
    $("publish-start").disabled = false;
  } catch (err) {
    setPublishAccount("error", isYoutube ? "YouTube is not connected" : "Instagram is not connected", err.message);
  }
}

async function startPublish() {
  const name = state.publishTarget;
  const isYoutube = state.publishPlatform === "youtube";
  const ok = await confirmAction({
    title: isYoutube ? "Post this as a YouTube Short?" : "Post this to Instagram?",
    message: isYoutube
      ? "It goes live on your channel immediately, using the privacy level you picked above."
      : "It goes live immediately. Instagram's API cannot delete posts, so removing it later means doing it by hand in the app.",
    confirmLabel: "Post it",
  });
  if (!ok) return;

  $("publish-start").disabled = true;
  $("publish-progress-track").hidden = false;
  $("publish-status").hidden = false;
  $("publish-status").textContent = "Starting…";
  $("publish-progress-fill").style.width = "5%";
  $("publish-progress-fill").classList.remove("failed");

  const res = isYoutube
    ? await fetch(`/api/outputs/${encodeURIComponent(name)}/youtube/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: $("publish-yt-title").value,
          description: $("publish-yt-description").value,
          privacy: $("publish-yt-privacy").value,
        }),
      })
    : await fetch(`/api/outputs/${encodeURIComponent(name)}/instagram/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caption: $("publish-caption").value }),
      });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    $("publish-status").textContent = err.detail || "Could not start";
    $("publish-progress-fill").classList.add("failed");
    $("publish-start").disabled = false;
    return;
  }

  const percents = isYoutube
    ? { container: 20, uploading: 60, thumbnail: 85, done: 100 }
    : { checking: 10, container: 25, uploading: 55, processing: 80, publishing: 92, done: 100 };
  const doneLabel = isYoutube ? "Posted to YouTube" : "Posted to Instagram";
  let thumbnailNote = "";
  const { job_id } = await res.json();
  const source = new EventSource(`/api/generate/${job_id}/stream`);
  source.onmessage = async (msg) => {
    const event = JSON.parse(msg.data);
    if (event.type === "progress") {
      $("publish-status").textContent = event.message;
      const pct = percents[event.stage];
      if (pct) $("publish-progress-fill").style.width = `${pct}%`;
      if (isYoutube && event.stage === "done") {
        thumbnailNote = event.thumbnail_set
          ? ""
          : ` (custom thumbnail skipped: ${event.thumbnail_error || "channel not eligible"})`;
      }
    } else if (event.type === "complete") {
      source.close();
      $("publish-progress-fill").style.width = "100%";
      $("publish-status").textContent = doneLabel + thumbnailNote;
      toast(doneLabel + (thumbnailNote ? " \u2014 thumbnail needs phone verification" : ""));
      if (state.activeTab === "outputs") await loadOutputs();
      const publishedCurrentPoem = state.lastPoemName && name === state.lastPoemName;
      setTimeout(() => {
        $("publish-overlay").classList.add("hidden");
        $("publish-modal").classList.add("hidden");
        if (publishedCurrentPoem) resetPoemForm();
      }, thumbnailNote ? 2200 : 1200);
    } else if (event.type === "error") {
      source.close();
      $("publish-progress-fill").classList.add("failed");
      $("publish-status").textContent = event.message;
      $("publish-start").disabled = false;
    }
  };
}

const INSIGHT_LABELS = {
  views: "Views",
  reach: "Reach",
  likes: "Likes",
  comments: "Comments",
  saved: "Saves",
  shares: "Shares",
};

const YOUTUBE_INSIGHT_LABELS = {
  viewCount: "Views",
  likeCount: "Likes",
  commentCount: "Comments",
  favoriteCount: "Favorites",
  estimatedMinutesWatched: "Minutes watched",
  averageViewDuration: "Avg. view (s)",
};

async function openInsights(name, platform = "instagram") {
  state.insightsTarget = name;
  state.insightsPlatform = platform;
  $("insights-target").textContent = titleCase(name);
  $("insights-permalink-label").textContent = platform === "youtube" ? "Open on YouTube" : "Open on Instagram";
  $("insights-grid").innerHTML = "";
  $("insights-note").textContent = "Loading…";
  $("insights-overlay").classList.remove("hidden");
  $("insights-modal").classList.remove("hidden");
  refreshIcons();
  // Show what we already know, then ask the platform for fresher numbers.
  await loadInsights(name, false, platform);
  await loadInsights(name, true, platform);
}

function renderInsights(data, platform) {
  const stats = data.stats || {};
  const merged = platform === "youtube" ? { ...stats, ...(data.analytics || {}) } : stats;
  const labels = platform === "youtube" ? YOUTUBE_INSIGHT_LABELS : INSIGHT_LABELS;
  const entries = Object.entries(labels).filter(([key]) => merged[key] !== undefined);
  if (entries.length) {
    $("insights-grid").innerHTML = entries
      .map(([key, label]) => `<div class="insight-card"><div class="insight-value">${merged[key]}</div><div class="insight-label">${label}</div></div>`)
      .join("");
  }
  const link = platform === "youtube" ? data.url : data.permalink;
  $("insights-permalink").href = link || "#";
  $("insights-permalink").hidden = !link;
  return entries.length;
}

async function loadInsights(name, refresh, platform = "instagram") {
  const note = $("insights-note");
  const platformName = platform === "youtube" ? "YouTube" : "Instagram";
  if (refresh) note.textContent = `Asking ${platformName} for the latest…`;
  try {
    const path = platform === "youtube" ? "youtube" : "instagram";
    const res = await fetch(`/api/outputs/${encodeURIComponent(name)}/${path}?refresh=${refresh ? "true" : "false"}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not load insights.");

    const shown = renderInsights(data, platform);
    note.textContent = shown
      ? `Updated ${formatDate(data.stats_at) || "just now"}. ${platformName} takes a while to report numbers on a new post.`
      : `${platformName} has no numbers for this post yet. Try again in a few minutes.`;
  } catch (err) {
    // A failed refresh must not blank out figures we already have on disk.
    const hasCached = $("insights-grid").children.length > 0;
    note.textContent = hasCached ? `Showing the last saved numbers. ${err.message}` : err.message;
  }
}

/* ---------------- Poetry reel ---------------- */

const POEM_LIMITS = { max_chars: 600, max_lines: 12 };
const POEM_STYLE_PRESETS = [
  { label: "Rain & dusk", value: "cinematic atmospheric photography, rain on glass, dusk, painterly, muted blue tones" },
  { label: "Desert night", value: "vast quiet desert at night, deep indigo sky, distant stars, painterly, minimal" },
  { label: "Old Delhi", value: "old Indian street at night, warm lamplight, wet stone, cinematic, muted amber tones" },
  { label: "Misty hills", value: "misty mountain valley at dawn, soft fog, muted greens and greys, painterly" },
  { label: "Empty room", value: "empty room with a single window, dust in a shaft of light, muted warm greys, still life" },
  { label: "Ocean dark", value: "dark calm ocean at night under moonlight, long exposure, deep teal and silver" },
];

function poemLines() {
  return $("poem-text").value
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((l) => l.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean);
}

function poemDuration(lines) {
  return Math.min(60, Math.max(4, lines.length * parseFloat($("poem-pace").value)));
}

function renderPoemPreview() {
  const lines = poemLines();
  const chars = $("poem-text").value.length;
  const handle = $("poem-handle").value.trim();

  syncPoemReaders();
  $("poem-counter").textContent = `${lines.length} ${lines.length === 1 ? "line" : "lines"} · ${chars} characters`;
  $("poem-counter").classList.toggle("over", chars > POEM_LIMITS.max_chars || lines.length > POEM_LIMITS.max_lines);
  $("poem-duration-hint").textContent = lines.length
    ? `Reel will be about ${Math.round(poemDuration(lines))} seconds.`
    : "Reel length follows the number of lines.";

  const preview = $("poem-preview");
  preview.innerHTML = "";
  if (!lines.length) {
    preview.innerHTML = `<span class="poem-preview-empty">Your poem appears here</span>`;
  } else {
    lines.forEach((line) => {
      const el = document.createElement("div");
      el.className = line.length > 42 ? "poem-line wrapped" : "poem-line";
      el.textContent = line;
      el.dir = "auto";
      preview.appendChild(el);
    });
    if (handle) {
      const h = document.createElement("div");
      h.className = "poem-handle";
      h.textContent = handle;
      preview.appendChild(h);
    }
  }

  const shape = $("poem-size").options[$("poem-size").selectedIndex]?.textContent || "";
  const track = $("poem-music-browser").dataset.selected;
  const summary = [
    ["Background", state.poemMode === "upload" ? state.poemBackground?.name || "Not chosen yet" : "Generated"],
    ["Shape", shape],
    ["Voice", state.poemNarrate ? ($("poem-voice").selectedOptions[0]?.textContent || "On") : "No voice-over"],
    ["Music", track ? titleCase(track.split("/").pop().replace(/\.[^.]+$/, "")) : "None"],
    ["Length", state.poemNarrate
      ? "follows the reading"
      : (lines.length ? `${Math.round(poemDuration(lines))}s` : "—")],
  ];
  $("poem-summary").innerHTML = summary
    .map(([k, v]) => `<div class="summary-row"><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`)
    .join("");
}

function poemWarnings(lines) {
  const warnings = [];
  const chars = $("poem-text").value.length;
  const usingOwnImage = state.poemMode === "upload";

  if (!lines.length) warnings.push(["danger", "Write a line or two of poetry first."]);
  if (chars > POEM_LIMITS.max_chars) {
    warnings.push(["danger", `That is ${chars} characters. Keep it under ${POEM_LIMITS.max_chars} so the words stay readable.`]);
  }
  if (lines.length > POEM_LIMITS.max_lines) {
    warnings.push(["danger", `That is ${lines.length} lines. Keep it to ${POEM_LIMITS.max_lines} or fewer.`]);
  }
  if (usingOwnImage && !state.poemBackground) {
    warnings.push(["danger", "Choose a photo, or switch back to Generate."]);
  }
  const longest = lines.reduce((a, b) => (b.length > a.length ? b : a), "");
  if (longest.length > 48) {
    warnings.push(["warn", "One line is very long, so it may be split across two lines and lose its rhythm."]);
  }
  if (state.poemUndrawable?.length) {
    warnings.push(["warn", `These characters cannot be drawn and will be skipped: ${state.poemUndrawable.join(" ")}`]);
  }
  if (usingOwnImage && state.poemBackground) {
    const [w, h] = $("poem-size").value.split("x").map(Number);
    const yours = state.poemBackground.width / state.poemBackground.height;
    if (Math.abs(yours - w / h) > 0.25) {
      warnings.push(["info", "Your photo is a different shape. Drag it in the frame to choose what stays."]);
    }
    const cover = Math.max(w / state.poemBackground.width, h / state.poemBackground.height) * state.poemBackground.zoom;
    if (cover > 1.6) {
      warnings.push(["warn", "Your photo is being enlarged a lot, so the reel may look soft. A bigger photo or less zoom will look sharper."]);
    }
  }
  const geminiSet = state.config.find((f) => f.key === "GEMINI_API_KEY")?.is_set;
  if (!geminiSet && !usingOwnImage) {
    warnings.push(["danger", "No Gemini key is saved. Add it in Settings, it plans the image and writes the caption."]);
  } else if (!geminiSet) {
    warnings.push(["info", "No Gemini key, so the caption will just be your poem plus general hashtags."]);
  }

  if (state.poemNarrate && lines.length && state.poemProvider !== "elevenlabs" && !readersFor(scriptOf(lines.join(" "))).length) {
    warnings.push(["danger", "No free reader can read this script yet. Turn the voice-over off to carry on."]);
  }
  return warnings;
}

function scriptOf(text) {
  if (/[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF]/.test(text)) return "arabic";
  if (/[\u0900-\u097F]/.test(text)) return "devanagari";
  if (/[\u0980-\u09FF]/.test(text)) return "bengali";
  return "latin";
}

function gatherPoemOptions() {
  return {
    poem_text: $("poem-text").value,
    language: $("poem-language").value,
    style: $("poem-style").value,
    size: $("poem-size").value,
    seconds_per_line: parseFloat($("poem-pace").value),
    music_file: $("poem-music-browser").dataset.selected || null,
    music_volume: parseFloat($("poem-music-volume").value),
    handle: $("poem-handle").value.trim(),
    seed: parseInt($("poem-seed").value, 10),
    background_file: state.poemBackground?.path || null,
    focus_x: state.poemBackground?.focusX ?? 0.5,
    focus_y: state.poemBackground?.focusY ?? 0.5,
    zoom: state.poemBackground?.zoom ?? 1,
    narrate: state.poemNarrate === true,
    voice: $("poem-voice").value,
    delivery: state.poemDelivery || "recitation",
    voice_provider: state.poemProvider || "edge",
  };
}

/* Reel defaults are remembered so you never retype your handle or re-pick a track. */
const POEM_PREFS_KEY = "storytube.poem.prefs";
const POEM_PREF_FIELDS = ["poem-language", "poem-style", "poem-size", "poem-handle", "poem-music-volume", "poem-pace", "poem-seed", "poem-voice"];

function savePoemPrefs() {
  const prefs = {};
  POEM_PREF_FIELDS.forEach((id) => { prefs[id] = $(id).value; });
  prefs.music = $("poem-music-browser").dataset.selected || "";
  prefs.mode = state.poemMode || "generate";
  prefs.narrate = state.poemNarrate === true;
  prefs.delivery = state.poemDelivery || "recitation";
  prefs.provider = state.poemProvider || "edge";
  try {
    localStorage.setItem(POEM_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* private mode or full quota; defaults simply will not persist */
  }
}

function loadPoemPrefs() {
  let prefs;
  try {
    prefs = JSON.parse(localStorage.getItem(POEM_PREFS_KEY) || "{}");
  } catch {
    return {};
  }
  POEM_PREF_FIELDS.forEach((id) => {
    if (prefs[id] !== undefined && $(id)) $(id).value = prefs[id];
  });
  // The reader list is built from the poem's script, so it has no options to select yet.
  syncPoemReaders();
  const savedVoice = prefs["poem-voice"];
  if (savedVoice && [...$("poem-voice").options].some((o) => o.value === savedVoice)) {
    $("poem-voice").value = savedVoice;
  }
  if (prefs.music) $("poem-music-browser").dataset.selected = prefs.music;
  $("poem-music-out").textContent = `${Math.round($("poem-music-volume").value * 100)}%`;
  $("poem-pace-out").textContent = `${Number($("poem-pace").value).toFixed(1)}s`;
  $("poem-seed-out").textContent = $("poem-seed").value;
  return prefs;
}

function setPoemMode(mode) {
  state.poemMode = mode;
  document.querySelectorAll("#poem-bg-segmented .segment").forEach((s) =>
    s.classList.toggle("active", s.dataset.value === mode)
  );
  $("poem-bg-upload").hidden = mode !== "upload";
  $("poem-bg-generate").hidden = mode !== "generate";
  savePoemPrefs();
  renderPoemPreview();
}

/* Mirrors prepare_background(): scale to cover, multiply by zoom, then offset the
   crop window by the focus fraction. Pixel positioning keeps preview and output identical. */
function cropGeometry() {
  const bg = state.poemBackground;
  const frame = $("poem-crop-frame").getBoundingClientRect();
  const cover = Math.max(frame.width / bg.width, frame.height / bg.height) * bg.zoom;
  const displayWidth = bg.width * cover;
  const displayHeight = bg.height * cover;
  return {
    frame,
    displayWidth,
    displayHeight,
    overflowX: Math.max(0, displayWidth - frame.width),
    overflowY: Math.max(0, displayHeight - frame.height),
  };
}

function applyCrop() {
  const bg = state.poemBackground;
  if (!bg || $("poem-crop-modal").classList.contains("hidden")) return;
  const geo = cropGeometry();
  const img = $("poem-bg-thumb");
  img.style.width = `${geo.displayWidth}px`;
  img.style.height = `${geo.displayHeight}px`;
  img.style.left = `${-geo.overflowX * bg.focusX}px`;
  img.style.top = `${-geo.overflowY * bg.focusY}px`;
  $("poem-zoom-out").textContent = `${bg.zoom.toFixed(2)}×`;
}

function setupCropDragging() {
  const frame = $("poem-crop-frame");
  let dragging = null;

  frame.addEventListener("pointerdown", (e) => {
    if (!state.poemBackground) return;
    const bg = state.poemBackground;
    const geo = cropGeometry();
    dragging = { x: e.clientX, y: e.clientY, fx: bg.focusX, fy: bg.focusY, geo };
    frame.classList.add("dragging");
    frame.setPointerCapture(e.pointerId);
  });

  frame.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const bg = state.poemBackground;
    // Dragging the picture right reveals what sits to its left, hence the sign flip.
    if (dragging.geo.overflowX > 0) {
      bg.focusX = Math.min(1, Math.max(0, dragging.fx - (e.clientX - dragging.x) / dragging.geo.overflowX));
    }
    if (dragging.geo.overflowY > 0) {
      bg.focusY = Math.min(1, Math.max(0, dragging.fy - (e.clientY - dragging.y) / dragging.geo.overflowY));
    }
    applyCrop();
  });

  ["pointerup", "pointercancel", "pointerleave"].forEach((ev) =>
    frame.addEventListener(ev, () => {
      dragging = null;
      frame.classList.remove("dragging");
    })
  );

  $("poem-zoom").addEventListener("input", (e) => {
    if (!state.poemBackground) return;
    state.poemBackground.zoom = parseFloat(e.target.value);
    applyCrop();
  });

  $("poem-crop-reset").addEventListener("click", () => {
    if (!state.poemBackground) return;
    Object.assign(state.poemBackground, { focusX: 0.5, focusY: 0.5, zoom: 1 });
    $("poem-zoom").value = 1;
    applyCrop();
  });

  window.addEventListener("resize", applyCrop);
}

function syncCropFrameShape() {
  const [w, h] = $("poem-size").value.split("x").map(Number);
  $("poem-crop-frame").style.aspectRatio = `${w} / ${h}`;
  applyCrop();
}

async function uploadPoemBackground(file) {
  if (!file) return;
  if (!file.type.startsWith("image/") && !/\.(jpe?g|png|webp|heic|heif|avif|tiff?|bmp)$/i.test(file.name)) {
    toast("That is not an image file", "error");
    return;
  }
  const drop = $("poem-drop");
  drop.classList.add("dragging");
  const body = new FormData();
  body.append("file", file);
  try {
    const res = await fetch("/api/poem/background", { method: "POST", body });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    state.poemBackground = {
      path: data.path,
      url: data.url,
      name: file.name,
      width: data.width,
      height: data.height,
      focusX: 0.5,
      focusY: 0.5,
      zoom: 1,
    };
    $("poem-bg-thumb").src = data.url;
    $("poem-bg-chip").src = data.url;
    $("poem-bg-name").textContent = file.name;
    $("poem-bg-dims").textContent = `${data.width} × ${data.height}`;
    $("poem-zoom").value = 1;
    $("poem-bg-preview").hidden = false;
    drop.hidden = true;
    renderPoemPreview();
    toast("Photo ready");
  } catch (err) {
    toast(err.message, "error");
  } finally {
    drop.classList.remove("dragging");
    refreshIcons();
  }
}

function openCropModal() {
  if (!state.poemBackground) return;
  $("poem-crop-overlay").classList.remove("hidden");
  $("poem-crop-modal").classList.remove("hidden");
  syncCropFrameShape();
  refreshIcons();
}

function closeCropModal() {
  $("poem-crop-overlay").classList.add("hidden");
  $("poem-crop-modal").classList.add("hidden");
  renderPoemPreview();
}

function clearPoemBackground() {
  state.poemBackground = null;
  $("poem-bg-preview").hidden = true;
  $("poem-drop").hidden = false;
  $("poem-bg-input").value = "";
  renderPoemPreview();
}

function resetPoemForm() {
  $("poem-text").value = "";
  $("poem-text").dispatchEvent(new Event("input", { bubbles: true }));
  clearPoemBackground();
  $("poem-seed").value = 0;
  $("poem-seed-out").textContent = "0";
  $("poem-caption").value = "";
  $("poem-result-card").hidden = true;
  $("poem-progress-card").hidden = true;
  state.lastPoemName = null;
  $("poem-text").scrollIntoView({ behavior: "smooth", block: "center" });
  $("poem-text").focus();
  toast("Ready for a new poem");
}

function setPoemNarrate(on) {
  state.poemNarrate = on;
  document.querySelectorAll("#poem-voice-segmented .segment").forEach((s) =>
    s.classList.toggle("active", (s.dataset.value === "on") === on)
  );
  $("poem-voice-row").hidden = !on;
  $("poem-delivery-row").hidden = !on;
  if (!on) stopVoicePreview();
  savePoemPrefs();
  renderPoemPreview();
}

function setPoemDelivery(mode) {
  state.poemDelivery = mode;
  document.querySelectorAll("#poem-delivery-segmented .segment").forEach((s) =>
    s.classList.toggle("active", s.dataset.value === mode)
  );
  stopVoicePreview();
  savePoemPrefs();
  renderPoemPreview();
}

function readersFor(script) {
  // Verified against edge-tts: a reader returns no audio at all for a script it does not know.
  return script === "latin" ? POEM_READERS : POEM_READERS.filter((r) => r.script === script);
}

async function setPoemProvider(provider) {
  state.poemProvider = provider;
  document.querySelectorAll("#poem-provider-segmented .segment").forEach((s) =>
    s.classList.toggle("active", s.dataset.value === provider)
  );
  stopVoicePreview();
  const select = $("poem-voice");
  select.dataset.signature = "";
  if (provider === "elevenlabs") {
    $("poem-voice-help").textContent = "Your ElevenLabs voices. Each reel costs credits, roughly one per character.";
    $("poem-voice-note").hidden = true;
    if (!state.elevenVoices) {
      select.innerHTML = "";
      select.add(new Option("Loading your voices…", ""));
      enhanceAllSelects($("poem-voice-row"));
      try {
        const res = await fetch("/api/elevenlabs/voices");
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Could not reach ElevenLabs.");
        state.elevenVoices = data.voices;
      } catch (err) {
        toast(err.message, "error");
        setPoemProvider("edge");
        return;
      }
    }
    select.innerHTML = "";
    state.elevenVoices.forEach((v) => select.add(new Option(v.name, v.voice_id)));
    if (!state.elevenVoices.length) select.add(new Option("No voices in your account", ""));
    enhanceAllSelects($("poem-voice-row"));
  } else {
    $("poem-voice-help").textContent = "Free, via edge-tts. The reel length follows the reading, so pacing is ignored.";
    syncPoemReaders();
  }
  savePoemPrefs();
  renderPoemPreview();
}

function syncPoemReaders() {
  if (state.poemProvider === "elevenlabs") return;
  const select = $("poem-voice");
  const script = scriptOf($("poem-text").value);
  const allowed = readersFor(script);
  const signature = allowed.map((r) => r.value).join(",");
  if (select.dataset.signature === signature) return;
  select.dataset.signature = signature;

  const wanted = select.value;
  select.innerHTML = "";
  allowed.forEach((r) => select.add(new Option(r.label, r.value)));
  if (allowed.some((r) => r.value === wanted)) {
    select.value = wanted;
  } else {
    const fallback = LANGUAGE_DEFAULT_READER[$("poem-language").value];
    select.value = allowed.some((r) => r.value === fallback) ? fallback : allowed[0]?.value || "";
    state.poemVoiceTouched = false;
  }
  const note = $("poem-voice-note");
  note.textContent = script === "latin" ? "" : `Only the readers that can read ${titleCase(script)} script are listed.`;
  note.hidden = !note.textContent;
  stopVoicePreview();
  enhanceAllSelects($("poem-voice-row"));
}

function stopVoicePreview() {
  const audio = $("poem-voice-audio");
  audio.pause();
  audio.currentTime = 0;
  state.voicePreviewPlaying = false;
  const btn = $("poem-voice-listen");
  btn.disabled = false;
  btn.innerHTML = `${icon("volume-2", 14)} Listen`;
  refreshIcons();
}

async function previewPoemVoice() {
  if (state.voicePreviewPlaying) {
    stopVoicePreview();
    return;
  }
  const btn = $("poem-voice-listen");
  const audio = $("poem-voice-audio");
  const voice = $("poem-voice").value;
  const provider = state.poemProvider || "edge";
  // edge voices only speak their own locale; ElevenLabs takes the poem's language directly.
  const language = provider === "elevenlabs"
    ? $("poem-language").value
    : EDGE_LOCALE_LANGUAGE[voice.split("-")[0]] || "English";

  btn.disabled = true;
  btn.innerHTML = `${icon("loader-circle", 14)} Loading…`;
  refreshIcons();
  try {
    const res = await fetch("/api/voice-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, voice, language, delivery: state.poemDelivery }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "That voice could not produce a sample.");
    audio.src = data.url;
    await audio.play();
    state.voicePreviewPlaying = true;
    btn.disabled = false;
    btn.innerHTML = `${icon("square", 14)} Stop`;
    refreshIcons();
  } catch (err) {
    toast(err.message, "error");
    stopVoicePreview();
  }
}

function setupPoetry() {
  const presets = $("poem-style-presets");
  POEM_STYLE_PRESETS.forEach(({ label, value }) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = label;
    chip.addEventListener("click", () => {
      presets.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      $("poem-style").value = value;
      savePoemPrefs();
    });
    presets.appendChild(chip);
  });

  ["poem-text", "poem-handle", "poem-pace"].forEach((id) =>
    $(id).addEventListener("input", renderPoemPreview)
  );
  POEM_PREF_FIELDS.forEach((id) => $(id).addEventListener("change", savePoemPrefs));

  $("poem-pace").addEventListener("input", (e) => {
    $("poem-pace-out").textContent = `${Number(e.target.value).toFixed(1)}s`;
  });
  $("poem-music-volume").addEventListener("input", (e) => {
    $("poem-music-out").textContent = Number(e.target.value) === 0 ? "Off" : `${Math.round(e.target.value * 100)}%`;
  });
  $("poem-seed").addEventListener("input", (e) => {
    $("poem-seed-out").textContent = e.target.value;
  });

  document.querySelectorAll("#poem-bg-segmented .segment").forEach((seg) =>
    seg.addEventListener("click", () => setPoemMode(seg.dataset.value))
  );
  document.querySelectorAll("#poem-voice-segmented .segment").forEach((seg) =>
    seg.addEventListener("click", () => setPoemNarrate(seg.dataset.value === "on"))
  );
  $("poem-voice-listen").addEventListener("click", previewPoemVoice);
  $("poem-voice-audio").addEventListener("ended", stopVoicePreview);
  document.querySelectorAll("#poem-delivery-segmented .segment").forEach((seg) =>
    seg.addEventListener("click", () => setPoemDelivery(seg.dataset.value))
  );
  document.querySelectorAll("#poem-provider-segmented .segment").forEach((seg) =>
    seg.addEventListener("click", () => setPoemProvider(seg.dataset.value))
  );
  $("poem-language").addEventListener("change", () => {
    // Follow the language unless the reader was deliberately chosen.
    if (!state.poemVoiceTouched) {
      const next = LANGUAGE_DEFAULT_READER[$("poem-language").value];
      if (next && POEM_READERS.some((r) => r.value === next)) {
        $("poem-voice").value = next;
        enhanceAllSelects($("poem-voice-row"));
      }
    }
    renderPoemPreview();
  });
  $("poem-voice").addEventListener("change", () => {
    state.poemVoiceTouched = true;
    stopVoicePreview();
    renderPoemPreview();
  });

  const drop = $("poem-drop");
  drop.addEventListener("click", () => $("poem-bg-input").click());
  $("poem-bg-input").addEventListener("change", (e) => uploadPoemBackground(e.target.files[0]));
  $("poem-bg-clear").addEventListener("click", clearPoemBackground);
  $("poem-crop-open").addEventListener("click", openCropModal);
  $("poem-crop-close").addEventListener("click", closeCropModal);
  $("poem-crop-done").addEventListener("click", closeCropModal);
  $("poem-crop-overlay").addEventListener("click", closeCropModal);

  $("poem-advanced-toggle").addEventListener("click", () => {
    $("poem-advanced-overlay").classList.remove("hidden");
    $("poem-advanced-drawer").classList.remove("hidden");
    refreshIcons();
  });
  const closeAdvanced = () => {
    $("poem-advanced-overlay").classList.add("hidden");
    $("poem-advanced-drawer").classList.add("hidden");
    renderPoemPreview();
  };
  $("poem-advanced-close").addEventListener("click", closeAdvanced);
  $("poem-advanced-overlay").addEventListener("click", closeAdvanced);
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("dragging"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("dragging"); })
  );
  drop.addEventListener("drop", (e) => uploadPoemBackground(e.dataTransfer.files[0]));

  $("poem-music-upload-btn").addEventListener("click", () => $("poem-music-upload-input").click());
  $("poem-music-upload-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const btn = $("poem-music-upload-btn");
    btn.innerHTML = `${icon("loader-circle", 14)} Uploading…`;
    refreshIcons();
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch("/api/assets/upload", { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      $("poem-music-browser").dataset.selected = `assets/${data.path.split("/").pop()}`;
      await loadMusicAssets();
      savePoemPrefs();
      toast("Track added");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.innerHTML = `${icon("upload", 14)} Upload your own track`;
      refreshIcons();
      e.target.value = "";
    }
  });

  $("poem-generate-btn").addEventListener("click", openPoemReview);
  $("poem-review-back").addEventListener("click", closePoemReview);
  $("poem-review-close").addEventListener("click", closePoemReview);
  $("poem-review-overlay").addEventListener("click", closePoemReview);
  $("poem-review-start").addEventListener("click", startPoem);

  $("poem-copy-caption").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("poem-caption").value);
      toast("Caption copied");
    } catch {
      $("poem-caption").select();
      toast("Press Cmd+C to copy", "error");
    }
  });

  $("poem-redraw").addEventListener("click", () => {
    const next = (parseInt($("poem-seed").value, 10) + 1) % 100;
    $("poem-seed").value = next;
    $("poem-seed-out").textContent = next;
    openPoemReview();
  });

  $("poem-publish").addEventListener("click", () => {
    if (state.lastPoemName) openPublishModal(state.lastPoemName, $("poem-caption").value);
  });
  $("poem-publish-yt").addEventListener("click", () => {
    if (state.lastPoemName) openPublishModal(state.lastPoemName, $("poem-caption").value, "youtube");
  });
  $("poem-clear").addEventListener("click", () => resetPoemForm());

  setupCropDragging();
  $("poem-size").addEventListener("change", () => {
    syncCropFrameShape();
    renderPoemPreview();
  });

  const prefs = loadPoemPrefs();
  // Your own photo is both the fast path and the usual case, so it leads.
  setPoemMode(prefs.mode || "upload");
  setPoemDelivery(prefs.delivery || "recitation");
  if (prefs.provider === "elevenlabs") setPoemProvider("elevenlabs");
  setPoemNarrate(prefs.narrate === true);
  renderPoemPreview();
}

function renderPoemMusic(assets) {
  const browser = $("poem-music-browser");
  const selected = browser.dataset.selected || "";
  browser.innerHTML = "";

  const entries = [{ path: "", label: "No music" }].concat(
    assets.map((f) => ({ path: `assets/${f}`, label: titleCase(f.replace(/\.[^.]+$/, "")) }))
  );
  entries.forEach(({ path, label }) => {
    const item = document.createElement("div");
    item.className = path === selected ? "music-item selected" : "music-item";

    const play = document.createElement("button");
    play.type = "button";
    play.className = "music-play";
    play.dataset.path = path;
    play.disabled = !path;
    play.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMusicPlayback(path);
    });

    const name = document.createElement("span");
    name.className = "music-name";
    name.textContent = label;

    item.appendChild(play);
    item.appendChild(name);
    if (path === selected) {
      const check = document.createElement("span");
      check.className = "music-check";
      check.innerHTML = icon("check", 15);
      item.appendChild(check);
    }
    item.addEventListener("click", () => {
      browser.dataset.selected = path;
      renderPoemMusic(assets);
      savePoemPrefs();
      renderPoemPreview();
    });
    browser.appendChild(item);
  });
  syncMusicIcons();
}

async function openPoemReview() {
  const lines = poemLines();

  // The server owns the real rules, so ask it rather than duplicating them here.
  try {
    const res = await fetch("/api/poem/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gatherPoemOptions()),
    });
    const check = await res.json();
    state.poemUndrawable = check.undrawable || [];
  } catch {
    state.poemUndrawable = [];
  }

  const warnings = poemWarnings(lines);
  const blocking = warnings.some(([kind]) => kind === "danger");

  $("poem-review-warnings").innerHTML = warnings
    .map(([kind, text]) => `<div class="notice ${kind}">${icon(kind === "info" ? "info" : "triangle-alert", 15)}<span>${escapeHtml(text)}</span></div>`)
    .join("");

  $("poem-review-lines").innerHTML = lines.length
    ? lines.map((l) => `<div class="poem-line" dir="auto">${escapeHtml(l)}</div>`).join("")
    : `<span class="poem-preview-empty">Nothing to draw yet</span>`;

  const opts = gatherPoemOptions();
  const usingOwnImage = state.poemMode === "upload";
  const rows = [
    ["Language", opts.language],
    ["Background", usingOwnImage ? state.poemBackground?.name || "Your photo" : "Generated by FLUX"],
    ["Shape", $("poem-size").options[$("poem-size").selectedIndex].textContent],
    ["Music", opts.music_file ? `${titleCase(opts.music_file.split("/").pop().replace(/\.[^.]+$/, ""))} at ${Math.round(opts.music_volume * 100)}%` : "None"],
    ["Handle", opts.handle || "None"],
    ["Length", `${Math.round(poemDuration(lines))}s`],
  ];
  $("poem-review-rows").innerHTML = rows
    .map(([k, v]) => `<div class="review-row"><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`)
    .join("");

  if (usingOwnImage) {
    $("poem-review-estimate").innerHTML =
      `${icon("zap", 15)}<span>Your own photo, so there is no image to draw. About 20 seconds.</span>`;
  } else {
    const [w, h] = opts.size.split("x").map(Number);
    const minutes = Math.max(1, Math.round((60 + 100 * ((w * h) / (1920 * 1080)) + 20) / 60));
    $("poem-review-estimate").innerHTML =
      `${icon("clock", 15)}<span>One image to draw, so roughly ${minutes}–${minutes * 2} minutes. Switch to your own photo to skip the wait.</span>`;
  }

  $("poem-review-start").disabled = blocking;
  $("poem-review-overlay").classList.remove("hidden");
  $("poem-review-modal").classList.remove("hidden");
  refreshIcons();
}

function closePoemReview() {
  $("poem-review-overlay").classList.add("hidden");
  $("poem-review-modal").classList.add("hidden");
}

function setPoemBusy(busy) {
  $("poem-generate-btn").disabled = busy;
  $("poem-redraw").disabled = busy;
  $("poem-generate-btn").innerHTML = busy
    ? `${icon("loader-circle", 14)} Building…`
    : `${icon("wand-sparkles", 14)} Make reel`;
  refreshIcons();
}

async function startPoem() {
  closePoemReview();
  setPoemBusy(true);

  $("poem-result-card").hidden = true;
  $("poem-progress-card").hidden = false;
  $("poem-error").hidden = true;
  $("poem-progress-fill").style.width = "5%";
  $("poem-progress-fill").classList.remove("failed");
  $("poem-progress-label").textContent = "Starting…";
  $("poem-progress-card").scrollIntoView({ behavior: "smooth", block: "nearest" });

  let payload;
  try {
    const res = await fetch("/api/poem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gatherPoemOptions()),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }
    payload = await res.json();
  } catch (err) {
    failPoem(err.message);
    return;
  }

  const percents = { planning: 15, image: 55, typography: 75, video: 90, done: 100 };
  const source = new EventSource(`/api/generate/${payload.job_id}/stream`);
  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    if (event.type === "progress") {
      $("poem-progress-label").textContent = event.message;
      const pct = percents[event.stage];
      if (pct) $("poem-progress-fill").style.width = `${pct}%`;
    } else if (event.type === "complete") {
      source.close();
      finishPoem(payload.name);
    } else if (event.type === "error") {
      source.close();
      failPoem(event.message);
    }
  };
  source.onerror = () => {
    source.close();
    failPoem("Lost contact with the server.");
  };
}

async function finishPoem(name) {
  state.lastPoemName = name;
  $("poem-progress-fill").style.width = "100%";
  $("poem-progress-label").textContent = "Finished";
  $("poem-progress-card").hidden = true;
  setPoemBusy(false);

  const res = await fetch("/api/outputs");
  const { outputs } = await res.json();
  const made = outputs.find((o) => o.name === name);

  $("poem-result-card").hidden = false;
  $("poem-result-video").src = `${made?.video_url || `/output/${name}/reel.mp4`}?t=${Date.now()}`;
  const facts = [
    made?.duration_seconds ? `${Math.round(made.duration_seconds)}s` : null,
    made?.description || null,
    made?.voice || null,
  ].filter(Boolean);
  $("poem-result-mood").textContent = facts.length ? facts.join(" \u00b7 ") : "Your reel is ready to post";
  $("poem-result-shape").textContent = (made?.size || "1080x1920").replace("x", " \u00d7 ");
  $("poem-caption").value = made?.caption || "";
  $("poem-download").href = `/api/outputs/${encodeURIComponent(name)}/download`;
  $("poem-download").download = `${name}.mp4`;
  $("poem-result-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
  toast("Reel ready");
  loadOutputCount();
  refreshIcons();
}

function failPoem(message) {
  $("poem-progress-fill").style.width = "100%";
  $("poem-progress-fill").classList.add("failed");
  $("poem-progress-label").textContent = "Failed";
  showErrorBanner("poem-error", message);
  setPoemBusy(false);
  refreshIcons();
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

/* ---------------- Generate ---------------- */

function gatherGenerateOptions() {
  return {
    story_name: $("story-name").value.trim(),
    story_text: $("story-text").value,
    style: $("opt-style").value,
    language: $("opt-language").value,
    category: $("opt-category").value,
    tts_provider: $("opt-tts-provider").value,
    voice: $("opt-voice").value,
    voice_rate: $("opt-voice-rate").value,
    voice_pitch: $("opt-voice-pitch").value,
    sarvam_speaker: $("opt-sarvam-speaker").value,
    indicf5_voice: $("opt-indicf5-voice").value,
    sarvam_pace: parseFloat($("opt-sarvam-pace").value),
    sarvam_temperature: parseFloat($("opt-sarvam-temperature").value),
    size: $("opt-size").value,
    transition: parseFloat($("opt-transition").value),
    scene_pause: parseFloat($("opt-scene-pause").value),
    ambience_volume: parseFloat($("opt-ambience-volume").value),
    music_volume: parseFloat($("opt-music-volume").value),
    music_style: "arabic",
    music_file: $("opt-music-preset").value || null,
    force_replan: $("opt-force-replan").checked,
    force_images: $("opt-force-images").checked,
  };
}

function stagePercent(event) {
  const fixed = {
    plan: 4,
    plan_done: 10,
    captions: 82,
    crossfade_video: 86,
    crossfade_audio: 89,
    mixing: 92,
    muxing: 95,
    burning: 98,
    done: 100,
  };
  if (event.stage in fixed) return fixed[event.stage];
  if (event.total && event.scene) {
    const perScene = 70 / event.total;
    const offsets = { image: 0.35, voice: 0.7, video_clip: 1 };
    const within = offsets[event.stage] ?? 1;
    return Math.min(80, Math.round(10 + (event.scene - 1 + within) * perScene));
  }
  return null;
}

const STAGE_TO_STEP = {
  plan: "plan",
  plan_done: "plan",
  image: "scene",
  voice: "scene",
  video_clip: "scene",
  captions: "stitch",
  crossfade_video: "stitch",
  crossfade_audio: "stitch",
  mixing: "stitch",
  muxing: "stitch",
  burning: "captions",
  done: "captions",
};

function setStep(stage) {
  const order = ["plan", "scene", "stitch", "captions"];
  const current = STAGE_TO_STEP[stage];
  if (!current) return;
  const currentIndex = order.indexOf(current);
  order.forEach((step, i) => {
    const li = document.querySelector(`#step-list li[data-step="${step}"]`);
    li.classList.toggle("active", i === currentIndex);
    li.classList.toggle("done", i < currentIndex);
  });
}

function setupGenerate() {
  $("result-goto-outputs").addEventListener("click", () => switchTab("outputs"));
  $("result-publish").addEventListener("click", () => {
    if (state.lastStoryName) openPublishModal(state.lastStoryName, "");
  });
  $("result-publish-yt").addEventListener("click", () => {
    if (state.lastStoryName) openPublishModal(state.lastStoryName, "", "youtube");
  });

  $("generate-btn").addEventListener("click", () => {
    if (!validateStoryForm()) return;
    openReviewModal();
  });

  $("review-close").addEventListener("click", closeReviewModal);
  $("review-back").addEventListener("click", closeReviewModal);
  $("review-overlay").addEventListener("click", closeReviewModal);
  $("review-start").addEventListener("click", () => {
    closeReviewModal();
    startGeneration();
  });
}

function validateStoryForm() {
  const name = $("story-name").value.trim();
  const text = $("story-text").value.trim();
  let valid = true;

  setFieldError("story-name", !name ? "Give this story a name so its output folder can be found later." : "");
  setFieldError("story-text", !text ? "Write or load a story before generating." : "");
  if (!name || !text) valid = false;

  if (valid && text.split(/\s+/).length < 15) {
    setFieldError("story-text", "This is very short. Scene planning works best with at least a short paragraph.");
  }
  if (!valid) {
    switchTab("story");
    (!name ? $("story-name") : $("story-text")).focus();
  }
  return valid;
}

function setFieldError(fieldId, message) {
  const field = $(fieldId);
  const holder = $(`${fieldId}-error`);
  if (!holder) return;
  holder.hidden = !message;
  holder.innerHTML = message ? `${icon("circle-alert", 13)} ${message}` : "";
  field.classList.toggle("invalid", Boolean(message));
  refreshIcons();
}

function reviewWarnings(opts) {
  const warnings = [];
  const configFor = (key) => state.config.find((f) => f.key === key);
  const isSet = (key) => Boolean(configFor(key)?.is_set);

  if (opts.tts_provider === "sarvam" && state.config.length && !isSet("SARVAM_API_KEY")) {
    warnings.push(["danger", "Sarvam is selected but no Sarvam API key is saved. Add it in Settings first."]);
  }
  if (opts.tts_provider === "indicf5" && /urdu/i.test(opts.language)) {
    warnings.push(["warn", "IndicF5 does not support Urdu. Use Hindi in Devanagari script, or switch to Sarvam."]);
  }
  if (opts.tts_provider === "edge") {
    const expected = LANGUAGE_VOICE[opts.language];
    if (expected && opts.voice.split("-")[0] !== expected.split("-")[0]) {
      warnings.push(["danger", `Voice "${opts.voice}" cannot speak ${opts.language}. edge-tts will return no audio. Pick a matching voice.`]);
    }
  }
  if (state.stories.includes(opts.story_name)) {
    warnings.push(["warn", `An output named "${opts.story_name}" already exists. Cached scenes and images will be reused unless you enable the re-generate switches.`]);
  }
  if (/cinematic/i.test(opts.style)) {
    warnings.push(["info", "The word \u201Ccinematic\u201D can make the image model add black letterbox bars. Remove it if you see them."]);
  }
  if (opts.music_volume > 0 && !opts.music_file) {
    warnings.push(["warn", "Music volume is above zero but no music track is selected."]);
  }
  if (opts.music_file && opts.music_volume === 0) {
    warnings.push(["warn", "A music track is selected but music volume is zero, so it will be silent."]);
  }
  return warnings;
}

function estimateMinutes(opts) {
  // Gemini decides the real scene count, so this is a range, not a promise.
  const words = opts.story_text.trim().split(/\s+/).filter(Boolean).length;
  const scenes = Math.max(6, Math.min(14, Math.round(words / 18)));

  const [w, h] = (opts.size || "1920x1080").split("x").map(Number);
  const local = state.imageProvider === "local";
  // Measured here: FLUX.1-schnell at 4 steps takes ~100s per 1080p image.
  const perImage = local ? 100 * ((w * h) / (1920 * 1080)) : 10;
  const perVoice = { indicf5: 20, sarvam: 3, edge: 2 }[opts.tts_provider] ?? 3;
  const startup = local ? 60 : 10;
  const seconds = startup + scenes * (perImage + perVoice + 5) + 45;
  const minutes = Math.max(1, Math.round(seconds / 60));
  return {
    scenes,
    low: minutes,
    high: Math.round(minutes * 1.5),
    imageShare: Math.round(((scenes * perImage) / seconds) * 100),
    local,
  };
}

function openReviewModal() {
  const opts = gatherGenerateOptions();
  const provider = opts.tts_provider;
  const voice = { sarvam: opts.sarvam_speaker, indicf5: opts.indicf5_voice }[provider] ?? opts.voice;
  const providerLabel = { edge: "edge-tts (free)", indicf5: "IndicF5 (local)", sarvam: "Sarvam (paid API)" }[provider];

  const groups = [
    ["Story", [
      ["Name", opts.story_name],
      ["Category", titleCase(opts.category)],
      ["Language", opts.language],
    ]],
    ["Look", [
      ["Style", opts.style],
      ["Images", state.imageProvider === "local" ? "FLUX.1-schnell (local)" : state.imageProvider],
      ["Resolution", opts.size],
    ]],
    ["Sound", [
      ["Voice engine", providerLabel],
      ["Voice", voice],
      ["Music", opts.music_file ? `${opts.music_file.split("/").pop()} at ${Math.round(opts.music_volume * 100)}%` : "None"],
      ["Ambience", opts.ambience_volume > 0 ? `${Math.round(opts.ambience_volume * 100)}%` : "Off"],
    ]],
    ["Rendering", [
      ["Crossfade", `${opts.transition}s`],
      ["Pause per scene", `${opts.scene_pause}s`],
      ["Re-plan scenes", opts.force_replan ? "Yes" : "No, reuse cache"],
      ["Re-generate images", opts.force_images ? "Yes" : "No, reuse cache"],
    ]],
  ];

  $("review-groups").innerHTML = groups
    .map(([title, rows]) => `
      <div class="review-group">
        <h3>${title}</h3>
        <div class="review-rows">
          ${rows.map(([k, v]) => `<div class="review-row"><dt>${k}</dt><dd>${v}</dd></div>`).join("")}
        </div>
      </div>`)
    .join("") + `
      <div class="review-group">
        <h3>Story preview</h3>
        <div class="review-story">${opts.story_text.trim().slice(0, 320)}${opts.story_text.length > 320 ? "\u2026" : ""}</div>
      </div>`;

  $("review-warnings").innerHTML = reviewWarnings(opts)
    .map(([kind, text]) => `<div class="notice ${kind}">${icon(kind === "info" ? "info" : "triangle-alert", 15)}<span>${text}</span></div>`)
    .join("");

  const { scenes, low, high, imageShare, local } = estimateMinutes(opts);
  const detail = local
    ? `About ${imageShare}% of that is FLUX drawing images on your Mac, at roughly 1.5–2 minutes each.`
    : "";
  $("review-estimate").innerHTML =
    `${icon("clock", 15)}<span>Around ${scenes} scenes, roughly ${low}–${high} minutes. ${detail} ` +
    `You can keep using the other tabs while it runs.</span>`;

  $("review-overlay").classList.remove("hidden");
  $("review-modal").classList.remove("hidden");
  refreshIcons();
  $("review-start").focus();
}

function closeReviewModal() {
  $("review-overlay").classList.add("hidden");
  $("review-modal").classList.add("hidden");
}

async function startGeneration() {
  const opts = gatherGenerateOptions();
  {
    $("generate-btn").disabled = true;
    $("progress-card").hidden = false;
    $("result-card").hidden = true;
    $("progress-log").textContent = "";
    $("progress-fill").style.width = "0%";
    $("progress-fill").classList.remove("failed");
    $("progress-percent").textContent = "0%";
    $("progress-label").textContent = "Starting...";
    $("progress-error").hidden = true;
    const cardIcon = document.querySelector("#progress-card .card-icon");
    cardIcon.classList.remove("danger");
    cardIcon.classList.add("spinning");
    cardIcon.innerHTML = icon("loader-circle", 17);
    refreshIcons();
    document.querySelectorAll("#step-list li").forEach((li) => li.classList.remove("active", "done"));
    $("progress-card").scrollIntoView({ behavior: "smooth", block: "nearest" });

    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts),
    });
    const { job_id, story_name } = await res.json();
    $("story-name").value = story_name;

    const source = new EventSource(`/api/generate/${job_id}/stream`);
    source.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      if (event.type === "progress") {
        const percent = stagePercent(event);
        $("progress-log").textContent += event.message + "\n";
        $("progress-log").scrollTop = $("progress-log").scrollHeight;
        $("progress-label").textContent = event.message;
        if (percent !== null) {
          $("progress-fill").style.width = percent + "%";
          $("progress-percent").textContent = percent + "%";
        }
        setStep(event.stage);
      } else if (event.type === "complete") {
        $("progress-fill").style.width = "100%";
        $("progress-percent").textContent = "100%";
        $("progress-label").textContent = "Finished";
        document.querySelectorAll("#step-list li").forEach((li) => {
          li.classList.remove("active");
          li.classList.add("done");
        });
        const url = `/output/${story_name}/final_video.mp4?t=${Date.now()}`;
        $("result-card").hidden = false;
        $("result-video").src = url;
        $("result-download").href = `/api/outputs/${encodeURIComponent(story_name)}/download`;
        $("result-download").download = `${story_name}.mp4`;
        state.lastStoryName = story_name;
        // Instagram reels and YouTube Shorts are both vertical, so only offer them when the render is not landscape.
        const [rw, rh] = (opts.size || "1920x1080").split("x").map(Number);
        $("result-publish").hidden = rw >= rh;
        $("result-publish-yt").hidden = rw >= rh;
        toast("Video ready");
      } else if (event.type === "error") {
        const cardIcon = document.querySelector("#progress-card .card-icon");
        cardIcon.classList.remove("spinning");
        cardIcon.classList.add("danger");
        cardIcon.innerHTML = icon("circle-alert", 17);
        $("progress-fill").classList.add("failed");
        $("progress-label").textContent = "Generation failed";
        showErrorBanner("progress-error", event.message);
        $("progress-log").textContent += "\nERROR: " + event.message + "\n";
        document.querySelector("#progress-card .log-details").open = true;
        refreshIcons();
        toast("Generation failed", "error");
      } else if (event.type === "end") {
        source.close();
        $("generate-btn").disabled = false;
        loadStoriesList();
        loadOutputCount();
      }
    };
    source.onerror = () => {
      source.close();
      $("generate-btn").disabled = false;
      if ($("progress-percent").textContent !== "100%") {
        $("progress-label").textContent = "Lost connection to the server";
        showErrorBanner(
          "progress-error",
          "The progress stream disconnected. The job may still be running \u2014 check the Outputs tab in a few minutes."
        );
        toast("Lost connection to the server", "error");
      }
    };
  }
}


async function loadPromptCategories() {
  $("prompts-skeleton").classList.remove("hidden");
  $("prompts-layout").classList.add("hidden");
  await loadCategoriesIntoSelect($("prompt-category"));
  if (state.categories.length) {
    await loadPrompt($("prompt-category").value);
  }
  $("prompts-skeleton").classList.add("hidden");
  $("prompts-layout").classList.remove("hidden");
}

async function loadPrompt(category) {
  if (!category) return;
  state.promptCategory = category;
  const res = await fetch(`/api/prompts/${category}`);
  const data = await res.json();
  $("prompt-text").value = data.text;
  state.promptBaseline = data.text;
  setDirty(false);
  updatePromptCounter();

  const list = $("prompt-versions");
  list.innerHTML = "";
  if (!data.versions.length) {
    list.innerHTML = `<div class="empty-state">
      <span class="empty-icon">${icon("history", 24)}</span>
      <strong>No versions yet</strong>
      <p>Edit the template and save — every save is archived here so you can roll back.</p>
    </div>`;
    refreshIcons();
    return;
  }
  data.versions.forEach((v) => {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.className = "preview";
    span.innerHTML = `<strong>${v.id}</strong><span>${v.preview}</span>`;
    const btn = document.createElement("button");
    btn.className = "btn-secondary";
    btn.innerHTML = `${icon("rotate-ccw", 13)} Restore`;
    btn.addEventListener("click", async () => {
      await fetch(`/api/prompts/${category}/restore/${v.id}`, { method: "POST" });
      await loadPrompt(category);
      toast("Version restored");
    });
    li.appendChild(span);
    li.appendChild(btn);
    list.appendChild(li);
  });
  refreshIcons();
}

function updatePromptCounter() {
  $("prompt-counter").textContent = `${$("prompt-text").value.length} characters`;
}

async function savePromptVersion() {
  const category = state.promptCategory;
  if (!category) return;
  await fetch(`/api/prompts/${category}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: $("prompt-text").value }),
  });
  await loadPrompt(category);
  toast("Prompt template saved");
}

function setupPrompts() {
  $("prompt-category").addEventListener("change", (e) => loadPrompt(e.target.value));

  $("prompt-text").addEventListener("input", () => {
    updatePromptCounter();
    setDirty($("prompt-text").value !== state.promptBaseline);
  });

  document.querySelectorAll("#placeholder-chips .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const area = $("prompt-text");
      const start = area.selectionStart;
      const text = chip.dataset.insert;
      area.value = area.value.slice(0, start) + text + area.value.slice(area.selectionEnd);
      area.focus();
      area.selectionStart = area.selectionEnd = start + text.length;
      updatePromptCounter();
      setDirty(true);
    });
  });

  $("prompt-new-category-btn").addEventListener("click", async () => {
    const name = prompt("New category name (letters, numbers, dashes/underscores):");
    if (!name) return;
    const safe = name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/^_|_$/g, "");
    if (!safe) return;
    await fetch(`/api/prompts/${safe}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("prompt-text").value || "" }),
    });
    await loadPromptCategories();
    $("prompt-category").value = safe;
    renderSelect($("prompt-category"));
    await loadPrompt(safe);
    await loadCategoriesIntoSelect($("opt-category"));
    toast(`Category "${safe}" created`);
  });
}

/* ---------------- Settings ---------------- */

async function loadSettings() {
  $("settings-skeleton").classList.remove("hidden");
  $("settings-groups").classList.add("hidden");

  const res = await fetch("/api/config");
  const fields = await res.json();
  state.config = fields;
  state.imageProvider = fields.find((f) => f.key === "IMAGE_PROVIDER")?.value || "local";
  state.settingsBaseline = {};

  const shell = $("settings-groups");
  shell.innerHTML = `<nav class="settings-nav" id="settings-nav"></nav><div class="settings-panels" id="settings-panels"></div>`;
  const navEl = $("settings-nav");
  const panelsEl = $("settings-panels");

  const groups = {};
  fields.forEach((f) => {
    groups[f.group] = groups[f.group] || [];
    groups[f.group].push(f);
  });

  const names = Object.keys(groups);
  if (!names.includes(state.settingsSection)) state.settingsSection = names[0];

  names.forEach((groupName) => {
    const groupFields = groups[groupName].filter((f) => !f.hidden);
    const meta = SETTINGS_GROUP_META[groupName] || { icon: "circle", description: "" };

    const missing = groupFields.filter((f) => f.secret && !f.is_set).length;
    const navItem = document.createElement("button");
    navItem.type = "button";
    navItem.className = "settings-nav-item";
    navItem.dataset.section = groupName;
    navItem.innerHTML =
      `<span class="settings-nav-icon">${icon(meta.icon, 15)}</span>` +
      `<span class="settings-nav-text"><span class="settings-nav-title">${groupName}</span>` +
      `<span class="settings-nav-sub">${groupFields.length} setting${groupFields.length === 1 ? "" : "s"}</span></span>` +
      (missing ? `<span class="settings-nav-dot" title="${missing} key not set"></span>` : "");
    navItem.addEventListener("click", () => showSettingsSection(groupName));
    navEl.appendChild(navItem);

    const panel = document.createElement("section");
    panel.className = "settings-panel";
    panel.dataset.section = groupName;
    panel.innerHTML = `<header class="settings-panel-head">
        <h2>${groupName}</h2>
        <p>${meta.description}</p>
      </header>`;

    groupFields.forEach((f) => {
      const wrap = document.createElement("div");
      wrap.className = "settings-field";
      wrap.dataset.key = f.key;
      if (f.applies_when) wrap.dataset.appliesWhen = JSON.stringify(f.applies_when);

      const labelRow = document.createElement("div");
      labelRow.className = "settings-field-label-row";
      labelRow.innerHTML =
        `<label>${f.label}</label>` +
        `<span class="field-flags">` +
        `<span class="badge inactive inactive-badge" hidden>inactive</span>` +
        `<span class="badge ${f.is_set ? "" : "unset"}">${f.is_set ? "saved" : "not set"}</span>` +
        `</span>`;
      wrap.appendChild(labelRow);

      const control = buildSettingsInput(f);
      control.classList.add("settings-field-control");
      wrap.appendChild(control);

      const help = document.createElement("div");
      help.className = "help-text";
      help.textContent = f.help;
      if (f.guidance) {
        const line = document.createElement("div");
        line.className = "help-text guidance";
        line.innerHTML = f.guidance_url
          ? `<a href="${f.guidance_url}" target="_blank" rel="noopener">${icon("external-link", 11)} ${f.guidance}</a>`
          : f.guidance;
        wrap.appendChild(help);
        wrap.appendChild(line);
      } else {
        wrap.appendChild(help);
      }

      panel.appendChild(wrap);
      state.settingsBaseline[f.key] = f.secret ? "" : (f.value || "");
    });

    if (groupName === "Instagram") appendInstagramHelp(panel);
    if (groupName === "YouTube") appendYoutubeHelp(panel);
    panelsEl.appendChild(panel);
  });

  enhanceAllSelects(shell);
  refreshIcons();
  setDirty(false);
  applySettingsRelevance();
  showSettingsSection(state.settingsSection);

  shell.addEventListener("input", checkSettingsDirty);
  shell.addEventListener("change", () => {
    checkSettingsDirty();
    applySettingsRelevance();
  });

  $("settings-skeleton").classList.add("hidden");
  shell.classList.remove("hidden");
}

function showSettingsSection(name) {
  state.settingsSection = name;
  document.querySelectorAll(".settings-nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.section === name)
  );
  document.querySelectorAll(".settings-panel").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.section !== name)
  );
}

function appendInstagramHelp(panel) {
  const steps = document.createElement("div");
  steps.className = "setup-steps";
  steps.innerHTML =
    `<strong>${icon("list-ordered", 13)} Where to get these two values</strong>` +
    `<ol>
       <li>In the Instagram app, switch your account to <b>Professional</b> (Business or Creator). A personal account cannot post through the API.</li>
       <li>Link it to a Facebook Page. Instagram &rarr; Settings &rarr; Sharing to other apps.</li>
       <li>At <a href="https://developers.facebook.com/apps" target="_blank" rel="noopener">developers.facebook.com/apps</a> create an app, type <b>Business</b>.</li>
       <li>Open <a href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noopener">Graph API Explorer</a>, pick your app, and add these permissions:
         <code>instagram_basic</code>, <code>instagram_content_publish</code>, <code>pages_show_list</code>, <code>pages_read_engagement</code>.</li>
       <li>Press <b>Generate Access Token</b> and paste it into the token box above.</li>
       <li>Run <code>me/accounts?fields=instagram_business_account</code> and copy the <code>id</code> into Account ID.</li>
     </ol>`;
  panel.appendChild(steps);

  const tester = document.createElement("div");
  tester.className = "connection-test";
  tester.innerHTML =
    `<button class="btn-secondary" id="ig-test-btn">${icon("plug-zap", 14)} Test connection</button>` +
    `<span class="connection-status" id="ig-test-status">Save your details first, then test.</span>`;
  panel.appendChild(tester);
  tester.querySelector("#ig-test-btn").addEventListener("click", testInstagram);
}

function appendYoutubeHelp(panel) {
  const steps = document.createElement("div");
  steps.className = "setup-steps";
  steps.innerHTML =
    `<strong>${icon("list-ordered", 13)} Where to get these two values</strong>` +
    `<ol>
       <li>In <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">Google Cloud Console \u2192 Credentials</a>, enable <b>YouTube Data API v3</b> and <b>YouTube Analytics API</b> for your project.</li>
       <li>Create Credentials \u2192 OAuth client ID \u2192 type <b>Desktop app</b>.</li>
       <li>Copy the Client ID and Client Secret it shows into the two fields above and save.</li>
       <li>Click <b>Connect YouTube</b> below, sign in with the Google account that owns your channel, and approve.</li>
       <li>Custom thumbnails (recommended, so the caption card is what shows up rather than a random frame) need your channel to be <a href="https://www.youtube.com/verify" target="_blank" rel="noopener">phone-verified</a>. Without that, posting still works, YouTube just picks its own thumbnail.</li>
     </ol>`;
  panel.appendChild(steps);

  const status = document.createElement("div");
  status.className = "connection-test";
  status.innerHTML =
    `<button class="btn-secondary" id="yt-connect-btn">${icon("plug-zap", 14)} Connect YouTube</button>` +
    `<span class="connection-status" id="yt-connect-status">Not connected yet.</span>`;
  panel.appendChild(status);
  status.querySelector("#yt-connect-btn").addEventListener("click", connectYoutube);

  refreshYoutubeStatus();
}

async function refreshYoutubeStatus() {
  const status = $("yt-connect-status");
  if (!status) return;
  try {
    const res = await fetch("/api/youtube/test");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Not connected.");
    status.className = "connection-status ok";
    status.textContent = `Connected to ${data.title}${data.subscriber_count ? ` \u00b7 ${data.subscriber_count} subscribers` : ""}`;
  } catch (err) {
    status.className = "connection-status";
    status.textContent = err.message.includes("not set") || err.message.includes("not connected")
      ? "Not connected yet."
      : err.message;
  }
}

async function connectYoutube() {
  const btn = $("yt-connect-btn");
  const status = $("yt-connect-status");
  btn.disabled = true;
  btn.innerHTML = `${icon("loader-circle", 14)} Starting\u2026`;
  status.className = "connection-status";
  status.textContent = "Opening Google sign-in in a new tab\u2026";
  refreshIcons();
  try {
    const res = await fetch("/api/youtube/connect", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not start the connection.");
    window.open(data.auth_url, "_blank", "noopener");

    status.textContent = "Waiting for you to approve access in the browser tab\u2026";
    for (let i = 0; i < 150; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const poll = await fetch(`/api/youtube/connect/status?session_id=${data.session_id}`);
      const state = await poll.json();
      if (state.status === "connected") {
        status.className = "connection-status ok";
        status.textContent = `Connected to ${state.channel.title}`;
        toast("YouTube connected");
        return;
      }
      if (state.status === "error") throw new Error(state.error || "Connection failed.");
    }
    throw new Error("Timed out waiting for approval. Try again.");
  } catch (err) {
    status.className = "connection-status error";
    status.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${icon("plug-zap", 14)} Connect YouTube`;
    refreshIcons();
  }
}

function buildSettingsInput(field) {
  if (field.type === "select") {
    const select = document.createElement("select");
    (field.options || []).forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt;
      o.textContent = opt;
      if (opt === field.value) o.selected = true;
      select.appendChild(o);
    });
    select.dataset.key = field.key;
    return select;
  }

  if (field.type === "combo") {
    const container = document.createElement("div");
    const select = document.createElement("select");
    const known = field.options || [];
    known.forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      select.appendChild(o);
    });
    const customOption = document.createElement("option");
    customOption.value = "__custom__";
    customOption.textContent = "Custom value...";
    select.appendChild(customOption);

    const input = document.createElement("input");
    input.type = "text";
    input.className = "combo-custom";
    input.dataset.key = field.key;
    input.value = field.value || "";

    const matches = known.some((o) => o.value === field.value);
    select.value = matches ? field.value : "__custom__";
    input.hidden = matches;

    select.addEventListener("change", () => {
      if (select.value === "__custom__") {
        input.hidden = false;
        input.focus();
      } else {
        input.hidden = true;
        input.value = select.value;
      }
    });

    container.appendChild(select);
    container.appendChild(input);
    return container;
  }

  if (field.type === "password") {
    const container = document.createElement("div");

    const input = document.createElement("input");
    input.type = "password";
    input.dataset.key = field.key;
    input.placeholder = "Paste the new key here";

    if (field.is_set) {
      // Show that a key exists rather than an empty box, and only reveal the input on request.
      const saved = document.createElement("div");
      saved.className = "saved-value";
      saved.innerHTML =
        `<span class="saved-mask">${icon("key-round", 14)} ${field.value || "••••••••"}</span>` +
        `<button type="button" class="btn-ghost replace-btn">Replace</button>`;
      container.appendChild(saved);

      input.hidden = true;
      saved.querySelector(".replace-btn").addEventListener("click", () => {
        saved.hidden = true;
        input.hidden = false;
        input.focus();
      });
    }

    const wrap = document.createElement("div");
    wrap.className = "password-wrap";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "password-toggle";
    toggle.innerHTML = icon("eye", 15);
    toggle.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      toggle.innerHTML = icon(showing ? "eye" : "eye-off", 15);
      refreshIcons();
    });
    wrap.appendChild(input);
    wrap.appendChild(toggle);
    if (field.is_set) wrap.hidden = true;

    if (field.is_set) {
      container.querySelector(".replace-btn").addEventListener("click", () => {
        wrap.hidden = false;
      });
    }

    container.appendChild(wrap);
    return container;
  }

  const input = document.createElement("input");
  input.type = "text";
  input.dataset.key = field.key;
  input.value = field.value || "";
  return input;
}

function applySettingsRelevance() {
  const current = collectSettingsValues();
  document.querySelectorAll("#settings-groups .settings-field[data-applies-when]").forEach((field) => {
    const rules = JSON.parse(field.dataset.appliesWhen);
    const relevant = Object.entries(rules).every(([key, allowed]) => allowed.includes(current[key]));
    field.classList.toggle("not-applicable", !relevant);
    const badge = field.querySelector(".inactive-badge");
    if (badge) badge.hidden = relevant;
  });
}

function collectSettingsValues() {
  const values = {};
  document.querySelectorAll("#settings-groups [data-key]").forEach((input) => {
    values[input.dataset.key] = input.value;
  });
  return values;
}

function checkSettingsDirty() {
  const values = collectSettingsValues();
  const changed = Object.entries(values).some(([key, value]) => {
    const field = state.config.find((f) => f.key === key);
    if (field && field.secret) return value !== "";
    return value !== (state.settingsBaseline[key] || "");
  });
  setDirty(changed);
}

async function saveSettings() {
  const values = {};
  Object.entries(collectSettingsValues()).forEach(([key, value]) => {
    const field = state.config.find((f) => f.key === key);
    if (field && field.secret && value === "") return;
    values[key] = value;
  });
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  await loadSettings();
  toast("Settings saved and applied");
}


async function loadOutputs() {
  $("outputs-skeleton").classList.remove("hidden");
  $("outputs-list").classList.add("hidden");

  const res = await fetch("/api/outputs");
  const data = await res.json();
  state.outputs = data.outputs;
  $("nav-outputs-count").textContent = data.outputs.length || "";

  $("outputs-skeleton").classList.add("hidden");
  $("outputs-list").classList.remove("hidden");
  renderOutputStats();
  renderOutputs();
}

function renderOutputStats() {
  const total = state.outputs.length;
  const seconds = state.outputs.reduce((sum, o) => sum + (o.duration_seconds || 0), 0);
  const scenes = state.outputs.reduce((sum, o) => sum + (o.scene_count || 0), 0);
  const stats = [
    { icon: "film", value: total, label: total === 1 ? "video" : "videos" },
    { icon: "clock", value: formatDuration(seconds), label: "total runtime" },
    { icon: "images", value: scenes || "—", label: "scenes rendered" },
  ];
  $("outputs-stats").innerHTML = stats
    .map((s) => `<div class="stat-card">
        <span class="stat-icon">${icon(s.icon, 18)}</span>
        <div><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>
      </div>`)
    .join("");
  refreshIcons();
}

function renderOutputs() {
  const query = $("outputs-search").value.trim().toLowerCase();
  const sort = $("outputs-sort").value;
  const grid = $("outputs-list");

  let items = state.outputs.filter((o) =>
    (state.outputFilter === "all" || o.orientation === state.outputFilter) &&
    (!query ||
      o.name.toLowerCase().includes(query) ||
      (o.description || "").toLowerCase().includes(query))
  );

  items = [...items].sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name);
    if (sort === "longest") return (b.duration_seconds || 0) - (a.duration_seconds || 0);
    // created_at is ISO, modified_at is unix seconds; put both on the same scale.
    const at = Date.parse(a.created_at) || (a.modified_at || 0) * 1000;
    const bt = Date.parse(b.created_at) || (b.modified_at || 0) * 1000;
    return sort === "oldest" ? at - bt : bt - at;
  });

  grid.innerHTML = "";

  if (!items.length) {
    const filterLabel = { portrait: "Reels & Shorts", landscape: "Landscape", square: "Square" }[state.outputFilter];
    let reason = "Nothing here matches your search yet.";
    if (query && filterLabel) reason = `No ${filterLabel} videos match "${escapeHtml(query)}".`;
    else if (query) reason = `Nothing here matches "${escapeHtml(query)}". Try a different search term.`;
    else if (filterLabel) reason = `No ${filterLabel} videos yet. Poetry reels are portrait, story videos are landscape.`;

    grid.innerHTML = state.outputs.length
      ? `<div class="empty-state">
          <span class="empty-icon">${icon("search-x", 24)}</span>
          <strong>No matches</strong>
          <p>${reason}</p>
        </div>`
      : `<div class="empty-state">
          <span class="empty-icon">${icon("clapperboard", 24)}</span>
          <strong>No videos yet</strong>
          <p>Generated videos show up here with their description, runtime and scene count.</p>
          <button class="btn-primary" id="empty-create-btn">${icon("wand-sparkles", 14)} Create your first video</button>
        </div>`;
    refreshIcons();
    const btn = $("empty-create-btn");
    if (btn) btn.addEventListener("click", () => switchTab("story"));
    return;
  }

  items.forEach((o) => {
    const card = document.createElement("div");
    card.className = "output-card";

    // Remixing rewrites the file at the same path, so key the URL on its mtime.
    const bust = Math.round(o.modified_at || 0);
    const thumb = o.video_url
      ? `<video controls preload="metadata" src="${o.video_url}?v=${bust}"${o.images?.[0] ? ` poster="${o.images[0]}?v=${bust}"` : ""}></video>`
      : `<div class="output-thumb-empty">${icon("video-off", 22)}<span>No final video</span></div>`;

    const shapeLabel = { portrait: "Short", landscape: "Landscape", square: "Square" }[o.orientation] || "";
    const posted = o.instagram && o.instagram.media_id;
    const postedYoutube = o.youtube && o.youtube.video_id;
    const badges =
      (posted ? `<span class="badge posted">${icon("check", 12)} IG posted</span>` : "") +
      (postedYoutube ? `<span class="badge posted">${icon("check", 12)} YT posted</span>` : "") +
      [shapeLabel, o.language].filter(Boolean)
        .map((v) => `<span class="badge outline">${v}</span>`).join("");

    const shown = (o.images || []).slice(0, 4);
    const extra = (o.images || []).length - shown.length;
    const gallery = shown.length
      ? `<div class="scene-strip">${shown
          .map((src, i) => `<img src="${src}" alt="Scene ${i + 1}" loading="lazy" data-full="${src}" />`)
          .join("")}${extra > 0 ? `<span class="scene-more">+${extra}</span>` : ""}</div>`
      : "";

    card.innerHTML = `
      ${thumb}
      <div class="output-body">
        <div class="name">${titleCase(o.name)}</div>
        ${o.description ? `<div class="description">${o.description}</div>` : ""}
        ${badges ? `<div class="output-badges">${badges}</div>` : ""}
        ${gallery}
        <div class="output-meta-row">
          <span>${icon("clock", 12)} ${formatDuration(o.duration_seconds)}</span>
          <span>${icon("calendar", 12)} ${formatDate(o.created_at || o.modified_at)}</span>
        </div>
      </div>
      <div class="output-actions"></div>`;

    card.querySelectorAll(".scene-strip img").forEach((img, i) => {
      img.addEventListener("click", () => openLightbox(o.images, i));
    });

    const actions = card.querySelector(".output-actions");
    const menu = [];

    // Posting is the point of a reel, so it leads. Landscape cannot be a Short or a Reel.
    const canPost = o.video_url && o.orientation !== "landscape";
    const shortDuration = o.duration_seconds || 0;
    const eligibleForYoutube = canPost && (!shortDuration || shortDuration <= 180);
    if (canPost) {
      const ig = document.createElement("button");
      ig.className = "btn-primary primary-action";
      if (posted) {
        ig.innerHTML = `${icon("chart-no-axes-column", 14)} Insights`;
        ig.addEventListener("click", () => openInsights(o.name));
      } else {
        ig.innerHTML = `${icon("camera", 14)} Post`;
        ig.addEventListener("click", () => openPublishModal(o.name, o.caption));
      }
      actions.appendChild(ig);
    }
    if (eligibleForYoutube) {
      const yt = document.createElement("button");
      yt.className = "btn-secondary primary-action";
      yt.title = "YouTube Shorts";
      if (postedYoutube) {
        yt.innerHTML = `${icon("chart-no-axes-column", 14)} Shorts`;
        yt.addEventListener("click", () => openInsights(o.name, "youtube"));
      } else {
        yt.innerHTML = `${icon("monitor-play", 14)} Shorts`;
        yt.addEventListener("click", () => openPublishModal(o.name, o.caption, "youtube"));
      }
      actions.appendChild(yt);
    }

    if (o.video_url) {
      const download = { icon: "download", label: "Download video", onClick: () => {
        const a = document.createElement("a");
        a.href = `/api/outputs/${encodeURIComponent(o.name)}/download`;
        a.download = `${o.name}.mp4`;
        a.click();
      } };
      if (canPost) {
        menu.push(download);
      } else {
        const dl = document.createElement("a");
        dl.className = "btn-secondary primary-action";
        dl.href = `/api/outputs/${encodeURIComponent(o.name)}/download`;
        dl.download = `${o.name}.mp4`;
        dl.innerHTML = `${icon("download", 14)} Download`;
        actions.appendChild(dl);
      }
    }

    // Remix rebuilds from a scene plan, which poem reels do not have.
    if (o.kind !== "poem") {
      menu.push({ icon: "music", label: "Change music", onClick: () => openRemixModal(o) });
    }
    if (canPost && !eligibleForYoutube) {
      menu.push({ icon: "monitor-play", label: "Too long for a Short (>3 min)", onClick: () => toast("YouTube Shorts must be 3 minutes or under.", "error") });
    }
    if (o.images?.length) {
      menu.push({ icon: "images", label: "View images", onClick: () => openLightbox(o.images, 0) });
    }
    menu.push({ icon: "trash-2", label: "Delete", danger: true, onClick: () => deleteOutput(o) });

    actions.appendChild(buildCardMenu(menu));
    grid.appendChild(card);
  });

  refreshIcons();
}

function buildCardMenu(items) {
  const wrap = document.createElement("div");
  wrap.className = "card-menu";

  const trigger = document.createElement("button");
  trigger.className = "icon-btn menu-trigger";
  trigger.title = "More actions";
  trigger.setAttribute("aria-label", "More actions");
  trigger.innerHTML = icon("ellipsis-vertical", 16);

  const popup = document.createElement("div");
  popup.className = "menu-popup hidden";
  items.forEach((item) => {
    const btn = document.createElement("button");
    btn.className = item.danger ? "menu-item danger" : "menu-item";
    btn.innerHTML = `${icon(item.icon, 14)} ${item.label}`;
    btn.addEventListener("click", () => {
      popup.classList.add("hidden");
      item.onClick();
    });
    popup.appendChild(btn);
  });

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    const wasOpen = !popup.classList.contains("hidden");
    closeAllCardMenus();
    popup.classList.toggle("hidden", wasOpen);
    // Flip upwards when there is not enough room below.
    if (!wasOpen) {
      const room = window.innerHeight - trigger.getBoundingClientRect().bottom;
      popup.classList.toggle("drop-up", room < popup.offsetHeight + 16);
    }
    refreshIcons();
  });

  wrap.appendChild(trigger);
  wrap.appendChild(popup);
  return wrap;
}

function closeAllCardMenus() {
  document.querySelectorAll(".menu-popup").forEach((p) => p.classList.add("hidden"));
}

async function deleteOutput(o) {
  const ok = await confirmAction({
    title: `Delete "${titleCase(o.name)}"?`,
    message: "The video, scene images and voice-over files are removed from disk. This can't be undone.",
    confirmLabel: "Delete video",
  });
  if (!ok) return;
  try {
    const res = await fetch(`/api/outputs/${encodeURIComponent(o.name)}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server returned ${res.status}`);
    }
    await loadOutputs();
    toast(`Deleted "${titleCase(o.name)}"`);
  } catch (err) {
    toast(err.message || "Could not delete that output", "error");
  }
}

function setupLightbox() {
  $("lightbox-close").addEventListener("click", closeLightbox);
  $("lightbox-prev").addEventListener("click", (e) => { e.stopPropagation(); stepLightbox(-1); });
  $("lightbox-next").addEventListener("click", (e) => { e.stopPropagation(); stepLightbox(1); });
  $("lightbox").addEventListener("click", (e) => {
    if (e.target === $("lightbox")) closeLightbox();
  });
}

function openLightbox(images, index) {
  state.lightboxImages = images;
  state.lightboxIndex = index;
  $("lightbox").classList.remove("hidden");
  renderLightbox();
  refreshIcons();
}

function closeLightbox() {
  $("lightbox").classList.add("hidden");
}

function stepLightbox(delta) {
  const total = state.lightboxImages.length;
  state.lightboxIndex = (state.lightboxIndex + delta + total) % total;
  renderLightbox();
}

function renderLightbox() {
  const total = state.lightboxImages.length;
  $("lightbox-image").src = state.lightboxImages[state.lightboxIndex];
  $("lightbox-caption").textContent = `Scene ${state.lightboxIndex + 1} of ${total}`;
  $("lightbox-prev").disabled = total < 2;
  $("lightbox-next").disabled = total < 2;
}

/* ---------------- Remix background music ---------------- */

function setupRemix() {
  const close = () => {
    stopMusicPreview();
    $("remix-overlay").classList.add("hidden");
    $("remix-modal").classList.add("hidden");
  };
  $("remix-close").addEventListener("click", close);
  $("remix-cancel").addEventListener("click", close);
  $("remix-overlay").addEventListener("click", close);

  $("remix-music-volume").addEventListener("input", (e) => {
    $("remix-music-out").textContent = Number(e.target.value) === 0 ? "Off" : `${Math.round(e.target.value * 100)}%`;
  });
  $("remix-ambience-volume").addEventListener("input", (e) => {
    $("remix-ambience-out").textContent = Number(e.target.value) === 0 ? "Off" : `${Math.round(e.target.value * 100)}%`;
  });

  $("remix-start").addEventListener("click", startRemix);
}

async function openRemixModal(output) {
  stopMusicPreview();
  state.remixTarget = output.name;
  state.remixTrack = "";
  $("remix-story").textContent = titleCase(output.name);
  $("remix-progress-track").hidden = true;
  $("remix-status").hidden = true;
  $("remix-start").disabled = false;

  const res = await fetch("/api/assets");
  const { assets } = await res.json();
  renderRemixTracks(assets);

  $("remix-overlay").classList.remove("hidden");
  $("remix-modal").classList.remove("hidden");
  refreshIcons();
}

function renderRemixTracks(assets) {
  const browser = $("remix-music-browser");
  browser.innerHTML = "";

  const entries = [{ path: "", label: "No music (voice only)" }].concat(
    assets.map((f) => ({ path: `assets/${f}`, label: titleCase(f.replace(/\.[^.]+$/, "")) }))
  );

  entries.forEach(({ path, label }) => {
    const item = document.createElement("div");
    item.className = path === state.remixTrack ? "music-item selected" : "music-item";

    const play = document.createElement("button");
    play.type = "button";
    play.className = "music-play";
    play.dataset.path = path;
    play.disabled = !path;
    play.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMusicPlayback(path);
    });

    const name = document.createElement("span");
    name.className = "music-name";
    name.textContent = label;

    item.appendChild(play);
    item.appendChild(name);
    if (path === state.remixTrack) {
      const check = document.createElement("span");
      check.className = "music-check";
      check.innerHTML = icon("check", 15);
      item.appendChild(check);
    }

    item.addEventListener("click", () => {
      state.remixTrack = path;
      renderRemixTracks(assets);
    });

    browser.appendChild(item);
  });
  syncMusicIcons();
}

async function startRemix() {
  const name = state.remixTarget;
  $("remix-start").disabled = true;
  $("remix-progress-track").hidden = false;
  $("remix-status").hidden = false;
  $("remix-status").textContent = "Starting\u2026";
  $("remix-progress-fill").style.width = "5%";

  const res = await fetch(`/api/outputs/${encodeURIComponent(name)}/remix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      music_file: state.remixTrack || null,
      music_volume: parseFloat($("remix-music-volume").value),
      ambience_volume: parseFloat($("remix-ambience-volume").value),
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    $("remix-status").textContent = err.detail || "Could not start";
    $("remix-start").disabled = false;
    return;
  }

  const { job_id } = await res.json();
  const source = new EventSource(`/api/generate/${job_id}/stream`);
  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    if (event.type === "progress") {
      const percent = stagePercent(event);
      $("remix-status").textContent = event.message;
      if (percent !== null) $("remix-progress-fill").style.width = percent + "%";
    } else if (event.type === "complete") {
      $("remix-progress-fill").style.width = "100%";
      $("remix-status").textContent = "Finished";
      toast("Music updated");
    } else if (event.type === "error") {
      $("remix-status").textContent = event.message;
      toast("Re-render failed", "error");
    } else if (event.type === "end") {
      source.close();
      $("remix-start").disabled = false;
      loadOutputs();
    }
  };
  source.onerror = () => {
    source.close();
    $("remix-start").disabled = false;
  };
}

async function testInstagram() {
  const btn = $("ig-test-btn");
  const status = $("ig-test-status");
  btn.disabled = true;
  btn.innerHTML = `${icon("loader-circle", 14)} Checking…`;
  status.className = "connection-status";
  status.textContent = "Asking Instagram…";
  refreshIcons();

  try {
    const res = await fetch("/api/instagram/test", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not verify those credentials.");

    const quota = data.quota_total ? ` · ${data.quota_used ?? 0}/${data.quota_total} posts used today` : "";
    status.className = data.can_publish ? "connection-status ok" : "connection-status warn";
    status.textContent = data.can_publish
      ? `Connected as @${data.username} (${data.account_type || "professional"})${quota}`
      : `@${data.username} is a ${data.account_type} account, which cannot publish through the API. Switch it to Business or Creator.`;
  } catch (err) {
    status.className = "connection-status error";
    status.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `${icon("plug-zap", 14)} Test connection`;
    refreshIcons();
  }
}

function setupOutputsToolbar() {
  $("outputs-search").addEventListener("input", renderOutputs);
  $("outputs-sort").addEventListener("change", renderOutputs);
  document.querySelectorAll("#outputs-filter .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#outputs-filter .chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.outputFilter = chip.dataset.filter;
      renderOutputs();
    });
  });
  $("outputs-refresh-btn").addEventListener("click", async () => {
    await loadOutputs();
    toast("Outputs refreshed");
  });
}

/* ---------------- Init ---------------- */

async function init() {
  setupTabs();
  setupSaveBar();
  setupProviderToggle();
  setupAdvancedDrawer();
  setupRanges();
  setupStylePresets();
  setupStorySelect();
  setupMusicUpload();
  setupSummaryWatchers();
  setupGenerate();
  setupPrompts();
  setupOutputsToolbar();
  setupVoicePreview();
  setupLightbox();
  setupRemix();
  setupConfirm();
  setupPoetry();
  setupPublish();

  await loadStoriesList();
  await loadCategoriesIntoSelect($("opt-category"));
  await loadMusicAssets();
  await loadConfigSummary();

  enhanceAllSelects();
  updateSummary();
  refreshIcons();

  await loadOutputCount();

  const requested = location.hash.replace("#", "");
  switchTab(TABS.includes(requested) ? requested : "story");
}

async function loadConfigSummary() {
  try {
    const res = await fetch("/api/config");
    const fields = await res.json();
    state.config = fields;
    state.imageProvider = fields.find((f) => f.key === "IMAGE_PROVIDER")?.value || "local";
  } catch {
    state.config = [];
  }
}

async function loadOutputCount() {
  try {
    const res = await fetch("/api/outputs");
    const data = await res.json();
    state.outputs = data.outputs;
    $("nav-outputs-count").textContent = data.outputs.length || "";
  } catch {
    $("nav-outputs-count").textContent = "";
  }
}

function setupGlobalKeys() {
  document.addEventListener("keydown", (e) => {
    if (!$("lightbox").classList.contains("hidden")) {
      if (e.key === "ArrowLeft") return stepLightbox(-1);
      if (e.key === "ArrowRight") return stepLightbox(1);
      if (e.key === "Escape") return closeLightbox();
    }
    if (e.key !== "Escape") return;
    if (confirmResolver) return closeConfirm(false);
    if (!$("insights-modal").classList.contains("hidden")) {
      $("insights-overlay").classList.add("hidden");
      return $("insights-modal").classList.add("hidden");
    }
    if (!$("publish-modal").classList.contains("hidden")) {
      $("publish-overlay").classList.add("hidden");
      return $("publish-modal").classList.add("hidden");
    }
    if (!$("poem-crop-modal").classList.contains("hidden")) return closeCropModal();
    if (!$("poem-review-modal").classList.contains("hidden")) return closePoemReview();
    if (!$("remix-modal").classList.contains("hidden")) {
      stopMusicPreview();
      $("remix-overlay").classList.add("hidden");
      return $("remix-modal").classList.add("hidden");
    }
    if (!$("review-modal").classList.contains("hidden")) return closeReviewModal();
    if (!$("advanced-drawer").classList.contains("hidden")) {
      $("advanced-drawer").classList.add("hidden");
      $("advanced-overlay").classList.add("hidden");
    }
  });

  window.addEventListener("beforeunload", (e) => {
    if (state.dirty || $("generate-btn").disabled) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
}

async function boot() {
  try {
    setupGlobalKeys();
    await init();
  } catch (err) {
    toast("Could not reach the server. Is storytube-web still running?", "error");
    console.error(err);
  } finally {
    const boot = $("boot");
    boot.classList.add("done");
    setTimeout(() => boot.remove(), 300);
  }
}

boot();
