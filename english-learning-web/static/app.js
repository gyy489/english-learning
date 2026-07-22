const state = {
  article: null,
  days: [],
  latestDay: null,
  todayWords: [],
  todayWordsRenderId: 0,
  dirty: false,
  generating: false,
  toastTimer: null,
  dictionaryClickTimer: null,
  dictionaryRequestId: 0,
  syncCheckInFlight: false,
};

const elements = {
  daySelect: document.querySelector("#daySelect"),
  articleTitle: document.querySelector("#articleTitle"),
  sourceLabel: document.querySelector("#sourceLabel"),
  reviewPlanDay: document.querySelector("#reviewPlanDay"),
  vocabularyCount: document.querySelector("#vocabularyCount"),
  activePoolCount: document.querySelector("#activePoolCount"),
  inboxWordCount: document.querySelector("#inboxWordCount"),
  dueWordCount: document.querySelector("#dueWordCount"),
  maintenancePoolCount: document.querySelector("#maintenancePoolCount"),
  archivedWordCount: document.querySelector("#archivedWordCount"),
  reviewPlanMessage: document.querySelector("#reviewPlanMessage"),
  reviewHabitMessage: document.querySelector("#reviewHabitMessage"),
  reviewPlanWords: document.querySelector("#reviewPlanWords"),
  reviewCount: document.querySelector("#reviewCount"),
  reviewWords: document.querySelector("#reviewWords"),
  sentenceCount: document.querySelector("#sentenceCount"),
  articleBody: document.querySelector("#articleBody"),
  todayWordsList: document.querySelector("#todayWordsList"),
  saveStatus: document.querySelector("#saveStatus"),
  generateStatus: document.querySelector("#generateStatus"),
  generateButton: document.querySelector("#generateButton"),
  themeButton: document.querySelector("#themeButton"),
  themeIcon: document.querySelector("#themeIcon"),
  themeColor: document.querySelector("#themeColor"),
  audio: document.querySelector("#audio"),
  playButton: document.querySelector("#playButton"),
  backButton: document.querySelector("#backButton"),
  forwardButton: document.querySelector("#forwardButton"),
  progress: document.querySelector("#progress"),
  currentTime: document.querySelector("#currentTime"),
  duration: document.querySelector("#duration"),
  volume: document.querySelector("#volume"),
  dictionaryPopover: document.querySelector("#dictionaryPopover"),
  dictionaryWord: document.querySelector("#dictionaryWord"),
  dictionaryPhonetic: document.querySelector("#dictionaryPhonetic"),
  dictionaryClose: document.querySelector("#dictionaryClose"),
  dictionaryLoading: document.querySelector("#dictionaryLoading"),
  dictionaryContent: document.querySelector("#dictionaryContent"),
  dictionaryChinese: document.querySelector("#dictionaryChinese"),
  dictionaryEnglish: document.querySelector("#dictionaryEnglish"),
  toast: document.querySelector("#toast"),
};

const THEME_STORAGE_KEY = "english-learning-theme";
const dictionaryCache = new Map();
const SESSION_TOKEN = globalThis.crypto?.randomUUID?.()
  || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
let sessionRegistered = false;

async function registerSession() {
  try {
    await request("/api/session", {
      method: "POST",
      body: JSON.stringify({ token: SESSION_TOKEN }),
    });
    sessionRegistered = true;
  } catch {
    // The normal page requests will show the useful connection error.
  }
}

function closeSession() {
  sessionRegistered = false;
  const body = JSON.stringify({ token: SESSION_TOKEN });
  const beacon = new Blob([body], { type: "application/json" });
  if (navigator.sendBeacon?.("/api/session-close", beacon)) return;
  fetch("/api/session-close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {
    // Closing the page must not show an error to the user.
  });
}

