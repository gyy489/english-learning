const state = {
  article: null,
  days: [],
  latestDay: null,
  reviewWordCount: 0,
  reviewWordsExpanded: false,
  todayWords: [],
  todayWordMeanings: {},
  todayWordsExpanded: false,
  todayWordsRenderId: 0,
  dirty: false,
  generating: false,
  learningView: "reading",
  writingPractice: null,
  writingLoadedDay: null,
  writingCreating: false,
  writingSubmitting: false,
  writingDraftSyncTimer: null,
  writingDraftSaving: false,
  writingDraftLastSyncedText: "",
  writingDraftRequestId: 0,
  toastTimer: null,
  dictionaryClickTimer: null,
  dictionaryRequestId: 0,
  syncCheckInFlight: false,
};

const elements = {
  appShell: document.querySelector(".app-shell"),
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
  reviewSection: document.querySelector("#reviewSection"),
  reviewWordsToggle: document.querySelector("#reviewWordsToggle"),
  sentenceCount: document.querySelector("#sentenceCount"),
  articleBody: document.querySelector("#articleBody"),
  todayWordsList: document.querySelector("#todayWordsList"),
  todaySection: document.querySelector("#todaySection"),
  todayWordsToggle: document.querySelector("#todayWordsToggle"),
  saveStatus: document.querySelector("#saveStatus"),
  generateStatus: document.querySelector("#generateStatus"),
  generateInstruction: document.querySelector("#generateInstruction"),
  generateButton: document.querySelector("#generateButton"),
  completeReadingButton: document.querySelector("#completeReadingButton"),
  readingTab: document.querySelector("#readingTab"),
  writingTab: document.querySelector("#writingTab"),
  readingView: document.querySelector("#readingView"),
  writingView: document.querySelector("#writingView"),
  writingDayLabel: document.querySelector("#writingDayLabel"),
  writingAvailability: document.querySelector("#writingAvailability"),
  writingCreateButton: document.querySelector("#writingCreateButton"),
  writingContent: document.querySelector("#writingContent"),
  writingFocusCard: document.querySelector("#writingFocusCard"),
  writingFocusTitle: document.querySelector("#writingFocusTitle"),
  writingFocusExplanation: document.querySelector("#writingFocusExplanation"),
  writingFocusMethod: document.querySelector("#writingFocusMethod"),
  writingTitle: document.querySelector("#writingTitle"),
  writingInstructions: document.querySelector("#writingInstructions"),
  writingTargetWords: document.querySelector("#writingTargetWords"),
  writingExercise: document.querySelector("#writingExercise"),
  writingWordCount: document.querySelector("#writingWordCount"),
  writingSyncStatus: document.querySelector("#writingSyncStatus"),
  correctionLevel: document.querySelector("#correctionLevel"),
  writingSubmitButton: document.querySelector("#writingSubmitButton"),
  writingStatus: document.querySelector("#writingStatus"),
  writingAttemptsSection: document.querySelector("#writingAttemptsSection"),
  writingAttemptCount: document.querySelector("#writingAttemptCount"),
  writingAttempts: document.querySelector("#writingAttempts"),
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
const WRITING_DRAFT_KEY_PREFIX = "english-learning-writing-draft-";
const WRITING_DRAFT_SYNC_DELAY_MS = 700;
const SEEK_SECONDS = 3;
const IS_LOCAL_ACCESS = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
const SYNC_INTERVAL_MS = IS_LOCAL_ACCESS ? 3000 : 30000;
const HEARTBEAT_INTERVAL_MS = 30000;
const dictionaryCache = new Map();
const SESSION_TOKEN = globalThis.crypto?.randomUUID?.()
  || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
let sessionRegistered = false;
let sessionRegistrationInFlight = null;

async function registerSession(force = false) {
  if (sessionRegistrationInFlight) return sessionRegistrationInFlight;
  if (sessionRegistered && !force) return;
  sessionRegistrationInFlight = request("/api/session", {
      method: "POST",
      body: JSON.stringify({ token: SESSION_TOKEN }),
    })
    .then(() => {
      sessionRegistered = true;
    })
    .catch(() => {
      sessionRegistered = false;
      // The normal page requests will show the useful connection error.
    })
    .finally(() => {
      sessionRegistrationInFlight = null;
    });
  return sessionRegistrationInFlight;
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

function writingDraftKey(day) {
  return `${WRITING_DRAFT_KEY_PREFIX}${day}`;
}

function writingDraftValues() {
  return [...elements.writingExercise.querySelectorAll(".writing-input")].map((input) => input.value);
}

function writingDraftText(values = writingDraftValues()) {
  return values.map((value) => value.trim()).filter(Boolean).join("\n\n");
}

function writingDraftSignature(values = writingDraftValues()) {
  return JSON.stringify(values);
}

function updateWritingWordCount() {
  const count = (writingDraftText().match(/[A-Za-z]+(?:['’][A-Za-z]+)?/g) || []).length;
  elements.writingWordCount.textContent = `${count} 词`;
}

function saveWritingDraft() {
  const day = state.article?.day;
  if (!day) return;
  try {
    localStorage.setItem(writingDraftKey(day), JSON.stringify(writingDraftValues()));
  } catch {
    // Draft persistence is a convenience; typing must still work without storage.
  }
}

function loadWritingDraft(day, paragraphCount) {
  try {
    const saved = localStorage.getItem(writingDraftKey(day));
    if (!saved) return Array(paragraphCount).fill("");
    const parsed = JSON.parse(saved);
    if (Array.isArray(parsed)) {
      return (parsed.map((value) => String(value))
        .slice(0, paragraphCount)
        .concat(Array(paragraphCount).fill("")))
        .slice(0, paragraphCount);
    }
  } catch {
    // Legacy single-box drafts are restored by splitting blank-line paragraphs.
  }
  const legacy = localStorage.getItem(writingDraftKey(day)) || "";
  const parts = legacy ? legacy.split(/\n\s*\n/) : [];
  return (parts.slice(0, paragraphCount).concat(Array(paragraphCount).fill(""))).slice(0, paragraphCount);
}

function setWritingSyncStatus(message, stateName = "") {
  elements.writingSyncStatus.textContent = message;
  elements.writingSyncStatus.className = `writing-sync-status${stateName ? ` ${stateName}` : ""}`;
}

function queueWritingDraftSync() {
  window.clearTimeout(state.writingDraftSyncTimer);
  if (!state.writingPractice?.available) return;
  setWritingSyncStatus("正在同步到 VS Code...");
  state.writingDraftSyncTimer = window.setTimeout(() => {
    syncWritingDraft();
  }, WRITING_DRAFT_SYNC_DELAY_MS);
}

async function syncWritingDraft({ immediate = false } = {}) {
  window.clearTimeout(state.writingDraftSyncTimer);
  state.writingDraftSyncTimer = null;
  const day = state.article?.day;
  const paragraphs = writingDraftValues();
  const text = writingDraftText(paragraphs);
  const signature = writingDraftSignature(paragraphs);
  if (!day || !state.writingPractice?.available) return true;
  if (!immediate && signature === state.writingDraftLastSyncedText) {
    setWritingSyncStatus("已同步到 VS Code", "saved");
    return true;
  }
  const requestId = ++state.writingDraftRequestId;
  state.writingDraftSaving = true;
  setWritingSyncStatus("正在同步到 VS Code...");
  try {
    await request("/api/writing-draft", {
      method: "POST",
      body: JSON.stringify({ day, text, paragraphs }),
    });
    if (requestId === state.writingDraftRequestId && state.article?.day === day) {
      state.writingDraftLastSyncedText = signature;
      setWritingSyncStatus("已同步到 VS Code", "saved");
    }
    return true;
  } catch (error) {
    if (requestId === state.writingDraftRequestId && state.article?.day === day) {
      setWritingSyncStatus("本地草稿尚未同步", "error");
    }
    return false;
  } finally {
    if (requestId === state.writingDraftRequestId) state.writingDraftSaving = false;
  }
}

function setLearningView(view) {
  const nextView = view === "writing" ? "writing" : "reading";
  state.learningView = nextView;
  const writing = nextView === "writing";
  elements.readingView.hidden = writing;
  elements.writingView.hidden = !writing;
  elements.readingTab.classList.toggle("active", !writing);
  elements.writingTab.classList.toggle("active", writing);
  elements.readingTab.setAttribute("aria-selected", String(!writing));
  elements.writingTab.setAttribute("aria-selected", String(writing));
  elements.appShell.dataset.learningView = nextView;
}

function renderWritingAttempts(attempts) {
  const records = Array.isArray(attempts) ? [...attempts].reverse() : [];
  elements.writingAttempts.replaceChildren();
  elements.writingAttemptsSection.hidden = !records.length;
  elements.writingAttemptCount.textContent = records.length ? `${records.length} 次` : "";
  for (const record of records) {
    const item = document.createElement("article");
    item.className = "writing-attempt";
    const meta = document.createElement("div");
    meta.className = "writing-attempt-meta";
    const label = document.createElement("span");
    label.textContent = `第 ${record.id || "?"} 次 · ${record.levelLabel || "修正"}`;
    const date = document.createElement("span");
    const rawDate = record.submittedAt ? new Date(record.submittedAt) : null;
    date.textContent = rawDate && !Number.isNaN(rawDate.valueOf())
      ? rawDate.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
      : "";
    meta.append(label, date);
    item.append(meta);

    const addTextBlock = (heading, content, extraClass = "") => {
      if (!content) return;
      const title = document.createElement("h3");
      title.textContent = heading;
      const body = document.createElement("p");
      body.className = `writing-text${extraClass ? ` ${extraClass}` : ""}`;
      body.textContent = content;
      item.append(title, body);
    };
    addTextBlock("你的提交", record.originalText);
    addTextBlock("修正版", record.correctedText, "writing-correction");

    const feedback = Array.isArray(record.feedback) ? record.feedback : [];
    const coverage = Array.isArray(record.coverage) ? record.coverage : [];
    const suggestions = Array.isArray(record.suggestions) ? record.suggestions : [];
    if (feedback.length || coverage.length || suggestions.length) {
      const title = document.createElement("h3");
      title.textContent = "反馈";
      const list = document.createElement("ul");
      list.className = "writing-feedback";
      for (const message of [...feedback, ...coverage]) {
        const line = document.createElement("li");
        line.textContent = message;
        list.append(line);
      }
      if (suggestions.length) {
        const line = document.createElement("li");
        line.textContent = `可尝试使用：${suggestions.join("、")}`;
        list.append(line);
      }
      item.append(title, list);
    }
    elements.writingAttempts.append(item);
  }
}

function renderWritingExercise(paragraphs, drafts) {
  elements.writingExercise.replaceChildren();
  paragraphs.forEach((paragraph, index) => {
    const item = document.createElement("article");
    item.className = "writing-paragraph-exercise";

    const heading = document.createElement("h3");
    heading.textContent = `第 ${index + 1} 段`;
    const prompt = document.createElement("p");
    prompt.className = "writing-paragraph-prompt";
    prompt.textContent = paragraph;

    const input = document.createElement("textarea");
    input.className = "writing-input";
    input.rows = Math.max(5, Math.min(12, Math.ceil(paragraph.length / 70)));
    input.maxLength = 12000;
    input.placeholder = "在这里写这一段的英文翻译";
    input.value = drafts[index] || "";
    input.setAttribute("aria-label", `第 ${index + 1} 段英文翻译`);
    input.addEventListener("input", () => {
      updateWritingWordCount();
      saveWritingDraft();
      queueWritingDraftSync();
    });
    input.addEventListener("blur", () => {
      syncWritingDraft({ immediate: true });
    });

    item.append(heading, prompt, input);
    elements.writingExercise.append(item);
  });
}

// Updates only the "订正" block inside each existing paragraph article,
// without touching the draft textareas (which would lose focus/typing).
function renderWritingParagraphCorrections(corrections) {
  const items = elements.writingExercise.querySelectorAll(".writing-paragraph-exercise");
  items.forEach((item, index) => {
    const correction = corrections[index];
    let block = item.querySelector(".writing-paragraph-correction");
    if (!correction) {
      if (block) block.remove();
      return;
    }
    if (!block) {
      block = document.createElement("div");
      block.className = "writing-paragraph-correction";
      const label = document.createElement("h4");
      label.textContent = "订正";
      const text = document.createElement("p");
      text.className = "writing-text writing-correction";
      block.append(label, text);
      item.append(block);
    }
    block.querySelector("p").textContent = correction;
  });
}

function renderWritingPractice(payload) {
  state.writingPractice = payload;
  const day = state.article?.day;
  elements.writingDayLabel.textContent = day ? `第 ${day} 天` : "";
  const available = Boolean(payload?.available);
  const completed = Boolean(payload?.readingCompleted);
  elements.completeReadingButton.disabled = !available || state.generating;
  elements.completeReadingButton.textContent = completed ? "进入中译英" : "完成阅读，进入中译英";
  elements.writingCreateButton.hidden = available || !payload?.canCreate;
  elements.writingCreateButton.disabled = state.writingCreating;

  if (!available) {
    elements.writingAvailability.textContent = payload?.message || "当前日期没有中译英练习。";
    elements.writingContent.hidden = true;
    elements.writingFocusCard.hidden = true;
    elements.writingAttemptsSection.hidden = true;
    return;
  }
  elements.writingAvailability.textContent = completed
    ? "根据当天阅读改写的中文题目；可重复提交并选择不同的修正程度。"
    : "本篇中译英已准备好；可直接开始输入，也可先回到阅读页完成学习。";
  elements.writingContent.hidden = false;
  const writingFocus = payload.writingFocus;
  const hasWritingFocus = Boolean(writingFocus?.focusTitle);
  elements.writingFocusCard.hidden = !hasWritingFocus;
  elements.writingFocusTitle.textContent = hasWritingFocus ? writingFocus.focusTitle : "";
  elements.writingFocusExplanation.textContent = hasWritingFocus
    ? writingFocus.focusExplanation || ""
    : "";
  elements.writingFocusMethod.textContent = hasWritingFocus
    ? `今天的练习方法：${writingFocus.practiceInstruction || "围绕这一项反复练习。"}`
    : "";
  elements.writingTitle.textContent = payload.title || "中文题目";
  elements.writingInstructions.textContent = payload.instructions || "";
  elements.writingTargetWords.replaceChildren();
  for (const word of Array.isArray(payload.suggestedWords) ? payload.suggestedWords : []) {
    const chip = document.createElement("span");
    chip.className = "review-plan-word";
    chip.textContent = word;
    elements.writingTargetWords.append(chip);
  }
  const paragraphs = Array.isArray(payload.paragraphs) ? payload.paragraphs.map(String) : [];
  if (state.writingLoadedDay !== day) {
    const storedDrafts = Array.isArray(payload.draftParagraphs)
      ? payload.draftParagraphs.map((value) => String(value))
      : String(payload.draftText || "").split(/\n\s*\n/);
    const serverDrafts = (storedDrafts.slice(0, paragraphs.length)
      .concat(Array(paragraphs.length).fill("")))
      .slice(0, paragraphs.length);
    const localDrafts = loadWritingDraft(day, paragraphs.length);
    const drafts = serverDrafts.some(Boolean) ? serverDrafts : localDrafts;
    renderWritingExercise(paragraphs, drafts);
    state.writingLoadedDay = day;
    state.writingDraftLastSyncedText = writingDraftSignature(serverDrafts);
    if (localDrafts.some(Boolean) && !serverDrafts.some(Boolean)) queueWritingDraftSync();
  }
  const correctionParagraphs = Array.isArray(payload.latestCorrectionParagraphs)
    ? payload.latestCorrectionParagraphs.map((value) => String(value))
    : [];
  renderWritingParagraphCorrections(correctionParagraphs);
  elements.writingExercise.querySelectorAll(".writing-input").forEach((input) => {
    input.disabled = state.writingSubmitting;
  });
  elements.correctionLevel.disabled = state.writingSubmitting;
  elements.writingSubmitButton.disabled = state.writingSubmitting;
  updateWritingWordCount();
  if (!state.writingDraftSaving && state.writingDraftLastSyncedText === writingDraftSignature()) {
    setWritingSyncStatus("已同步到 VS Code", "saved");
  }
  renderWritingAttempts(payload.attempts);
}

async function loadWritingPractice() {
  const day = state.article?.day;
  if (!day) return;
  try {
    const payload = await request(`/api/writing-practice?day=${encodeURIComponent(day)}`);
    if (state.article?.day === day) renderWritingPractice(payload);
  } catch (error) {
    if (state.article?.day !== day) return;
    renderWritingPractice({ day, available: false, message: `无法读取中译英练习：${error.message}` });
  }
}

function renderReviewPlan(payload) {
  const summary = payload?.summary || {};
  const habits = payload?.habits || {};
  const plan = payload?.nextPlan || {};
  const generationMode = payload?.generationMode || {};
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
  const sourceText = generationMode.usesSource
    ? "会使用超给的听力转写作为情节参考"
    : "当前没有可用的听力情节来源";
  const planText = targetWords.length
    ? `下一篇固定不超过 15 个：重学/本篇词 ${recentWords.length} 个，到期词 ${dueWords.length} 个，收件箱新激活 ${admittedWords.length} 个${deferredText}。`
    : "下一篇当前没有必须复习的目标词；系统最多只会激活 2 个新词。";
  elements.reviewPlanMessage.textContent = `${sourceText}。${planText}`;
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
    const knownMeaning = state.todayWordMeanings[word];
    if (knownMeaning !== undefined) {
      meaning.textContent = conciseTranslation(knownMeaning) || "暂无释义";
      meaning.title = knownMeaning;
      continue;
    }
    lookupDictionary(word)
      .then((result) => {
        if (renderId === state.todayWordsRenderId && item.isConnected) {
          state.todayWordMeanings[word] = result.translation || "";
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
  updateTodayWordsVisibility();
}

function updateTodayWordsVisibility() {
  const isCompactMobile = window.matchMedia("(max-width: 760px)").matches;
  const canCollapse = isCompactMobile && state.todayWords.length > 6;
  elements.todaySection.classList.toggle(
    "mobile-collapsed",
    canCollapse && !state.todayWordsExpanded,
  );
  elements.todayWordsToggle.hidden = !canCollapse;
  elements.todayWordsToggle.setAttribute("aria-expanded", String(state.todayWordsExpanded));
  elements.todayWordsToggle.textContent = state.todayWordsExpanded
    ? "收起"
    : `展开 ${state.todayWords.length}`;
}

function updateReviewWordsVisibility() {
  const isCompactMobile = window.matchMedia("(max-width: 760px)").matches;
  const canCollapse = isCompactMobile && state.reviewWordCount > 6;
  elements.reviewSection.classList.toggle(
    "mobile-collapsed",
    canCollapse && !state.reviewWordsExpanded,
  );
  elements.reviewWordsToggle.hidden = !canCollapse;
  elements.reviewWordsToggle.setAttribute("aria-expanded", String(state.reviewWordsExpanded));
  elements.reviewWordsToggle.textContent = state.reviewWordsExpanded
    ? "收起"
    : `展开 ${state.reviewWordCount}`;
}

function setTodayWords(words, meanings = null) {
  state.todayWords = [...new Set(words.map((word) => String(word).trim().toLowerCase()).filter(Boolean))];
  if (meanings && typeof meanings === "object") {
    state.todayWordMeanings = { ...meanings };
  }
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
  if (state.article?.day !== article.day) state.writingLoadedDay = null;
  state.article = article;
  state.dirty = false;
  elements.daySelect.value = String(article.day);
  elements.articleTitle.textContent = article.title;
  elements.sourceLabel.textContent = article.metadata["来源真题"] || "";

  state.reviewWordCount = article.reviewWords.length;
  elements.reviewCount.textContent = `${state.reviewWordCount} 个`;
  elements.reviewWords.replaceChildren();
  for (const entry of article.reviewWords) {
    const item = document.createElement("div");
    item.className = "review-item";
    const word = document.createElement("div");
    word.className = "review-word dictionary-list-word";
    word.textContent = entry.word;
    word.addEventListener("click", (event) => {
      event.stopPropagation();
      scheduleDictionary(entry.word, word);
    });
    const meaning = document.createElement("div");
    meaning.className = "review-meaning translation-faded";
    meaning.textContent = entry.meaning;
    item.append(word, meaning);
    elements.reviewWords.append(item);
  }
  updateReviewWordsVisibility();

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

  setTodayWords(article.todayWords, article.todayWordMeanings);
  configureAudio(article);
  updateMediaMetadata(article);
  updateGenerateButton();
  loadWritingPractice();
}

function configureAudio(article) {
  const enabled = article.audioAvailable;
  elements.playButton.disabled = !enabled;
  elements.backButton.disabled = !enabled;
  elements.forwardButton.disabled = !enabled;
  elements.progress.disabled = !enabled;
  elements.currentTime.textContent = "0:00";
  elements.duration.textContent = enabled ? "--:--" : "0:00";
  elements.progress.value = "0";
  if (enabled) {
    elements.audio.src = `${article.audioUrl}?day=${article.day}`;
    elements.audio.preload = "auto";
    elements.audio.volume = Number(elements.volume.value);
    elements.audio.load();
  } else {
    elements.audio.removeAttribute("src");
    elements.audio.load();
  }
}

function updateMediaMetadata(article) {
  if (!("mediaSession" in navigator) || !("MediaMetadata" in window)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: article.title,
    artist: "每日英语",
    album: `第 ${article.day} 天`,
  });
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
  updateGenerateButton();
}

function updateGenerateButton() {
  const isLatestDay = state.article?.day === state.latestDay;
  elements.generateButton.disabled = state.generating || !isLatestDay;
  elements.generateButton.title = isLatestDay ? "" : `请先切换到第 ${state.latestDay} 天`;
  elements.generateInstruction.disabled = state.generating;
  if (state.writingPractice) {
    elements.completeReadingButton.disabled = !state.writingPractice.available || state.generating;
  }
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
function attachHoldSeek(button, direction) {
  let holdTimer = null;
  let repeatTimer = null;
  let longPressed = false;

  const stopHolding = () => {
    window.clearTimeout(holdTimer);
    window.clearInterval(repeatTimer);
    holdTimer = null;
    repeatTimer = null;
    button.classList.remove("holding");
  };

  button.addEventListener("pointerdown", (event) => {
    if (button.disabled || (event.button !== undefined && event.button !== 0)) return;
    longPressed = false;
    holdTimer = window.setTimeout(() => {
      longPressed = true;
      button.classList.add("holding");
      seekBy(direction * SEEK_SECONDS);
      repeatTimer = window.setInterval(() => seekBy(direction * SEEK_SECONDS), 260);
    }, 450);
  });
  button.addEventListener("pointerup", stopHolding);
  button.addEventListener("pointercancel", stopHolding);
  button.addEventListener("lostpointercapture", stopHolding);
  button.addEventListener("contextmenu", (event) => event.preventDefault());
  button.addEventListener("click", (event) => {
    if (longPressed) {
      event.preventDefault();
      longPressed = false;
      return;
    }
    seekBy(direction * SEEK_SECONDS);
  });
}

attachHoldSeek(elements.backButton, -1);
attachHoldSeek(elements.forwardButton, 1);
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
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "playing";
});
elements.audio.addEventListener("pause", () => {
  elements.playButton.textContent = "▶";
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "paused";
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

if ("mediaSession" in navigator) {
  const mediaActions = {
    play: () => elements.audio.play().catch((error) => showToast(error.message)),
    pause: () => elements.audio.pause(),
    seekbackward: (details) => seekBy(-(details?.seekOffset || SEEK_SECONDS)),
    seekforward: (details) => seekBy(details?.seekOffset || SEEK_SECONDS),
    seekto: (details) => {
      if (Number.isFinite(details?.seekTime)) elements.audio.currentTime = details.seekTime;
    },
  };
  for (const [action, handler] of Object.entries(mediaActions)) {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch {
      // Older mobile browsers may only support part of the Media Session API.
    }
  }
}
elements.dictionaryClose.addEventListener("click", closeDictionary);
document.addEventListener("click", (event) => {
  if (!elements.dictionaryPopover.contains(event.target)) closeDictionary();
});
window.addEventListener("scroll", closeDictionary, { passive: true });
window.addEventListener("resize", closeDictionary);
window.addEventListener("resize", () => {
  updateTodayWordsVisibility();
  updateReviewWordsVisibility();
});
elements.readingTab.addEventListener("click", () => setLearningView("reading"));
elements.writingTab.addEventListener("click", async () => {
  setLearningView("writing");
  await loadWritingPractice();
});
elements.completeReadingButton.addEventListener("click", async () => {
  const day = state.article?.day;
  if (!day || elements.completeReadingButton.disabled) return;
  if (!(await saveTodayWords())) return;
  elements.completeReadingButton.disabled = true;
  elements.writingStatus.textContent = "";
  try {
    const practice = await request("/api/complete-reading", {
      method: "POST",
      body: JSON.stringify({ day }),
    });
    renderWritingPractice(practice);
    setLearningView("writing");
    showToast("阅读已完成，开始中译英练习");
  } catch (error) {
    showToast(error.message);
    await loadWritingPractice();
  }
});
elements.writingCreateButton.addEventListener("click", async () => {
  const day = state.article?.day;
  if (!day || state.writingCreating) return;
  state.writingCreating = true;
  elements.writingCreateButton.disabled = true;
  elements.writingAvailability.textContent = "正在根据本篇阅读创建中译英题目...";
  try {
    const practice = await request("/api/create-writing-practice", {
      method: "POST",
      body: JSON.stringify({ day }),
    });
    renderWritingPractice(practice);
    showToast("中译英题目已创建");
  } catch (error) {
    renderWritingPractice({
      day,
      available: false,
      canCreate: true,
      message: conciseError(error, "中译英题目创建失败，请重试"),
    });
  } finally {
    state.writingCreating = false;
    if (state.writingPractice) renderWritingPractice(state.writingPractice);
  }
});
elements.writingSubmitButton.addEventListener("click", async () => {
  const day = state.article?.day;
  const text = writingDraftText();
  if (!day || state.writingSubmitting) return;
  if (!text) {
    showToast("请先输入英文内容");
    elements.writingExercise.querySelector(".writing-input")?.focus();
    return;
  }
  state.writingSubmitting = true;
  elements.writingStatus.textContent = "正在检查表达和高频词...";
  elements.writingStatus.className = "generate-status";
  await syncWritingDraft({ immediate: true });
  renderWritingPractice(state.writingPractice);
  try {
    const result = await request("/api/writing-submit", {
      method: "POST",
      body: JSON.stringify({
        day,
        text,
        level: elements.correctionLevel.value,
      }),
    });
    state.writingPractice = result.practice;
    state.writingDraftLastSyncedText = writingDraftSignature();
    renderWritingPractice(result.practice);
    elements.writingStatus.textContent = "修正版已保存，可继续修改后再次提交。";
    saveWritingDraft();
    showToast("已生成修正版");
  } catch (error) {
    elements.writingStatus.textContent = conciseError(error, "中译英修正失败，请重试");
    elements.writingStatus.className = "generate-status error";
    showToast(elements.writingStatus.textContent);
  } finally {
    state.writingSubmitting = false;
    if (state.writingPractice) renderWritingPractice(state.writingPractice);
  }
});
elements.reviewWordsToggle.addEventListener("click", () => {
  state.reviewWordsExpanded = !state.reviewWordsExpanded;
  updateReviewWordsVisibility();
});
elements.todayWordsToggle.addEventListener("click", () => {
  state.todayWordsExpanded = !state.todayWordsExpanded;
  updateTodayWordsVisibility();
});
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
    setLearningView("reading");
    state.reviewWordsExpanded = false;
    state.todayWordsExpanded = false;
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
    seekBy(-SEEK_SECONDS);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    seekBy(SEEK_SECONDS);
  }
});

elements.generateButton.addEventListener("click", async () => {
  if (state.article?.day !== state.latestDay) return;
  if (!(await saveTodayWords())) return;
  const extraInstruction = elements.generateInstruction.value.trim();
  state.generating = true;
  updateGenerateButton();
  elements.generateStatus.textContent = "正在生成文章和音频，这可能需要几分钟...";
  elements.generateStatus.className = "generate-status";
  try {
    const result = await request("/api/generate-next", {
      method: "POST",
      body: JSON.stringify({ extraInstruction }),
    });
    const audioStatus = result.warning
      ? conciseError({ message: result.warning }, "音频未生成")
      : `第 ${result.day} 天文章已生成，音频未生成`;
    const baseStatus = result.audioGenerated ? `第 ${result.day} 天已生成` : audioStatus;
    elements.generateStatus.textContent = result.generatorNotice
      ? `${baseStatus}\n${result.generatorNotice}`
      : baseStatus;
    elements.generateStatus.className = result.generatorNotice
      ? "generate-status warning"
      : "generate-status";
    showToast(
      result.generatorNotice
        ? `${result.mode}：第 ${result.day} 天已生成 · ${result.generatorNotice}`
        : `${result.mode}：第 ${result.day} 天已生成`
    );
    elements.generateInstruction.value = "";
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
    await Promise.all([
      registerSession(),
      loadDayOptions(),
      loadCurrentArticle(),
      loadReviewPlan(),
    ]);
  } catch (error) {
    elements.articleTitle.textContent = "无法读取文章";
    showToast(error.message);
  }
}

initialize();
window.setInterval(checkExternalChanges, SYNC_INTERVAL_MS);
window.setInterval(() => registerSession(true), HEARTBEAT_INTERVAL_MS);
window.addEventListener("pageshow", () => registerSession(true));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") registerSession(true);
});
window.addEventListener("pagehide", (event) => {
  if (!event.persisted) closeSession();
});