function applyTheme(theme, persist = false) {
  const resolvedTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = resolvedTheme;
  const isDark = resolvedTheme === "dark";
  elements.themeIcon.textContent = isDark ? "☀" : "☾";
  elements.themeButton.title = isDark ? "切换到浅色主题" : "切换到暗色主题";
  elements.themeButton.setAttribute("aria-label", elements.themeButton.title);
  elements.themeButton.setAttribute("aria-pressed", String(isDark));
  elements.themeColor.content = isDark ? "#141714" : "#f4f3ee";
  if (persist) {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, resolvedTheme);
    } catch {
      // The selected theme still applies for the current page.
    }
  }
}

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

applyTheme(currentTheme());

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败 (${response.status})`);
  }
  return payload;
}

function renderReviewPlan(payload) {
  const summary = payload?.summary || {};
  const habits = payload?.habits || {};
  const plan = payload?.nextPlan || {};
  const recentWords = Array.isArray(plan.recentWords) ? plan.recentWords : [];
  const dueWords = Array.isArray(plan.dueWords) ? plan.dueWords : [];
  const admittedWords = Array.isArray(plan.admittedWords) ? plan.admittedWords : [];
  const maintenanceWords = Array.isArray(plan.maintenanceWords) ? plan.maintenanceWords : [];
  const targetWords = Array.isArray(plan.targetWords) ? plan.targetWords : [];
  const dueSet = new Set(dueWords);
  const admittedSet = new Set(admittedWords);
  const maintenanceSet = new Set(maintenanceWords);

  elements.reviewPlanDay.textContent = `第 ${plan.nextDay || "—"} 天计划`;
  elements.vocabularyCount.textContent = String(summary.totalWords ?? 0);
  elements.activePoolCount.textContent = `${summary.activePoolWords ?? 0}/60`;
  elements.inboxWordCount.textContent = String(summary.inboxWords ?? 0);
  elements.dueWordCount.textContent = String(plan.totalDueCount ?? 0);
  elements.maintenancePoolCount.textContent = `${summary.maintenancePoolWords ?? 0}/120`;
  elements.archivedWordCount.textContent = String(summary.archivedWords ?? 0);

  const deferred = Number(plan.deferredDueCount || 0);
  const deferredRecent = Number(plan.deferredRecentCount || 0);
  const deferredParts = [];
  if (deferredRecent) deferredParts.push(`${deferredRecent} 个本篇生词`);
  if (deferred) deferredParts.push(`${deferred} 个到期旧词`);
  const deferredText = deferredParts.length ? `，另有 ${deferredParts.join("、")}顺延` : "";
  elements.reviewPlanMessage.textContent = targetWords.length
    ? `下一篇固定不超过 15 个：重学/本篇词 ${recentWords.length} 个，到期词 ${dueWords.length} 个，收件箱新激活 ${admittedWords.length} 个${deferredText}。`
    : "下一篇当前没有必须复习的目标词；系统最多只会激活 2 个新词。";
  const recentWindow = Number(habits.recentWindow || 0);
  elements.reviewHabitMessage.textContent = recentWindow
    ? `最近 ${recentWindow} 篇回忆成功率 ${habits.recentRecallRate ?? 0}%，平均每篇标记 ${habits.averageMarkedWords ?? 0} 个生词。`
    : "完成下一篇学习后，这里会开始记录你的复习习惯。";

  elements.reviewPlanWords.replaceChildren();
  for (const word of targetWords) {
    const chip = document.createElement("span");
    const kind = admittedSet.has(word) ? " admitted" : dueSet.has(word) ? " due" : "";
    chip.className = `review-plan-word${kind}`;
    chip.textContent = word;
    chip.title = admittedSet.has(word)
      ? "从收件箱新激活"
      : maintenanceSet.has(word)
        ? "长期维护词"
        : dueSet.has(word)
          ? "活跃池到期词"
          : "仍不会，优先重学";
    elements.reviewPlanWords.append(chip);
  }
}

async function loadReviewPlan() {
  try {
    renderReviewPlan(await request("/api/review-plan"));
  } catch (error) {
    elements.reviewPlanMessage.textContent = `无法读取复习计划：${error.message}`;
  }
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => elements.toast.classList.remove("visible"), 2200);
}

function conciseError(error, fallback = "操作失败，请稍后重试") {
  const message = String(error?.message || fallback).trim();
  if (message.length <= 240) return message;
  if (message.includes("invalid_request_error") || message.includes("Error code: 400")) {
    return "文章生成失败：OpenAI 请求格式或模型配置不兼容，请重试。";
  }
  return `${message.slice(0, 220)}…`;
}

function closeDictionary() {
  window.clearTimeout(state.dictionaryClickTimer);
  state.dictionaryRequestId += 1;
  elements.dictionaryPopover.hidden = true;
}

function positionDictionary(anchor) {
  const anchorRect = anchor.getBoundingClientRect();
  const popoverRect = elements.dictionaryPopover.getBoundingClientRect();
  const margin = 12;
  const maxLeft = window.innerWidth - popoverRect.width - margin;
  const left = Math.max(margin, Math.min(anchorRect.left, maxLeft));
  let top = anchorRect.bottom + 8;
  if (top + popoverRect.height > window.innerHeight - margin) {
    top = Math.max(margin, anchorRect.top - popoverRect.height - 8);
  }
  elements.dictionaryPopover.style.left = `${left}px`;
  elements.dictionaryPopover.style.top = `${top}px`;
}

async function openDictionary(rawWord, anchor) {
  const requestId = ++state.dictionaryRequestId;
  elements.dictionaryWord.textContent = rawWord.toLowerCase();
  elements.dictionaryPhonetic.textContent = "";
  elements.dictionaryLoading.textContent = "查询中...";
  elements.dictionaryLoading.hidden = false;
  elements.dictionaryContent.hidden = true;
  elements.dictionaryPopover.hidden = false;
  positionDictionary(anchor);

  try {
    const result = await lookupDictionary(rawWord);
    if (requestId !== state.dictionaryRequestId) return;
    elements.dictionaryWord.textContent = result.word;
    elements.dictionaryPhonetic.textContent = result.phonetic ? `/${result.phonetic}/` : "";
    elements.dictionaryChinese.textContent = result.translation || "暂无中文释义";
    elements.dictionaryEnglish.textContent = result.definition || "No English definition available.";
    elements.dictionaryLoading.hidden = true;
    elements.dictionaryContent.hidden = false;
    positionDictionary(anchor);
  } catch (error) {
    if (requestId !== state.dictionaryRequestId) return;
    elements.dictionaryLoading.textContent = error.message;
    positionDictionary(anchor);
  }
}

function lookupDictionary(rawWord) {
  const key = rawWord.trim().toLowerCase();
  if (!dictionaryCache.has(key)) {
    const pending = request(`/api/dictionary?word=${encodeURIComponent(rawWord)}`).catch((error) => {
      dictionaryCache.delete(key);
      throw error;
    });
    dictionaryCache.set(key, pending);
  }
  return dictionaryCache.get(key);
}

function scheduleDictionary(rawWord, anchor) {
  window.clearTimeout(state.dictionaryClickTimer);
  state.dictionaryClickTimer = window.setTimeout(() => {
    openDictionary(rawWord, anchor);
  }, 220);
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "0:00";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

function refreshSelectedTokens() {
  const selected = new Set(state.todayWords);
  document.querySelectorAll(".word-token").forEach((token) => {
    token.classList.toggle("selected", selected.has(token.dataset.lemma));
  });
}

function conciseTranslation(translation) {
  const firstSense = String(translation || "").split("；", 1)[0].trim();
  if (!firstSense) return "暂无中文释义";
  return firstSense.length > 34 ? `${firstSense.slice(0, 34)}…` : firstSense;
}

function renderTodayWords() {
  const renderId = ++state.todayWordsRenderId;
  elements.todayWordsList.replaceChildren();
  for (const word of state.todayWords) {
    const item = document.createElement("div");
    item.className = "review-item today-word-item";

    const wordElement = document.createElement("div");
    wordElement.className = "review-word dictionary-list-word";
    wordElement.textContent = word;
    wordElement.addEventListener("click", (event) => {
      event.stopPropagation();
      scheduleDictionary(word, wordElement);
    });

    const meaning = document.createElement("div");
    meaning.className = "review-meaning translation-faded";
    meaning.textContent = "查询中...";

    const removeButton = document.createElement("button");
    removeButton.className = "remove-word-button";
    removeButton.type = "button";
    removeButton.textContent = "×";
    removeButton.title = `移除 ${word}`;
    removeButton.setAttribute("aria-label", removeButton.title);
    removeButton.addEventListener("click", (event) => {
      event.stopPropagation();
      removeTodayWord(word);
    });

    item.append(wordElement, meaning, removeButton);
    elements.todayWordsList.append(item);
    lookupDictionary(word)
      .then((result) => {
        if (renderId === state.todayWordsRenderId && item.isConnected) {
          meaning.textContent = conciseTranslation(result.translation);
          meaning.title = result.translation || "";
        }
      })
      .catch(() => {
        if (renderId === state.todayWordsRenderId && item.isConnected) {
          meaning.textContent = "暂无释义";
        }
      });
  }
}

function setTodayWords(words) {
  state.todayWords = [...new Set(words.map((word) => String(word).trim().toLowerCase()).filter(Boolean))];
  renderTodayWords();
  refreshSelectedTokens();
}

async function saveTodayWords(words = state.todayWords) {
  const day = state.article?.day;
  if (!day) return false;
  elements.saveStatus.textContent = "保存中...";
  elements.saveStatus.className = "save-status saving";
  try {
    const result = await request("/api/today-words", {
      method: "POST",
      body: JSON.stringify({ day, words }),
    });
    if (state.article?.day === result.day) {
      setTodayWords(result.words);
      if (result.updatedAt) state.article.updatedAt = result.updatedAt;
      state.dirty = false;
      elements.saveStatus.textContent = "已保存";
      elements.saveStatus.className = "save-status";
    }
    if (result.reviewPlan) renderReviewPlan(result.reviewPlan);
    return true;
  } catch (error) {
    elements.saveStatus.textContent = "保存失败";
    elements.saveStatus.className = "save-status error";
    showToast(error.message);
    return false;
  }
}

async function commitTodayWords(words) {
  const previousWords = [...state.todayWords];
  setTodayWords(words);
  state.dirty = true;
  elements.saveStatus.textContent = "保存中...";
  elements.saveStatus.className = "save-status saving";
  if (await saveTodayWords()) return true;
  setTodayWords(previousWords);
  state.dirty = false;
  return false;
}

async function removeTodayWord(word) {
  const saved = await commitTodayWords(state.todayWords.filter((item) => item !== word));
  if (saved) showToast(`已移除 ${word}`);
}

async function toggleWord(rawWord) {
  try {
    const result = await request("/api/lemma", {
      method: "POST",
      body: JSON.stringify({ word: rawWord }),
    });
    const lemma = result.word;
    if (!lemma) return;
    document.querySelectorAll(".word-token").forEach((token) => {
      if (token.dataset.original === rawWord.toLowerCase()) {
        token.dataset.lemma = lemma;
      }
    });
    const selected = new Set(state.todayWords);
    let message;
    if (selected.has(lemma)) {
      selected.delete(lemma);
      message = `已取消 ${lemma}`;
    } else {
      selected.add(lemma);
      message = `已加入 ${lemma}`;
    }
    if (await commitTodayWords([...selected])) showToast(message);
  } catch (error) {
    showToast(error.message);
  }
}

function localLemma(rawWord) {
  const irregular = {
    was: "be", were: "be", is: "be", are: "be", been: "be",
    began: "begin", came: "come", did: "do", fell: "fall", found: "find",
    gave: "give", gone: "go", had: "have", has: "have", leaves: "leaf",
    made: "make", people: "person", ran: "run", reached: "reach", saw: "see",
    took: "take", went: "go", wrote: "write", argued: "argue",
  };
  const sEndingBaseForms = new Set([
    "analysis", "business", "class", "fish", "gas", "glass",
    "his", "news", "process", "series", "species", "this",
  ]);
  const invariantForms = new Set([
    "always", "anything", "during", "evening", "morning", "nothing",
    "perhaps", "something", "spring", "thus",
  ]);
  let word = rawWord.toLowerCase().replace("’", "'").replace(/'s$/, "");
  if (irregular[word]) return irregular[word];
  if (invariantForms.has(word)) return word;
  if (word.length > 4 && word.endsWith("ies")) return `${word.slice(0, -3)}y`;
  if (word.length > 4 && word.endsWith("ves")) return `${word.slice(0, -3)}f`;
  if (word.length > 5 && word.endsWith("ing")) {
    let stem = word.slice(0, -3);
    if (stem.length > 2 && stem.at(-1) === stem.at(-2) && !/[lsz]/.test(stem.at(-1))) {
      stem = stem.slice(0, -1);
    }
    if (/(mak|tak|writ|mov|us|giv|shap)$/.test(stem)) stem += "e";
    return stem;
  }
  if (word.length > 4 && word.endsWith("ed")) {
    let stem = word.slice(0, -2);
    if (stem.endsWith("i")) return `${stem.slice(0, -1)}y`;
    if (stem.length > 2 && stem.at(-1) === stem.at(-2)) stem = stem.slice(0, -1);
    if (/(argu|creat|mov|us|prepar|shap)$/.test(stem)) stem += "e";
    return stem;
  }
  if (word.length > 4 && word.endsWith("s") && !sEndingBaseForms.has(word) && !/(ss|us|is)$/.test(word)) {
    return word.slice(0, -1);
  }
  return word;
}

function createWordToken(part) {
  const token = document.createElement("span");
  token.className = "word-token";
  token.textContent = part;
  token.dataset.original = part.toLowerCase();
  token.dataset.lemma = localLemma(part);
  token.addEventListener("click", (event) => {
    event.stopPropagation();
    scheduleDictionary(part, token);
  });
  token.addEventListener("dblclick", (event) => {
    event.preventDefault();
    window.clearTimeout(state.dictionaryClickTimer);
    closeDictionary();
    window.getSelection()?.removeAllRanges();
    toggleWord(part);
  });
  return token;
}

function createHardTranslatedSentence(entry) {
  const fragment = document.createDocumentFragment();
  const segments = Array.isArray(entry.glosses) ? entry.glosses : [];
  if (!segments.length) return fragment;
  for (const segment of segments) {
    if (!segment.isWord) {
      fragment.append(document.createTextNode(segment.text || ""));
      continue;
    }
    const pair = document.createElement("span");
    pair.className = "word-pair";
    pair.append(createWordToken(segment.text));
    const gloss = document.createElement("span");
    gloss.className = "word-gloss translation-faded";
    gloss.textContent = segment.gloss || "";
    pair.append(gloss);
    fragment.append(pair);
  }
  return fragment;
}

function renderArticle(article) {
  closeDictionary();
  state.article = article;
  state.dirty = false;
  elements.daySelect.value = String(article.day);
  elements.articleTitle.textContent = article.title;
  elements.sourceLabel.textContent = article.metadata["来源真题"] || "";

  elements.reviewCount.textContent = `${article.reviewWords.length} 个`;
  elements.reviewWords.replaceChildren();
  for (const entry of article.reviewWords) {
    const item = document.createElement("div");
    item.className = "review-item";
    const word = document.createElement("div");
    word.className = "review-word";
    word.textContent = entry.word;
    const meaning = document.createElement("div");
    meaning.className = "review-meaning translation-faded";
    meaning.textContent = entry.meaning;
    item.append(word, meaning);
    elements.reviewWords.append(item);
  }

  elements.sentenceCount.textContent = `${article.sentences.length} 句`;
  elements.articleBody.replaceChildren();
  for (const entry of article.sentences) {
    const row = document.createElement("article");
    row.className = "sentence";
    const number = document.createElement("div");
    number.className = "sentence-number";
    number.textContent = entry.number;
    const text = document.createElement("div");
    const english = document.createElement("div");
    english.className = "english";
    english.append(createHardTranslatedSentence(entry));
    text.append(english);
    row.append(number, text);
    elements.articleBody.append(row);
  }

  setTodayWords(article.todayWords);
  configureAudio(article);
  updateGenerateButton();
}

function configureAudio(article) {
  const enabled = article.audioAvailable;
  elements.playButton.disabled = !enabled;
  elements.backButton.disabled = !enabled;
  elements.forwardButton.disabled = !enabled;
  elements.progress.disabled = !enabled;
  if (enabled) {
    elements.audio.src = `${article.audioUrl}?day=${article.day}`;
    elements.audio.volume = Number(elements.volume.value);
  } else {
    elements.audio.removeAttribute("src");
    elements.audio.load();
  }
}

async function loadCurrentArticle(day = null) {
  try {
    const suffix = day ? `?day=${encodeURIComponent(day)}` : "";
    renderArticle(await request(`/api/current${suffix}`));
    return true;
  } catch (error) {
    elements.articleTitle.textContent = "无法读取文章";
    showToast(error.message);
    return false;
  }
}

async function checkExternalChanges() {
  if (
    state.syncCheckInFlight
    || !state.article
    || state.generating
    || state.dirty
    || document.visibilityState === "hidden"
  ) {
    return;
  }
  state.syncCheckInFlight = true;
  try {
    const result = await request(
      `/api/article-version?day=${encodeURIComponent(state.article.day)}`,
    );
    if (
      state.article
      && Number(result.updatedAt) !== Number(state.article.updatedAt)
    ) {
      const day = state.article.day;
      if (await loadCurrentArticle(day)) {
        await loadReviewPlan();
        showToast("已从项目文件同步最新内容");
      }
    }
  } catch {
    // 后台同步失败时不影响正常阅读和操作。
  } finally {
    state.syncCheckInFlight = false;
  }
}

async function loadDayOptions(preferredDay = null) {
  const result = await request("/api/days");
  state.days = result.days;
  state.latestDay = result.latestDay;
  elements.daySelect.replaceChildren();
  for (const article of state.days) {
    const option = document.createElement("option");
    option.value = String(article.day);
    option.textContent = `第 ${article.day} 天 · ${article.title}`;
    elements.daySelect.append(option);
  }
  elements.daySelect.value = String(preferredDay || state.latestDay);
}

function updateGenerateButton() {
  const isLatestDay = state.article?.day === state.latestDay;
  elements.generateButton.disabled = state.generating || !isLatestDay;
  elements.generateButton.title = isLatestDay ? "" : `请先切换到第 ${state.latestDay} 天`;
}

function seekBy(seconds) {
  if (!elements.audio.src) return;
  elements.audio.currentTime = Math.max(
    0,
    Math.min(elements.audio.duration || Infinity, elements.audio.currentTime + seconds),
  );
}

async function togglePlayback() {
  if (!elements.audio.src) return;
  if (elements.audio.paused) {
    await elements.audio.play();
  } else {
    elements.audio.pause();
  }
}

elements.playButton.addEventListener("click", () => togglePlayback().catch((error) => showToast(error.message)));
elements.backButton.addEventListener("click", () => seekBy(-5));
elements.forwardButton.addEventListener("click", () => seekBy(5));
elements.volume.addEventListener("input", () => {
  elements.audio.volume = Number(elements.volume.value);
});
elements.progress.addEventListener("input", () => {
  if (Number.isFinite(elements.audio.duration)) {
    elements.audio.currentTime = (Number(elements.progress.value) / 100) * elements.audio.duration;
  }
});
elements.audio.addEventListener("play", () => {
  elements.playButton.textContent = "❚❚";
});
elements.audio.addEventListener("pause", () => {
  elements.playButton.textContent = "▶";
});
elements.audio.addEventListener("loadedmetadata", () => {
  elements.duration.textContent = formatTime(elements.audio.duration);
});
elements.audio.addEventListener("timeupdate", () => {
  elements.currentTime.textContent = formatTime(elements.audio.currentTime);
  const percent = Number.isFinite(elements.audio.duration)
    ? (elements.audio.currentTime / elements.audio.duration) * 100
    : 0;
  elements.progress.value = String(percent || 0);
});
elements.dictionaryClose.addEventListener("click", closeDictionary);
document.addEventListener("click", (event) => {
  if (!elements.dictionaryPopover.contains(event.target)) closeDictionary();
});
window.addEventListener("scroll", closeDictionary, { passive: true });
window.addEventListener("resize", closeDictionary);
elements.daySelect.addEventListener("change", async () => {
  const selectedDay = Number(elements.daySelect.value);
  const previousDay = state.article?.day;
  if (selectedDay === previousDay) return;

  elements.daySelect.disabled = true;
  try {
    if (state.dirty) {
      const saved = await saveTodayWords();
      if (!saved) {
        elements.daySelect.value = String(previousDay);
        return;
      }
    }
    elements.audio.pause();
    const loaded = await loadCurrentArticle(selectedDay);
    if (!loaded) {
      elements.daySelect.value = String(previousDay);
      return;
    }
    window.scrollTo({ top: 0 });
  } finally {
    elements.daySelect.disabled = false;
  }
});
elements.themeButton.addEventListener("click", () => {
  applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.dictionaryPopover.hidden) {
    closeDictionary();
    return;
  }
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
    return;
  }
  if (event.code === "Space") {
    event.preventDefault();
    togglePlayback().catch((error) => showToast(error.message));
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    seekBy(-5);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    seekBy(5);
  }
});

elements.generateButton.addEventListener("click", async () => {
  if (state.article?.day !== state.latestDay) return;
  if (!(await saveTodayWords())) return;
  state.generating = true;
  updateGenerateButton();
  elements.generateStatus.textContent = "正在生成文章和音频，这可能需要几分钟...";
  elements.generateStatus.className = "generate-status";
  try {
    const result = await request("/api/generate-next", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const audioStatus = result.warning
      ? conciseError({ message: result.warning }, "音频未生成")
      : `第 ${result.day} 天文章已生成，音频未生成`;
    elements.generateStatus.textContent = result.audioGenerated
      ? `第 ${result.day} 天已生成`
      : audioStatus;
    showToast(`${result.mode}：第 ${result.day} 天已生成`);
    await loadDayOptions(result.day);
    await loadCurrentArticle(result.day);
    if (result.reviewPlan) renderReviewPlan(result.reviewPlan);
    else await loadReviewPlan();
  } catch (error) {
    const message = conciseError(error, "文章生成失败，请稍后重试");
    elements.generateStatus.textContent = message;
    elements.generateStatus.className = "generate-status error";
    showToast(message);
  } finally {
    state.generating = false;
    updateGenerateButton();
  }
});

async function initialize() {
  try {
    await registerSession();
    await loadDayOptions();
    await loadCurrentArticle(state.latestDay);
    await loadReviewPlan();
  } catch (error) {
    elements.articleTitle.textContent = "无法读取文章";
    showToast(error.message);
  }
}

initialize();
window.setInterval(checkExternalChanges, 3000);
window.addEventListener("pageshow", registerSession);
window.addEventListener("pagehide", (event) => {
  if (!event.persisted) closeSession();
});
