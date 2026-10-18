const accountNames = ["Applicant", "Collaborator", "Reviewer"];
const savedReviewer = localStorage.getItem("phd-platform-reviewer");
const pageStorageKey = "phd-platform-page";
const pageKeys = ["dashboard", "advisors", "outreach", "programs", "documents", "settings"];
const advisorPageSize = 100;
const advisorAutoLoadThresholdPx = 260;
const advisorCacheStorageKey = "phd-platform-advisor-cache-v3";
const advisorOptionsCacheKey = "phd-platform-options-cache-v2";
const advisorCacheTtlMs = 10 * 60 * 1000;
let advisorSearchTimer = null;
let outreachSearchTimer = null;
let programSearchTimer = null;
let aiSettingsLoaded = false;
const defaultDocumentTypes = [
  { value: "CV", label: "CV", count: 0 },
  { value: "SOP", label: "SOP / Statement of Purpose", count: 0 },
  { value: "Research Statement", label: "Research Statement", count: 0 },
  { value: "Personal Statement", label: "Personal Statement", count: 0 },
  { value: "套磁信", label: "套磁信 / Cold Email", count: 0 },
  { value: "推荐信", label: "推荐信相关", count: 0 },
  { value: "Writing Sample", label: "Writing Sample", count: 0 },
  { value: "Diversity Statement", label: "Diversity Statement", count: 0 },
  { value: "成绩单", label: "成绩单 / Transcript", count: 0 },
  { value: "语言成绩", label: "语言成绩 / TOEFL/IELTS", count: 0 },
  { value: "GRE", label: "GRE", count: 0 },
  { value: "作品集/补充材料", label: "作品集 / 补充材料", count: 0 },
  { value: "其他", label: "其他", count: 0 }
];
const outreachStatuses = ["待联系", "已发送", "已回复"];
const outreachResponseStatuses = ["待回复", "积极", "中性", "拒绝"];
const outreachStages = ["跟进中", "已面试", "已申请"];
const programStatuses = ["候选", "准备中", "已申请", "已提交", "已拒绝", "已录取", "不申请"];
const programPriorities = ["高", "中", "低"];
const advisorInterestOptions = ["待判断", "高兴趣", "有兴趣", "不感兴趣"];
const advisorQueryStatusOptions = ["待请求", "请求查询", "已查询"];
const legacyAdvisorInterestMap = {
  "很有兴趣": "高兴趣",
  "高": "高兴趣",
  "一般": "有兴趣",
  "中": "有兴趣",
  "低": "不感兴趣",
  "不保留": "不感兴趣",
  "排除": "不感兴趣",
  "未看": ""
};
const legacyAdvisorQueryStatusMap = {
  "需查询": "请求查询"
};

const state = {
  authenticated: false,
  sessionUser: "",
  page: initialPage(),
  reviewer: accountNames.includes(savedReviewer) ? savedReviewer : "Collaborator",
  options: null,
  advisors: [],
  advisorTotal: 0,
  advisorHasMore: false,
  advisorLoading: false,
  advisorLoadingMore: false,
  advisorListQueryKey: "",
  advisorListRequestId: 0,
  advisorListScrollTop: 0,
  advisorDetailLoadingId: "",
  advisorDetailRequestId: 0,
  advisorDetailError: "",
  selectedAdvisor: null,
  documents: [],
  documentTypes: defaultDocumentTypes,
  selectedDocType: "CV",
  selectedDocument: null,
  uploadOpen: false,
  pendingUploadFile: null,
  outreach: [],
  outreachFilters: createEmptyOutreachFilters(),
  outreachFilterCounts: { advisorStages: [], tiers: [], categories: [], statuses: [], responses: [], stages: [] },
  selectedOutreach: null,
  focusOutreachAdvisorId: "",
  programs: [],
  programFilters: createEmptyProgramFilters(),
  selectedProgram: null,
  programFormOpen: false,
  aiSettings: { enabled: false, available: false, hasApiKey: false },
  aiConversations: [],
  selectedAiConversation: null,
  aiPanelOpen: false,
  aiBusy: false,
  aiSending: false,
  pendingAiMessage: null,
  aiTyping: null,
  reviewSaveQueue: Promise.resolve(),
  outreachSaveQueue: Promise.resolve(),
  dashboardSummary: null,
  dashboardView: "overview",
  dashboardProfileScope: "all",
  dashboardHeatmapRows: "category",
  dashboardHeatmapCols: "stage",
  dashboardHeatmapFilters: createEmptyDashboardHeatmapFilters(),
  filters: createEmptyFilters(),
  collapsedFilters: {
    stage: false,
    tier: false,
    category: true,
    interest: true,
    queryStatus: true
  },
  collapsedOutreachFilters: {
    advisorStage: false,
    tier: false,
    category: true,
    status: false,
    response: false,
    stage: true
  }
};

function resetAiState(closePanel = true) {
  cancelAiTyping();
  if (closePanel) state.aiPanelOpen = false;
  state.selectedAiConversation = null;
  state.aiBusy = false;
  state.aiSending = false;
  state.pendingAiMessage = null;
}

function currentAiAdvisorId() {
  if (state.page === "outreach") return state.selectedOutreach?.advisorId || "";
  return state.selectedAdvisor?.id || "";
}

function isHiddenAiMessage(message) {
  return message?.role === "user"
    && String(message.content || "").trim() === "请先给出半分钟导师匹配简评。";
}

function cancelAiTyping() {
  if (state.aiTyping?.timer) {
    window.clearInterval(state.aiTyping.timer);
  }
  state.aiTyping = null;
}

const topPages = [
  ["dashboard", "总览"],
  ["advisors", "导师筛选"],
  ["outreach", "套磁跟踪"],
  ["programs", "申请跟踪"],
  ["documents", "文书管理"],
  ["settings", "系统设置"]
];

const reviewerLabels = {
  Applicant: "Applicant",
  Collaborator: "Collaborator",
  Reviewer: "Reviewer"
};

function createEmptyFilters() {
  return {
    search: "",
    stage: [],
    tier: [],
    category: [],
    interest: [],
    queryStatus: [],
    outreach: []
  };
}

function createEmptyDashboardHeatmapFilters() {
  return {
    category: [],
    stage: [],
    tier: [],
    outreachStatus: [],
    interest: []
  };
}

function createEmptyOutreachFilters() {
  return {
    search: "",
    advisorStage: [],
    tier: [],
    category: [],
    status: [],
    response: [],
    stage: []
  };
}

function createEmptyProgramFilters() {
  return {
    search: "",
    status: [],
    priority: []
  };
}

function pageFromHash() {
  return window.location.hash.replace(/^#/, "").trim();
}

function initialPage() {
  const hashPage = pageFromHash();
  if (pageKeys.includes(hashPage)) return hashPage;
  const savedPage = localStorage.getItem(pageStorageKey);
  if (pageKeys.includes(savedPage)) return savedPage;
  return "dashboard";
}

function hasActiveOutreachFilters() {
  return Boolean(
    state.outreachFilters.search
    || ["advisorStage", "tier", "category", "status", "response", "stage"].some(key => selectedFilterValues(state.outreachFilters, key).length)
  );
}

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeMarkdownUrl(value) {
  const url = String(value || "").trim();
  try {
    const parsed = new URL(url);
    if (["http:", "https:", "mailto:"].includes(parsed.protocol)) return parsed.href;
  } catch (_error) {
    return "";
  }
  return "";
}

function normalizeLinkUrlKey(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    parsed.hash = "";
    if ((parsed.protocol === "http:" && parsed.port === "80") || (parsed.protocol === "https:" && parsed.port === "443")) {
      parsed.port = "";
    }
    parsed.hostname = parsed.hostname.toLowerCase();
    parsed.pathname = parsed.pathname.replace(/\/+$/, "") || "/";
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}${parsed.search}`;
  } catch (_error) {
    return raw.replace(/#.*$/, "").replace(/\/+$/, "").toLowerCase();
  }
}

function isHomepageLink(link) {
  const label = String(link?.label || "").trim().toLowerCase();
  return label.includes("主页")
    || label.includes("homepage")
    || label.includes("personal website")
    || label.includes("personal site");
}

function orderedAdvisorLinks(links = []) {
  const groupedByUrl = new Map();
  (links || []).forEach(link => {
    const url = String(link?.url || "").trim();
    if (!url) return;
    const key = normalizeLinkUrlKey(url);
    if (!key) return;
    const existing = groupedByUrl.get(key) || { homepage: null, other: null };
    if (isHomepageLink(link) && !existing.homepage) {
      existing.homepage = { ...link, url };
    } else if (!isHomepageLink(link) && !existing.other) {
      existing.other = { ...link, url };
    }
    groupedByUrl.set(key, existing);
  });
  const homepageLinks = [];
  const otherLinks = [];
  groupedByUrl.forEach(entry => {
    if (entry.homepage) {
      homepageLinks.push(entry.homepage);
    } else if (entry.other) {
      otherLinks.push(entry.other);
    }
  });
  const renamedHomepages = homepageLinks.map((link, index) => ({
    ...link,
    label: homepageLinks.length > 1 ? `主页${index + 1}` : "主页"
  }));
  return [...renamedHomepages, ...otherLinks];
}

function renderAdvisorLinks(links = []) {
  return orderedAdvisorLinks(links)
    .map(link => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label || link.url)}</a>`)
    .join("");
}

function markdownInline(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g, (_match, label, url) => {
    const safeUrl = safeMarkdownUrl(url.replaceAll("&amp;", "&"));
    if (!safeUrl) return escapeHtml(label);
    return `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  return html;
}

function splitMarkdownTableRow(line) {
  let value = String(line || "").trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map(cell => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = splitMarkdownTableRow(line);
  return cells.length >= 2 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
}

function isMarkdownTableStart(lines, index) {
  return index + 1 < lines.length
    && String(lines[index] || "").includes("|")
    && isMarkdownTableSeparator(lines[index + 1]);
}

function isMarkdownBlockStart(lines, index) {
  const line = lines[index] || "";
  return /^#{1,4}\s+/.test(line)
    || /^-{3,}\s*$/.test(line.trim())
    || /^[-*]\s+/.test(line)
    || /^\d+\.\s+/.test(line)
    || /^```/.test(line.trim())
    || isMarkdownTableStart(lines, index);
}

function renderMarkdownTable(lines, startIndex) {
  const headers = splitMarkdownTableRow(lines[startIndex]);
  let index = startIndex + 2;
  const rows = [];
  while (index < lines.length && String(lines[index] || "").includes("|") && lines[index].trim()) {
    rows.push(splitMarkdownTableRow(lines[index]));
    index += 1;
  }
  const headerHtml = headers.map(cell => `<th>${markdownInline(cell)}</th>`).join("");
  const bodyHtml = rows.map(row => {
    const cells = headers.map((_header, cellIndex) => `<td>${markdownInline(row[cellIndex] || "")}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  return {
    html: `<div class="markdown-table-wrap"><table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`,
    nextIndex: index
  };
}

function markdownToHtml(value) {
  const lines = String(value || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (/^```/.test(line.trim())) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }
    if (isMarkdownTableStart(lines, index)) {
      const table = renderMarkdownTable(lines, index);
      blocks.push(table.html);
      index = table.nextIndex;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 5);
      blocks.push(`<h${level}>${markdownInline(heading[2].trim())}</h${level}>`);
      index += 1;
      continue;
    }
    if (/^-{3,}\s*$/.test(line.trim())) {
      blocks.push("<hr>");
      index += 1;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(`<li>${markdownInline(lines[index].replace(/^[-*]\s+/, ""))}</li>`);
        index += 1;
      }
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(`<li>${markdownInline(lines[index].replace(/^\d+\.\s+/, ""))}</li>`);
        index += 1;
      }
      blocks.push(`<ol>${items.join("")}</ol>`);
      continue;
    }
    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !isMarkdownBlockStart(lines, index)) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${paragraph.map(markdownInline).join("<br>")}</p>`);
  }
  return blocks.join("");
}

async function api(path, options = {}) {
  const { headers = {}, ...rest } = options;
  const isFormData = rest.body instanceof FormData;
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: isFormData ? headers : { "Content-Type": "application/json", ...headers },
    ...rest
  });
  if (response.status === 401) {
    state.authenticated = false;
    state.sessionUser = "";
    renderLogin("登录已过期，请重新登录。");
    throw new Error("unauthorized");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload.message || payload.error || "";
    } catch {
      detail = "";
    }
    throw new Error(detail ? `${response.status} ${detail}` : `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function nowMs() {
  return Date.now();
}

function safeJsonParse(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function readAdvisorCache() {
  const cache = safeJsonParse(localStorage.getItem(advisorCacheStorageKey) || "", null);
  if (!cache || cache.version !== 3) return { version: 3, lists: {}, details: {} };
  return {
    version: 3,
    lists: cache.lists || {},
    details: cache.details || {}
  };
}

function writeAdvisorCache(cache) {
  try {
    const detailEntries = Object.entries(cache.details || {})
      .sort((a, b) => Number(b[1]?.timestamp || 0) - Number(a[1]?.timestamp || 0))
      .slice(0, 60);
    const listEntries = Object.entries(cache.lists || {})
      .sort((a, b) => Number(b[1]?.timestamp || 0) - Number(a[1]?.timestamp || 0))
      .slice(0, 8);
    localStorage.setItem(advisorCacheStorageKey, JSON.stringify({
      version: 3,
      lists: Object.fromEntries(listEntries),
      details: Object.fromEntries(detailEntries)
    }));
  } catch {
    // localStorage quota is an optimization concern only; network data remains authoritative.
  }
}

function cacheFresh(entry) {
  return entry && nowMs() - Number(entry.timestamp || 0) < advisorCacheTtlMs;
}

function advisorFilterKey() {
  return JSON.stringify({
    search: state.filters.search || "",
    stage: selectedValues("stage"),
    tier: selectedValues("tier"),
    category: selectedValues("category"),
    interest: selectedValues("interest"),
    queryStatus: selectedValues("queryStatus"),
    outreach: selectedValues("outreach")
  });
}

function advisorListSummary(item) {
  return {
    id: item.id,
    num: item.num,
    rank: item.rank,
    name: item.name,
    institution: item.institution,
    institutionZh: item.institutionZh,
    firstInstitution: item.firstInstitution,
    firstInstitutionZh: item.firstInstitutionZh,
    city: item.city,
    state: item.state,
    primaryCategory: item.primaryCategory,
    schoolTier: item.schoolTier,
    schoolTierLabel: item.schoolTierLabel,
    stageKey: item.stageKey,
    stageLabel: item.stageLabel,
    contactCount: item.contactCount || 0,
    hasEmail: Boolean(item.hasEmail),
    primaryContact: item.primaryContact || "",
    primaryContactType: item.primaryContactType || "",
    reviewer: item.reviewer || "",
    interest: item.interest || "",
    queryStatus: item.queryStatus || "",
    reviewStatus: item.reviewStatus || "",
    note: item.note || "",
    updatedAt: item.updatedAt || "",
    outreachActive: Boolean(item.outreachActive),
    outreachStatus: item.outreachStatus || "",
    outreachResponseStatus: item.outreachResponseStatus || "",
    outreachStage: item.outreachStage || "",
    outreachNextAction: item.outreachNextAction || ""
  };
}

function cacheAdvisorList(queryKey, payload) {
  if (!queryKey || Number(payload.offset || 0) !== 0) return;
  const cache = readAdvisorCache();
  cache.lists[queryKey] = {
    timestamp: nowMs(),
    total: payload.total || 0,
    hasMore: Boolean(payload.hasMore),
    items: (payload.items || []).map(advisorListSummary)
  };
  writeAdvisorCache(cache);
}

function cachedAdvisorList(queryKey) {
  const entry = readAdvisorCache().lists[queryKey];
  return cacheFresh(entry) ? entry : null;
}

function cacheAdvisorDetail(advisorId, item) {
  if (!advisorId || !item) return;
  const cache = readAdvisorCache();
  cache.details[advisorId] = {
    timestamp: nowMs(),
    item
  };
  writeAdvisorCache(cache);
}

function cachedAdvisorDetail(advisorId) {
  const entry = readAdvisorCache().details[advisorId];
  return cacheFresh(entry) ? entry.item : null;
}

function mergeAdvisorCollaborativeState(base, latest) {
  if (!base || !latest) return base || latest;
  return {
    ...base,
    reviewer: latest.reviewer || "",
    interest: latest.interest || "",
    queryStatus: latest.queryStatus || latest.reviewStatus || "",
    reviewStatus: latest.reviewStatus || latest.queryStatus || "",
    note: latest.note || "",
    updatedAt: latest.updatedAt || "",
    outreachActive: Boolean(latest.outreachActive),
    outreachStatus: latest.outreachStatus || "",
    outreachResponseStatus: latest.outreachResponseStatus || "",
    outreachStage: latest.outreachStage || "",
    outreachNextAction: latest.outreachNextAction || "",
    contactCount: latest.contactCount ?? base.contactCount ?? 0,
    hasEmail: latest.hasEmail ?? base.hasEmail ?? false,
    primaryContact: latest.primaryContact || base.primaryContact || "",
    primaryContactType: latest.primaryContactType || base.primaryContactType || ""
  };
}

function buildAdvisorQuery({ limit = advisorPageSize, offset = 0 } = {}) {
  const params = new URLSearchParams({
    view: "list",
    limit: String(limit),
    offset: String(offset)
  });
  Object.entries(state.filters).forEach(([key]) => {
    if (key === "search") {
      if (state.filters.search) params.set(key, state.filters.search);
      return;
    }
    selectedValues(key).forEach(item => params.append(key, item));
  });
  return params.toString();
}

function cachedAdvisorOptions() {
  const entry = safeJsonParse(localStorage.getItem(advisorOptionsCacheKey) || "", null);
  return cacheFresh(entry) ? entry.options : null;
}

function cacheAdvisorOptions(options) {
  try {
    localStorage.setItem(advisorOptionsCacheKey, JSON.stringify({ timestamp: nowMs(), options }));
  } catch {
    // Options cache is only a startup optimization.
  }
}

async function ensureAdvisorOptions() {
  if (!state.options) {
    const cached = cachedAdvisorOptions();
    if (cached) {
      state.options = cached;
      renderSidebar();
    }
  }
  try {
    const latest = await api("/api/options");
    state.options = latest;
    cacheAdvisorOptions(latest);
    if (state.page === "advisors" || state.page === "outreach") renderSidebar();
  } catch (error) {
    if (!state.options) throw error;
  }
}

async function refreshAdvisorOptions() {
  try {
    const latest = await api("/api/options");
    state.options = latest;
    cacheAdvisorOptions(latest);
    if (state.page === "advisors" || state.page === "outreach") renderSidebar();
  } catch {
    // Sidebar counts are a convenience; review saves should not fail because counts refresh failed.
  }
}

async function loadAiSettings() {
  if (!state.authenticated) return;
  try {
    state.aiSettings = await api("/api/ai/settings");
    aiSettingsLoaded = true;
  } catch {
    state.aiSettings = { enabled: false, available: false, hasApiKey: false };
    aiSettingsLoaded = true;
  }
}

function setPage(page, options = {}) {
  const nextPage = pageKeys.includes(page) ? page : "dashboard";
  if (!state.authenticated) {
    state.page = nextPage;
    localStorage.setItem(pageStorageKey, state.page);
    renderLogin();
    return;
  }
  state.page = nextPage;
  localStorage.setItem(pageStorageKey, state.page);
  if (options.updateUrl !== false && window.location.hash !== `#${state.page}`) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${state.page}`);
  }
  state.selectedAdvisor = null;
  resetAiState();
  render();
}

function applyAdvisorDashboardPreset(preset) {
  if (!preset) return;
  state.filters = createEmptyFilters();
  state.advisorListScrollTop = 0;
  state.advisorListQueryKey = "";
  state.advisors = [];
  state.advisorTotal = 0;
  state.advisorHasMore = false;
  state.selectedAdvisor = null;
  if (preset === "interested") {
    state.filters.interest = ["高兴趣", "有兴趣"];
  }
}

function setCurrentPage(page, options = {}) {
  state.page = pageKeys.includes(page) ? page : "dashboard";
  localStorage.setItem(pageStorageKey, state.page);
  if (options.updateUrl !== false && window.location.hash !== `#${state.page}`) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${state.page}`);
  }
}

function renderMainLoading(message = "正在进入协作平台...") {
  $("main").innerHTML = `
    <div class="panel">
      <div class="panel-body">
        <div class="empty">${escapeHtml(message)}</div>
      </div>
    </div>
  `;
}

function renderTopNav() {
  if (!state.authenticated) {
    $("topnav").innerHTML = "";
    return;
  }
  $("topnav").innerHTML = topPages.map(([key, label]) => (
    `<button class="${state.page === key ? "active" : ""}" data-page="${key}">${escapeHtml(label)}</button>`
  )).join("");
  $("topnav").querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => setPage(button.dataset.page));
  });
  $("currentUser").textContent = reviewerLabels[state.reviewer] || state.sessionUser || "已登录";
  $("logoutBtn").addEventListener("click", logout);
}

function renderSidebar() {
  if (!state.authenticated) {
    $("sidebar").innerHTML = "";
    return;
  }
  if (state.page === "dashboard") {
    $("sidebar").innerHTML = `
      <div class="side-title">总览</div>
      <div class="side-nav dashboard-side-nav">
        <button class="${state.dashboardView === "overview" ? "active" : ""}" data-dashboard-view="overview">导师画像</button>
        <button class="${state.dashboardView === "heatmap" ? "active" : ""}" data-dashboard-view="heatmap">导师热力图</button>
      </div>
    `;
    $("sidebar").querySelectorAll("[data-dashboard-view]").forEach(button => {
      button.addEventListener("click", () => {
        state.dashboardView = button.dataset.dashboardView === "heatmap" ? "heatmap" : "overview";
        renderSidebar();
        renderDashboard();
      });
    });
    return;
  }
  if (state.page === "advisors") return renderAdvisorSidebar();
  if (state.page === "documents") return renderDocumentSidebar();
  if (state.page === "outreach") return renderOutreachSidebar();
  if (state.page === "programs") return renderProgramSidebar();
  const navMap = {
    settings: ["AI API 设置"]
  };
  $("sidebar").innerHTML = `
    <div class="side-title">${escapeHtml(topPages.find(([key]) => key === state.page)?.[1] || "")}</div>
    <div class="side-nav">
      ${(navMap[state.page] || []).map((item, index) => `<button class="${index === 0 ? "active" : ""}">${escapeHtml(item)}</button>`).join("")}
    </div>
  `;
}

function selectedValues(key) {
  const value = state.filters[key];
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

function selectedFilterValues(filters, key) {
  const value = filters[key];
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

function staticFilterItems(values) {
  return values.map(value => ({ value, label: value }));
}

function noteSavedLabel(value) {
  if (!value) return "";
  return `已保存于 ${formatTimestamp(value)}`;
}

function setSaveState(target, status, timestamp = new Date()) {
  const element = typeof target === "string" ? $(target) : target;
  if (!element) return;
  element.classList.remove("dirty", "saving", "saved", "error");
  if (status === "dirty") {
    element.textContent = "有未保存的修改";
    element.classList.add("dirty");
  } else if (status === "saving") {
    element.textContent = "保存中...";
    element.classList.add("saving");
  } else if (status === "saved") {
    element.textContent = noteSavedLabel(timestamp) || "已保存";
    element.classList.add("saved");
  } else if (status === "error") {
    element.textContent = "保存失败，请重试";
    element.classList.add("error");
  } else {
    element.textContent = "";
  }
}

function bindDirtySaveState({ fieldIds, stateId, savedAt = "" }) {
  const fields = fieldIds.map(id => $(id)).filter(Boolean);
  const stateElement = $(stateId);
  const baseline = new Map(fields.map(field => [field.id, field.value || ""]));
  if (stateElement && savedAt) setSaveState(stateElement, "saved", savedAt);
  const hasChanges = () => fields.some(field => (field.value || "") !== baseline.get(field.id));
  const update = () => {
    if (hasChanges()) {
      setSaveState(stateElement, "dirty");
    } else if (savedAt) {
      setSaveState(stateElement, "saved", savedAt);
    } else {
      setSaveState(stateElement, "");
    }
  };
  fields.forEach(field => field.addEventListener("input", update));
  return {
    markSaving() {
      setSaveState(stateElement, "saving");
    },
    markSaved(timestamp = new Date(), savedValues = null) {
      fields.forEach(field => {
        const value = savedValues && Object.prototype.hasOwnProperty.call(savedValues, field.id)
          ? savedValues[field.id]
          : field.value;
        baseline.set(field.id, value || "");
      });
      savedAt = timestamp;
      update();
    },
    markError() {
      setSaveState(stateElement, "error");
    }
  };
}

function fitAutoGrowTextarea(textarea) {
  if (!textarea) return;
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

function bindAutoGrowTextareas(root = document) {
  root.querySelectorAll("textarea[data-autogrow='true']").forEach(textarea => {
    textarea.classList.add("auto-grow-textarea");
    fitAutoGrowTextarea(textarea);
    requestAnimationFrame(() => fitAutoGrowTextarea(textarea));
    textarea.addEventListener("input", () => fitAutoGrowTextarea(textarea));
  });
}

function staticFilterItemsWithCounts(values, countedItems = []) {
  const countByValue = new Map((countedItems || []).map(item => [item.value, item.count || 0]));
  return values.map(value => ({ value, label: value, count: countByValue.get(value) || 0 }));
}

function normalizeAdvisorInterest(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (advisorInterestOptions.includes(text)) return text;
  if (Object.prototype.hasOwnProperty.call(legacyAdvisorInterestMap, text)) {
    return legacyAdvisorInterestMap[text];
  }
  return text;
}

function normalizeAdvisorQueryStatus(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (advisorQueryStatusOptions.includes(text)) return text;
  if (Object.prototype.hasOwnProperty.call(legacyAdvisorQueryStatusMap, text)) {
    return legacyAdvisorQueryStatusMap[text];
  }
  return text;
}

const researchPoolLabels = {
  "Core evaluation": "P1 核心 LLM Evaluation/Benchmarking",
  "Agent/persona": "P2 相邻 Agent/Persona",
  "NLP/LLM-adjacent": "P2 相邻 NLP/LLM",
  "HCI/social": "P2 相邻 HCI/Social",
  "Recommender/user": "P3 相关 Recommender/User",
  "Education/HCI": "P3 相关 Education/HCI",
  "AI/ML adjacent": "P3 相关 AI/ML",
  "Trustworthy/robust": "P3 相关 Trustworthy/Robust",
  "Software/systems adjacent": "P3 相关 Software/Systems",
  "CS faculty fallback": "P3 相关 CS Faculty"
};

const researchPoolOrder = Object.fromEntries(Object.keys(researchPoolLabels).map((value, index) => [value, index]));

const advisorStageLabels = {
  ap: "AP / 早期",
  associate: "Associate / 中期",
  full: "Full / 资深",
  star: "Distinguished / 杰出",
  faculty_unknown: "Faculty / 职级未知",
  nonfaculty: "Non-faculty / 路径不清",
  unknown: "Unknown / 待核实"
};

const schoolTierLabels = {
  tier1: "第一梯队",
  tier2: "第二梯队",
  tier3: "第三梯队"
};

const legacyAdvisorStageLabels = {
  "AP / 早期": advisorStageLabels.ap,
  "Associate / 中期": advisorStageLabels.associate,
  "Associate": advisorStageLabels.associate,
  "中期": advisorStageLabels.associate,
  "Full / PI": advisorStageLabels.full,
  "Full / 资深": advisorStageLabels.full,
  "Full": advisorStageLabels.full,
  "资深": advisorStageLabels.full,
  "大 PI / 高冲刺": advisorStageLabels.star,
  "Star / senior high-competition": advisorStageLabels.star,
  "Distinguished / 杰出": advisorStageLabels.star,
  "Faculty / 职级待定": advisorStageLabels.faculty_unknown,
  "Faculty / 职级未知": advisorStageLabels.faculty_unknown,
  "faculty 但阶段未知": advisorStageLabels.faculty_unknown,
  "非 faculty / 路径不清": advisorStageLabels.nonfaculty,
  "路径不清": advisorStageLabels.nonfaculty,
  "非独立导师": advisorStageLabels.nonfaculty,
  "未知": advisorStageLabels.unknown,
  "Unknown / 待核实": advisorStageLabels.unknown
};

function displayAdvisorStageLabel(value) {
  const text = String(value || "").trim();
  if (!text) return advisorStageLabels.unknown;
  return advisorStageLabels[text] || legacyAdvisorStageLabels[text] || text;
}

const sortOrders = {
  advisorStage: {
    ap: 0,
    associate: 1,
    full: 2,
    star: 3,
    faculty_unknown: 4,
    nonfaculty: 5,
    unknown: 6
  },
  stage: {
    ap: 0,
    associate: 1,
    full: 2,
    star: 3,
    faculty_unknown: 4,
    nonfaculty: 5,
    unknown: 6,
    "AP / 早期": 7,
    "Associate / 中期": 8,
    "中期": 8,
    "Full / 资深": 9,
    "Full / PI": 9,
    "资深": 9,
    "Distinguished / 杰出": 10,
    "大 PI / 高冲刺": 10,
    "路径不清": 10,
    "非独立导师": 11,
    "Faculty / 职级未知": 12,
    "Faculty / 职级待定": 12,
    "Unknown / 待核实": 13,
    "未知": 13,
    "跟进中": 20,
    "已面试": 21,
    "已申请": 22
  },
  tier: {
    tier1: 0,
    tier2: 1,
    tier3: 2
  },
  category: researchPoolOrder,
  interest: {
    "待判断": 0,
    "高兴趣": 1,
    "很有兴趣": 1,
    "高": 1,
    "有兴趣": 2,
    "一般": 2,
    "中": 2,
    "不感兴趣": 3,
    "低": 3
  },
  queryStatus: {
    "待请求": 0,
    "请求查询": 1,
    "需查询": 1,
    "已查询": 2
  },
  outreach: {
    "已加入": 0,
    "未加入": 1
  },
  status: {
    "待联系": 0,
    "已发送": 1,
    "已回复": 2
  },
  response: {
    "待回复": 0,
    "积极": 1,
    "中性": 2,
    "拒绝": 3
  },
  priority: {
    "高": 0,
    "中": 1,
    "低": 2
  },
};

const dashboardHeatmapDimensions = [
  { key: "category", label: "研究池" },
  { key: "stage", label: "导师阶段" },
  { key: "tier", label: "学校梯队" },
  { key: "outreachStatus", label: "套磁状态" },
  { key: "interest", label: "兴趣标记" }
];

const dashboardHeatmapFilterGroups = [
  { key: "category", label: "研究池" },
  { key: "stage", label: "导师阶段" },
  { key: "tier", label: "学校梯队" },
  { key: "outreachStatus", label: "套磁状态" },
  { key: "interest", label: "兴趣标记" }
];

const dashboardHeatmapOrders = {
  category: researchPoolOrder,
  stage: sortOrders.stage,
  tier: sortOrders.tier,
  outreachStatus: {
    "待联系": 0,
    "已发送": 1,
    "已回复": 2,
    "未加入": 3
  },
  interest: sortOrders.interest
};

function displayFilterLabel(key, value) {
  if (key === "category") {
    if (!value) return "未知";
    return researchPoolLabels[value] || `P3 相关 ${value}`;
  }
  if (key === "stage" || key === "advisorStage") {
    return displayAdvisorStageLabel(value);
  }
  if (key === "tier") return schoolTierLabels[value] || value || "未知";
  if (key === "interest") return normalizeAdvisorInterest(value) || "未设置";
  if (key === "queryStatus") return normalizeAdvisorQueryStatus(value) || "未设置";
  return value || "未知";
}

function orderedFilterItems(key, items) {
  const rows = [...(items || [])];
  const order = sortOrders[key];
  if (order) {
    rows.sort((a, b) => {
      const aValue = a.value || "";
      const bValue = b.value || "";
      const orderDiff = (order[aValue] ?? 999) - (order[bValue] ?? 999);
      if (orderDiff !== 0) return orderDiff;
      return String(a.label || aValue).localeCompare(String(b.label || bValue));
    });
  }
  return rows;
}

function coverageRows(key, rows) {
  return orderedFilterItems(key, rows).map(row => ({
    label: displayFilterLabel(key, row.label || row.value),
    count: row.count
  }));
}

function renderDashboardBars(rows, emptyText) {
  const maxCount = Math.max(...rows.map(row => Number(row.count) || 0), 1);
  if (!rows.length) return `<div class="empty compact-empty">${escapeHtml(emptyText)}</div>`;
  return rows.map(row => {
    const count = Number(row.count) || 0;
    const width = Math.max(4, Math.round((count / maxCount) * 100));
    const label = row.label || "未知";
    return `
      <div class="bar-row">
        <div class="bar-label">${escapeHtml(label)}</div>
        <div class="bar-track" aria-label="${escapeHtml(`${label}：${count} 人`)}">
          <div class="bar-fill" style="width:${width}%"></div>
        </div>
        <div class="bar-value">${escapeHtml(count)}</div>
      </div>
    `;
  }).join("");
}

function dashboardProfileScopes(summary) {
  return [
    { key: "all", label: "导师池", count: summary.total || 0 },
    { key: "interested", label: "兴趣", count: summary.interested || 0 },
    { key: "outreach", label: "套磁", count: summary.outreachActive || 0 },
    { key: "replied", label: "回复", count: summary.outreachReplied || 0 },
    { key: "interviews", label: "面试", count: summary.outreachInterviews || 0 },
    { key: "positive", label: "积极", count: summary.outreachPositive || 0 },
    { key: "submitted", label: "申请", count: summary.programsSubmitted || 0, unsupported: true },
    { key: "accepted", label: "录取", count: summary.programsAccepted || 0, unsupported: true }
  ];
}

function dashboardProfileScopeMeta(summary, scope) {
  return dashboardProfileScopes(summary).find(item => item.key === scope) || dashboardProfileScopes(summary)[0];
}

function dashboardItemHasPositiveInterest(item) {
  return ["高兴趣", "有兴趣"].includes(normalizeAdvisorInterest(item.interest));
}

function dashboardItemIsActiveOutreach(item) {
  const activeValue = item?.outreachActive;
  return Number(item?.outreachCount || 0) > 0
    || activeValue === true
    || activeValue === 1
    || activeValue === "1";
}

function dashboardItemHasOutreach(item) {
  return dashboardItemIsActiveOutreach(item);
}

function dashboardItemHasReply(item) {
  if (!dashboardItemIsActiveOutreach(item)) return false;
  const response = normalizeOutreachResponse(item.outreachResponseStatus || "");
  const status = normalizeOutreachStatus(item.outreachStatus || "");
  const stage = normalizeOutreachStage(item.outreachStage || "");
  return ["积极", "中性", "拒绝"].includes(response)
    || status === "已回复"
    || ["已面试", "已申请"].includes(stage);
}

function dashboardItemHasInterview(item) {
  if (!dashboardItemIsActiveOutreach(item)) return false;
  return normalizeOutreachStage(item.outreachStage || "") === "已面试"
    || ["已面试", "面试中"].includes(item.outreachStatus || "");
}

function dashboardItemHasPositiveReply(item) {
  if (!dashboardItemIsActiveOutreach(item)) return false;
  return normalizeOutreachResponse(item.outreachResponseStatus || "") === "积极";
}

function dashboardProfileItems(summary, scope) {
  const items = summary.advisorHeatmapItems || [];
  if (scope === "interested") return items.filter(dashboardItemHasPositiveInterest);
  if (scope === "outreach") return items.filter(dashboardItemHasOutreach);
  if (scope === "replied") return items.filter(dashboardItemHasReply);
  if (scope === "interviews") return items.filter(dashboardItemHasInterview);
  if (scope === "positive") return items.filter(dashboardItemHasPositiveReply);
  if (scope === "submitted" || scope === "accepted") return [];
  return items;
}

function dashboardProfileRows(items, key) {
  return dashboardHeatmapOptionRows(items, key).map(row => ({
    label: row.label || "未知",
    count: row.count
  }));
}

function dashboardProfileEmptyText(scopeMeta) {
  if (scopeMeta.unsupported) return "申请跟踪暂未关联到具体导师，暂不能生成导师画像。";
  return `当前“${scopeMeta.label}”范围没有导师画像数据。`;
}

function renderDashboardMetricCards(summary) {
  const scopes = dashboardProfileScopes(summary);
  if (!scopes.some(scope => scope.key === state.dashboardProfileScope)) state.dashboardProfileScope = "all";
  return scopes.map(scope => `
    <button class="metric-card metric-button ${state.dashboardProfileScope === scope.key ? "active" : ""}" type="button" data-dashboard-profile-scope="${escapeHtml(scope.key)}" aria-pressed="${state.dashboardProfileScope === scope.key ? "true" : "false"}">
      <b>${escapeHtml(scope.count)}</b>
      <span>${escapeHtml(scope.label)}</span>
    </button>
  `).join("");
}

function dashboardHeatmapDimensionLabel(key) {
  return dashboardHeatmapDimensions.find(item => item.key === key)?.label || key;
}

function dashboardHeatmapCellValue(item, key) {
  if (key === "category") {
    const value = item.category || "";
    return { value, label: displayFilterLabel("category", value) };
  }
  if (key === "stage") {
    const value = item.stage || "";
    return { value, label: displayFilterLabel("stage", value || item.stageLabel) };
  }
  if (key === "tier") {
    const value = item.tier || "";
    return { value, label: item.tierLabel || displayFilterLabel("tier", value) };
  }
  if (key === "outreachStatus") {
    const value = item.outreachStatus || "未加入";
    return { value, label: value };
  }
  if (key === "interest") {
    const value = normalizeAdvisorInterest(item.interest) || "待判断";
    return { value, label: value };
  }
  return { value: "", label: "未知" };
}

function dashboardHeatmapSeedValues(key) {
  if (key === "category") return Object.keys(researchPoolLabels);
  if (key === "stage") return Object.keys(advisorStageLabels);
  if (key === "tier") return ["tier1", "tier2", "tier3"];
  if (key === "outreachStatus") return ["未加入", ...outreachStatuses];
  if (key === "interest") return advisorInterestOptions;
  return [];
}

function dashboardHeatmapOptionRows(items, key, { includeZero = false } = {}) {
  const rows = new Map();
  const counts = new Map();
  if (includeZero) {
    dashboardHeatmapSeedValues(key).forEach(value => {
      const option = dashboardHeatmapCellValue({ [key]: value }, key);
      rows.set(option.value, option);
      counts.set(option.value, 0);
    });
  }
  items.forEach(item => {
    const option = dashboardHeatmapCellValue(item, key);
    if (!option.value) return;
    if (!rows.has(option.value)) rows.set(option.value, option);
    counts.set(option.value, (counts.get(option.value) || 0) + 1);
  });
  const order = dashboardHeatmapOrders[key] || {};
  return [...rows.values()].sort((a, b) => {
    const orderDiff = (order[a.value] ?? 999) - (order[b.value] ?? 999);
    if (orderDiff !== 0) return orderDiff;
    return a.label.localeCompare(b.label);
  }).map(option => ({ ...option, count: counts.get(option.value) || 0 }));
}

function dashboardHeatmapOptions(items, key) {
  return dashboardHeatmapOptionRows(items, key);
}

function selectedDashboardHeatmapValues(key) {
  const filters = state.dashboardHeatmapFilters || createEmptyDashboardHeatmapFilters();
  const value = filters[key];
  return Array.isArray(value) ? value : [];
}

function filterDashboardHeatmapItems(items) {
  const filters = state.dashboardHeatmapFilters || createEmptyDashboardHeatmapFilters();
  return (items || []).filter(item => dashboardHeatmapFilterGroups.every(group => {
    const selected = Array.isArray(filters[group.key]) ? filters[group.key] : [];
    if (!selected.length) return true;
    return selected.includes(dashboardHeatmapCellValue(item, group.key).value);
  }));
}

function renderDashboardHeatmapFilterGroup(items, group) {
  const selected = selectedDashboardHeatmapValues(group.key);
  const selectedSet = new Set(selected);
  const options = dashboardHeatmapOptionRows(items, group.key, { includeZero: true });
  const optionButtons = options.map(option => `
    <button type="button" class="heatmap-filter-chip ${selectedSet.has(option.value) ? "active" : ""}" data-heatmap-filter-key="${escapeHtml(group.key)}" data-heatmap-filter-value="${escapeHtml(option.value)}" title="${escapeHtml(`${option.label}：${option.count} 人`)}">
      <span>${escapeHtml(option.label)}</span>
      <b>${escapeHtml(option.count)}</b>
    </button>
  `).join("");
  return `
    <div class="heatmap-filter-group">
      <div class="heatmap-filter-label">
        <span>${escapeHtml(group.label)}</span>
      </div>
      <div class="heatmap-filter-options">
        <button type="button" class="heatmap-filter-chip heatmap-filter-all-chip ${selected.length ? "" : "active"}" data-heatmap-filter-all="${escapeHtml(group.key)}">
          <span>全部</span>
        </button>
        <div class="heatmap-filter-choice-list">
          ${optionButtons}
        </div>
      </div>
    </div>
  `;
}

function hasDashboardHeatmapFilters() {
  const filters = state.dashboardHeatmapFilters || createEmptyDashboardHeatmapFilters();
  return dashboardHeatmapFilterGroups.some(group => (filters[group.key] || []).length);
}

function ensureDashboardHeatmapDimensions() {
  const keys = dashboardHeatmapDimensions.map(item => item.key);
  if (!keys.includes(state.dashboardHeatmapRows)) state.dashboardHeatmapRows = keys[0];
  if (!keys.includes(state.dashboardHeatmapCols)) state.dashboardHeatmapCols = keys.find(key => key !== state.dashboardHeatmapRows) || keys[0];
  if (state.dashboardHeatmapRows === state.dashboardHeatmapCols) {
    state.dashboardHeatmapCols = keys.find(key => key !== state.dashboardHeatmapRows) || state.dashboardHeatmapCols;
  }
}

function renderDashboardHeatmap(items) {
  ensureDashboardHeatmapDimensions();
  const filteredItems = filterDashboardHeatmapItems(items);
  const rowKey = state.dashboardHeatmapRows;
  const colKey = state.dashboardHeatmapCols;
  const rowOptions = dashboardHeatmapOptions(filteredItems, rowKey);
  const colOptions = dashboardHeatmapOptions(filteredItems, colKey);
  const matrix = new Map();
  let maxOutreach = 0;
  filteredItems.forEach(item => {
    const row = dashboardHeatmapCellValue(item, rowKey);
    const col = dashboardHeatmapCellValue(item, colKey);
    if (!row.value || !col.value) return;
    const key = `${row.value}|||${col.value}`;
    const current = matrix.get(key) || { advisors: 0, outreach: 0 };
    current.advisors += 1;
    current.outreach += Number(item.outreachCount || 0);
    matrix.set(key, current);
    maxOutreach = Math.max(maxOutreach, current.outreach);
  });
  const rowSelectOptions = dashboardHeatmapDimensions.map(dim => (
    `<option value="${escapeHtml(dim.key)}" ${dim.key === rowKey ? "selected" : ""} ${dim.key === colKey ? "disabled" : ""}>${escapeHtml(dim.label)}</option>`
  )).join("");
  const colSelectOptions = dashboardHeatmapDimensions.map(dim => (
    `<option value="${escapeHtml(dim.key)}" ${dim.key === colKey ? "selected" : ""} ${dim.key === rowKey ? "disabled" : ""}>${escapeHtml(dim.label)}</option>`
  )).join("");
  const headerCells = colOptions.map(col => `<th>${escapeHtml(col.label)}</th>`).join("");
  const filterBar = dashboardHeatmapFilterGroups.map(group => renderDashboardHeatmapFilterGroup(items, group)).join("");
  const hasRangeFilters = hasDashboardHeatmapFilters();
  const bodyRows = rowOptions.map(row => {
    const cells = colOptions.map(col => {
      const cell = matrix.get(`${row.value}|||${col.value}`) || { advisors: 0, outreach: 0 };
      const alpha = cell.outreach && maxOutreach ? 0.10 + (cell.outreach / maxOutreach) * 0.68 : 0;
      const style = cell.advisors ? `style="background: rgba(232, 84, 43, ${alpha.toFixed(3)})"` : "";
      const title = `${row.label} / ${col.label}：导师 ${cell.advisors}，套磁 ${cell.outreach}`;
      return `<td class="heatmap-value ${cell.advisors ? "" : "zero"}" ${style} title="${escapeHtml(title)}">${escapeHtml(cell.advisors)}</td>`;
    }).join("");
    return `<tr><th>${escapeHtml(row.label)}</th>${cells}</tr>`;
  }).join("");
  const heatmapBody = filteredItems.length && rowOptions.length && colOptions.length ? `
    <div class="heatmap-scroller">
      <table class="heatmap-table">
        <thead>
          <tr><th>${escapeHtml(dashboardHeatmapDimensionLabel(rowKey))} × ${escapeHtml(dashboardHeatmapDimensionLabel(colKey))}</th>${headerCells}</tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  ` : `
    <div class="heatmap-empty">
      <div class="empty compact-empty">当前筛选范围没有可交叉统计的导师。</div>
    </div>
  `;
  return `
    <div class="panel-title heatmap-panel-title">
      <span>导师热力图</span>
    </div>
    <div class="heatmap-config">
      <section class="heatmap-config-section heatmap-range-section" aria-label="热力图范围">
        <div class="heatmap-config-head">
          <span>热力图范围</span>
          <button type="button" ${hasRangeFilters ? "" : "disabled"} data-heatmap-filter-clear>清空范围</button>
        </div>
        <div class="heatmap-filter-panel">
          ${filterBar}
        </div>
      </section>
      <section class="heatmap-config-section heatmap-dimension-section" aria-label="热力图维度">
        <div class="heatmap-config-head">
          <span>热力图维度</span>
        </div>
        <label class="heatmap-dimension-field">
          <span>行维度</span>
          <select id="dashboardHeatmapRows" aria-label="行属性">${rowSelectOptions}</select>
        </label>
        <label class="heatmap-dimension-field">
          <span>列维度</span>
          <select id="dashboardHeatmapCols" aria-label="列属性">${colSelectOptions}</select>
        </label>
        <div class="heatmap-legend"><span>套磁数量</span><span class="heatmap-ramp" aria-hidden="true"></span></div>
      </section>
    </div>
    ${heatmapBody}
  `;
}

function optionGroup(label, key, items, valueKey = "value", labelKey = "label") {
  const selected = selectedValues(key);
  const selectedSet = new Set(selected);
  const collapsed = Boolean(state.collapsedFilters[key]);
  const rows = orderedFilterItems(key, items)
    .filter(item => item[valueKey] || item[labelKey])
    .map(item => {
      const value = item[valueKey] || "";
      const labelText = displayFilterLabel(key, item[labelKey] || value);
      const count = Object.prototype.hasOwnProperty.call(item, "count") ? item.count : "";
      return `
        <button type="button" class="filter-option ${selectedSet.has(value) ? "active" : ""}" data-filter-key="${escapeHtml(key)}" data-filter-value="${escapeHtml(value)}">
          <span>${escapeHtml(labelText)}</span>
          <b>${escapeHtml(count)}</b>
        </button>
      `;
    })
    .join("");
  return `
    <div class="side-section filter-section ${collapsed ? "collapsed" : "open"}">
      <button type="button" class="filter-head" data-filter-toggle="${escapeHtml(key)}" aria-expanded="${collapsed ? "false" : "true"}">
        <span><i aria-hidden="true"></i>${escapeHtml(label)}</span>
        <em>${selected.length ? `${selected.length} 项` : "全部"}</em>
      </button>
      <div class="filter-group" ${collapsed ? "hidden" : ""}>
        <button type="button" class="filter-option ${selected.length ? "" : "active"}" data-filter-all="${escapeHtml(key)}">
          <span>全部</span>
          <b></b>
        </button>
        ${rows}
      </div>
    </div>
  `;
}

function renderAdvisorSidebar() {
  const options = state.options || {};
  $("sidebar").innerHTML = `
    <div class="filter-sidebar-layout">
      <div class="filter-sidebar-scroll">
        <div class="side-title">导师筛选</div>
        <div class="side-section filter-search-section">
          <label>搜索</label>
          <input class="filter-search-input" id="advisorSearch" value="${escapeHtml(state.filters.search)}" placeholder="姓名、学校、方向">
        </div>
        ${optionGroup("研究池", "category", options.categories)}
        ${optionGroup("导师阶段", "stage", options.stages)}
        ${optionGroup("学校梯队", "tier", options.tiers)}
        ${optionGroup("套磁状态", "outreach", staticFilterItems(["已加入", "未加入"]))}
        ${optionGroup("兴趣标记", "interest", staticFilterItemsWithCounts(advisorInterestOptions, options.interests))}
        ${optionGroup("查询标记", "queryStatus", staticFilterItemsWithCounts(advisorQueryStatusOptions, options.queryStatuses))}
      </div>
      <div class="filter-sidebar-actions">
        <button class="sidebar-clear-button" id="clearFilters" type="button">清空筛选</button>
      </div>
    </div>
  `;
  $("advisorSearch").addEventListener("input", event => {
    state.filters.search = event.target.value;
    window.clearTimeout(advisorSearchTimer);
    advisorSearchTimer = window.setTimeout(() => loadAdvisors({ renderSidebarPanel: false }), 280);
  });
  $("sidebar").querySelectorAll("[data-filter-toggle]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.filterToggle;
      state.collapsedFilters[key] = !state.collapsedFilters[key];
      renderAdvisorSidebar();
    });
  });
  $("sidebar").querySelectorAll("[data-filter-all]").forEach(button => {
    button.addEventListener("click", () => {
      state.filters[button.dataset.filterAll] = [];
      loadAdvisors();
    });
  });
  $("sidebar").querySelectorAll("[data-filter-value]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.filterKey;
      const value = button.dataset.filterValue;
      const current = new Set(selectedValues(key));
      if (current.has(value)) {
        current.delete(value);
      } else {
        current.add(value);
      }
      state.filters[key] = Array.from(current);
      loadAdvisors();
    });
  });
  $("clearFilters").addEventListener("click", () => {
    state.filters = createEmptyFilters();
    loadAdvisors();
  });
}

function renderDocumentSidebar() {
  const types = state.documentTypes?.length ? state.documentTypes : defaultDocumentTypes;
  $("sidebar").innerHTML = `
    <div class="filter-sidebar-layout">
      <div class="filter-sidebar-scroll">
        <div class="side-title">文书管理</div>
        <div class="side-nav document-type-nav">
          ${types.map(item => `
            <button type="button" class="${state.selectedDocType === item.value ? "active" : ""}" data-doc-type="${escapeHtml(item.value)}">
              <span>${escapeHtml(item.label)}</span>
              <b>${escapeHtml(item.count || 0)}</b>
            </button>
          `).join("")}
        </div>
      </div>
      <div class="filter-sidebar-actions">
        <button class="sidebar-primary-button" id="openUpload" type="button">上传文书</button>
      </div>
    </div>
  `;
  $("sidebar").querySelectorAll("[data-doc-type]").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedDocType = button.dataset.docType;
      state.selectedDocument = null;
      state.uploadOpen = false;
      state.pendingUploadFile = null;
      renderDocuments();
    });
  });
  $("openUpload").addEventListener("click", () => {
    state.uploadOpen = true;
    state.pendingUploadFile = null;
    renderDocuments();
  });
}

function compactFilterButtons(label, key, items, filters, prefix) {
  const selected = selectedFilterValues(filters, key);
  const selectedSet = new Set(selected);
  const rows = orderedFilterItems(key, items.map(item => typeof item === "string" ? { value: item, label: item } : item));
  return `
    <div class="side-section filter-section open">
      <button type="button" class="filter-head" disabled>
        <span>${escapeHtml(label)}</span>
        <em>${selected.length ? `${selected.length} 项` : "全部"}</em>
      </button>
      <div class="filter-group">
        <button type="button" class="filter-option ${selected.length ? "" : "active"}" data-${prefix}-all="${escapeHtml(key)}">
          <span>全部</span><b></b>
        </button>
        ${rows.map(item => `
          <button type="button" class="filter-option ${selectedSet.has(item.value) ? "active" : ""}" data-${prefix}-filter="${escapeHtml(key)}" data-filter-value="${escapeHtml(item.value)}">
            <span>${escapeHtml(item.label || item.value)}</span>
            <b>${escapeHtml(item.count || "")}</b>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function outreachFilterGroup(label, key, items) {
  const selected = selectedFilterValues(state.outreachFilters, key);
  const selectedSet = new Set(selected);
  const collapsed = Boolean(state.collapsedOutreachFilters[key]);
  const rows = orderedFilterItems(key, items.map(item => typeof item === "string" ? { value: item, label: item } : item));
  return `
    <div class="side-section filter-section ${collapsed ? "collapsed" : "open"}">
      <button type="button" class="filter-head" data-outreach-toggle="${escapeHtml(key)}" aria-expanded="${collapsed ? "false" : "true"}">
        <span><i aria-hidden="true"></i>${escapeHtml(label)}</span>
        <em>${selected.length ? `${selected.length} 项` : "全部"}</em>
      </button>
      <div class="filter-group" ${collapsed ? "hidden" : ""}>
        <button type="button" class="filter-option ${selected.length ? "" : "active"}" data-outreach-all="${escapeHtml(key)}">
          <span>全部</span><b></b>
        </button>
        ${rows.map(item => `
          <button type="button" class="filter-option ${selectedSet.has(item.value) ? "active" : ""}" data-outreach-filter="${escapeHtml(key)}" data-filter-value="${escapeHtml(item.value)}">
            <span>${escapeHtml(displayFilterLabel(key, item.label || item.value))}</span>
            <b>${escapeHtml(item.count || "")}</b>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderOutreachSidebar() {
  const filters = state.outreachFilters;
  const counts = state.outreachFilterCounts || {};
  $("sidebar").innerHTML = `
    <div class="filter-sidebar-layout">
      <div class="filter-sidebar-scroll">
        <div class="side-title">套磁跟踪</div>
        <div class="side-section filter-search-section">
          <label>搜索导师</label>
          <input class="filter-search-input" id="outreachSearch" value="${escapeHtml(filters.search)}" placeholder="导师、学校、标签、备注">
        </div>
        ${outreachFilterGroup("导师阶段", "advisorStage", counts.advisorStages || [])}
        ${outreachFilterGroup("学校梯队", "tier", counts.tiers || [])}
        ${outreachFilterGroup("研究池", "category", counts.categories || [])}
        ${outreachFilterGroup("套磁状态", "status", outreachStatuses)}
        ${outreachFilterGroup("反馈状态", "response", outreachResponseStatuses)}
        ${outreachFilterGroup("跟进阶段", "stage", outreachStages)}
      </div>
      <div class="filter-sidebar-actions">
        <button class="sidebar-clear-button" id="clearOutreachFilters" type="button">清空筛选</button>
      </div>
    </div>
  `;
  $("outreachSearch").addEventListener("input", event => {
    state.outreachFilters.search = event.target.value;
    window.clearTimeout(outreachSearchTimer);
    outreachSearchTimer = window.setTimeout(() => loadOutreach({ renderSidebarPanel: false }), 280);
  });
  $("sidebar").querySelectorAll("[data-outreach-toggle]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.outreachToggle;
      state.collapsedOutreachFilters[key] = !state.collapsedOutreachFilters[key];
      renderOutreachSidebar();
    });
  });
  $("sidebar").querySelectorAll("[data-outreach-all]").forEach(button => {
    button.addEventListener("click", () => {
      state.outreachFilters[button.dataset.outreachAll] = [];
      loadOutreach();
    });
  });
  $("sidebar").querySelectorAll("[data-outreach-filter]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.outreachFilter;
      const value = button.dataset.filterValue;
      const current = new Set(selectedFilterValues(state.outreachFilters, key));
      if (current.has(value)) current.delete(value);
      else current.add(value);
      state.outreachFilters[key] = Array.from(current);
      loadOutreach();
    });
  });
  $("clearOutreachFilters").addEventListener("click", () => {
    state.outreachFilters = createEmptyOutreachFilters();
    loadOutreach();
  });
}

function outreachQuery() {
  const params = new URLSearchParams();
  if (state.outreachFilters.search) params.set("search", state.outreachFilters.search);
  ["advisorStage", "tier", "category", "status", "response", "stage"].forEach(key => {
    selectedFilterValues(state.outreachFilters, key).forEach(value => params.append(key, value));
  });
  return params.toString();
}

async function loadOutreach(options = {}) {
  const { renderSidebarPanel = true, allowFocusFilterReset = true } = options;
  const payload = await api(`/api/outreach?${outreachQuery()}`);
  let items = payload.items || [];
  const focusedAdvisorId = state.focusOutreachAdvisorId;
  if (
    allowFocusFilterReset
    && focusedAdvisorId
    && !items.some(item => item.advisorId === focusedAdvisorId)
    && hasActiveOutreachFilters()
  ) {
    state.outreachFilters = createEmptyOutreachFilters();
    return loadOutreach({ renderSidebarPanel, allowFocusFilterReset: false });
  }
  state.outreach = items;
  state.outreachFilterCounts = payload.filters || { advisorStages: [], tiers: [], categories: [], statuses: [], responses: [], stages: [] };
  if (focusedAdvisorId && state.outreach.some(item => item.advisorId === focusedAdvisorId)) {
    state.selectedOutreach = state.outreach.find(item => item.advisorId === focusedAdvisorId);
  } else if (!state.selectedOutreach || !state.outreach.some(item => item.advisorId === state.selectedOutreach.advisorId)) {
    state.selectedOutreach = state.outreach[0] || null;
  } else {
    state.selectedOutreach = state.outreach.find(item => item.advisorId === state.selectedOutreach.advisorId) || state.selectedOutreach;
  }
  if (state.selectedOutreach) {
    try {
      const detail = await api(`/api/outreach/${encodeURIComponent(state.selectedOutreach.advisorId)}`);
      state.selectedOutreach = detail;
      state.outreach = state.outreach.map(row => row.advisorId === detail.advisorId ? { ...row, ...detail } : row);
    } catch {
      state.selectedOutreach = state.outreach[0] || null;
    }
  }
  if (!focusedAdvisorId || state.selectedOutreach?.advisorId === focusedAdvisorId || !hasActiveOutreachFilters()) {
    state.focusOutreachAdvisorId = "";
  }
  if (renderSidebarPanel) renderOutreachSidebar();
  renderOutreachMain();
}

function renderOutreachRows() {
  if (!state.outreach.length) {
    return `<div class="empty">当前还没有套磁导师。可以先到“导师筛选”页，在导师详情右上角点击“加入套磁”。</div>`;
  }
  return `
    <table class="outreach-table">
      <thead>
        <tr>
          <th style="width:52px">#</th>
          <th>导师</th>
          <th>学校</th>
          <th>套磁状态</th>
          <th>反馈状态</th>
          <th>跟进阶段</th>
          <th>上次联系</th>
        </tr>
      </thead>
      <tbody>
        ${state.outreach.map(renderOutreachRow).join("")}
      </tbody>
    </table>
  `;
}

function renderOutreachRow(item, index) {
  const advisor = item.advisor || {};
  const lastContactLabel = item.lastContactAt ? formatDateLabel(item.lastContactAt) : "未记录";
  const status = normalizeOutreachStatus(item.status);
  const responseStatus = normalizeOutreachResponse(item.responseStatus);
  const stage = normalizeOutreachStage(item.stage);
  return `
    <tr data-outreach-advisor="${escapeHtml(item.advisorId)}" class="${state.selectedOutreach?.advisorId === item.advisorId ? "selected" : ""}">
      <td>${index + 1}</td>
      <td><div class="name-cell">${escapeHtml(advisor.name || item.advisorId)}</div><div class="small muted">${escapeHtml(advisor.city || "")}${advisor.city && advisor.state ? ", " : ""}${escapeHtml(advisor.state || "")}</div></td>
      <td>${escapeHtml(advisor.institution || "")}<div class="small muted">${escapeHtml(advisor.institutionZh || "")}</div></td>
      <td><span class="badge ${badgeClass(status)}">${escapeHtml(status)}</span></td>
      <td><span class="badge ${badgeClass(responseStatus)}">${escapeHtml(responseStatus)}</span></td>
      <td><span class="badge ${badgeClass(stage)}">${escapeHtml(stage)}</span></td>
      <td>${escapeHtml(lastContactLabel)}</td>
    </tr>
  `;
}

function renderOutreachDetail() {
  const item = state.selectedOutreach;
  if (!item) return `<div class="empty">选择一个套磁导师后查看和更新记录。</div>`;
  const advisor = item.advisor || {};
  const today = todayDate();
  const status = normalizeOutreachStatus(item.status);
  const responseStatus = normalizeOutreachResponse(item.responseStatus);
  const stage = normalizeOutreachStage(item.stage);
  const links = renderAdvisorLinks(advisor.links || []);
  return `
    <div class="detail-heading">
      <div>
        <h2>${escapeHtml(advisor.name || item.advisorId)}</h2>
        <div class="subtle">${escapeHtml(advisor.institution || "")} / ${escapeHtml(advisor.institutionZh || "")}</div>
      </div>
    </div>
    <div class="link-list">${links}</div>
    <div class="detail-grid">
      ${renderInfoBlock("研究匹配", [displayFilterLabel("category", advisor.primaryCategory || ""), advisor.matchedKeywords || ""])}
      ${renderInfoBlock("学校与位置", [advisor.schoolTierLabel || "", `${advisor.locationLabelEn || ""} / ${advisor.locationLabelZh || ""}`])}
      ${renderReadOnlyContactSection(advisor.contacts || [])}
      <div class="info-block"><h3>导师看点</h3>${renderAdvisorHighlights(advisor)}</div>
    </div>
    <form class="review-form outreach-form" id="outreachForm">
      <div class="outreach-control-grid">
        ${choiceField("outreachStatus", "套磁状态", outreachStatuses, status, {
          "待联系": "neutral",
          "已发送": "amber",
          "已回复": "green"
        })}
        ${choiceField("outreachStage", "跟进阶段", outreachStages, stage, {
          "跟进中": "amber",
          "已面试": "green",
          "已申请": "green"
        })}
        ${choiceField("outreachResponse", "反馈状态", outreachResponseStatuses, responseStatus, {
          "待回复": "neutral",
          "积极": "green",
          "中性": "amber",
          "拒绝": "red"
        })}
        <label class="date-choice-field">上次联系<input id="outreachLastContact" type="date" value="${escapeHtml(dateInputValue(item.lastContactAt))}"></label>
      </div>
      <label>备注<textarea id="outreachNotes" data-autogrow="true" placeholder="保留长期判断、风险、申请路径">${escapeHtml(item.notes || "")}</textarea></label>
      <div class="toolbar outreach-save-toolbar">
        <button class="button primary" type="submit">保存</button>
        <span class="save-state note-save-state" id="outreachNoteSaveState">${escapeHtml(noteSavedLabel(item.updatedAt))}</span>
      </div>
    </form>
    <div class="outreach-events">
      <div class="outreach-section-title">沟通记录</div>
      <form class="event-form" id="outreachEventForm">
        <label>发生时间<input id="eventAt" type="date" value="${escapeHtml(today)}"></label>
        <label>记录详情<textarea id="eventDetail" data-autogrow="true" required placeholder="粘贴回复要点、面试问题、后续动作；不要粘贴无关隐私信息"></textarea></label>
        <div class="toolbar">
          <button class="button" type="submit">添加记录</button>
          <span class="save-state" id="eventSaveState"></span>
        </div>
      </form>
      <div class="event-list">
        ${(item.events || []).length ? item.events.map(event => `
          <div class="event-row">
            <div>
              <div class="small muted">${escapeHtml(formatDateLabel(event.eventAt))} · ${escapeHtml(event.createdBy || "")}</div>
              <p>${escapeHtml(event.detail || event.summary || "无记录详情")}</p>
            </div>
            <button class="button danger event-delete" type="button" data-outreach-event-id="${escapeHtml(event.id)}">删除</button>
          </div>
        `).join("") : `<div class="empty compact-empty">还没有沟通记录。</div>`}
      </div>
    </div>
  `;
}

async function renderOutreachMain() {
  $("main").innerHTML = `
    <section class="page work-only-page">
      <div class="outreach-workspace ${state.aiPanelOpen ? "with-ai" : ""}">
        <div class="panel table-wrap">
          ${renderOutreachRows()}
        </div>
        <div class="panel detail outreach-detail-panel">
          <div class="panel-title">
            <span>套磁详情</span>
            <div class="toolbar">
              ${state.selectedOutreach && state.aiSettings?.available ? `<button class="button" id="advisorAiLookup" type="button">${state.aiBusy ? "打开中..." : "AI助手"}</button>` : ""}
              ${state.selectedOutreach ? `<button class="button danger" id="removeOutreach" type="button">移出清单</button>` : ""}
            </div>
          </div>
          <div class="panel-body">${renderOutreachDetail()}</div>
        </div>
        ${state.aiPanelOpen ? `<div class="panel detail ai-panel"><div class="panel-title"><span>AI助手</span><button class="button" id="closeAiPanel" type="button">关闭</button></div><div class="panel-body">${renderAiConversationPanel()}</div></div>` : ""}
      </div>
    </section>
  `;
  bindOutreachEvents();
}

async function loadSelectedOutreachDetail(advisorId) {
  const wasAiOpen = state.aiPanelOpen;
  if (advisorId !== state.selectedOutreach?.advisorId) {
    resetAiState(false);
  }
  const item = await api(`/api/outreach/${encodeURIComponent(advisorId)}`);
  state.selectedOutreach = item;
  state.outreach = state.outreach.map(row => row.advisorId === advisorId ? { ...row, ...item } : row);
  renderOutreachMain();
  if (wasAiOpen && advisorId) {
    void openAdvisorAiConversation(advisorId);
  }
}

function applyOutreachPatchResult(advisorId, result) {
  const resultItem = result.item || {};
  state.outreach = state.outreach.map(row => row.advisorId === advisorId ? { ...row, ...resultItem } : row);
  if (state.selectedOutreach?.advisorId === advisorId) {
    state.selectedOutreach = {
      ...state.selectedOutreach,
      ...resultItem,
      events: state.selectedOutreach.events || resultItem.events || []
    };
  }
}

function enqueueOutreachSave(operation) {
  const next = state.outreachSaveQueue.catch(() => {}).then(operation);
  state.outreachSaveQueue = next.catch(() => {});
  return next;
}

async function saveOutreachPatch(advisorId, fields, values = {}) {
  return enqueueOutreachSave(async () => {
    const result = await api(`/api/outreach/${encodeURIComponent(advisorId)}`, {
      method: "POST",
      body: JSON.stringify({ fields, ...values })
    });
    applyOutreachPatchResult(advisorId, result);
    return result;
  });
}

function bindOutreachEvents() {
  bindAutoGrowTextareas($("main") || document);
  $("main").querySelectorAll("[data-outreach-advisor]").forEach(button => {
    button.addEventListener("click", async () => {
      await loadSelectedOutreachDetail(button.dataset.outreachAdvisor);
    });
  });
  const form = $("outreachForm");
  if (form && state.selectedOutreach) {
    const advisorId = state.selectedOutreach.advisorId;
    const noteSaveState = bindDirtySaveState({
      fieldIds: ["outreachNotes"],
      stateId: "outreachNoteSaveState",
      savedAt: state.selectedOutreach.updatedAt || ""
    });
    const outreachFieldMap = {
      outreachStatus: "status",
      outreachStage: "stage",
      outreachResponse: "responseStatus"
    };
    bindChoiceButtons(form, async ({ target, value, previousValue, field: choiceFieldElement }) => {
      const apiField = outreachFieldMap[target];
      if (!apiField) return;
      if (!value && previousValue) {
        setChoiceFieldValue(choiceFieldElement, previousValue);
        return;
      }
      await saveOutreachPatch(advisorId, [apiField], { [apiField]: value });
    });
    const lastContact = $("outreachLastContact");
    if (lastContact) {
      lastContact.addEventListener("change", async event => {
        const previousValue = state.selectedOutreach?.lastContactAt ? dateInputValue(state.selectedOutreach.lastContactAt) : "";
        const nextValue = event.target.value || "";
        try {
          await saveOutreachPatch(advisorId, ["lastContactAt"], { lastContactAt: nextValue });
        } catch (error) {
          if (event.target.value === nextValue) event.target.value = previousValue;
          console.warn("上次联系保存失败", error);
        }
      });
    }
    form.addEventListener("submit", async event => {
      event.preventDefault();
      try {
        noteSaveState.markSaving();
        const submittedNotes = $("outreachNotes")?.value || "";
        const result = await saveOutreachPatch(advisorId, ["notes"], { notes: submittedNotes });
        noteSaveState.markSaved(result.item?.updatedAt || new Date(), { outreachNotes: submittedNotes });
      } catch (error) {
        noteSaveState.markError();
        console.warn("备注保存失败", error);
      }
    });
  }
  const remove = $("removeOutreach");
  if (remove && state.selectedOutreach) {
    remove.addEventListener("click", async () => {
      const name = state.selectedOutreach.advisor?.name || state.selectedOutreach.advisorId;
      const ok = window.confirm(`确认把 ${name} 移出套磁清单吗？历史记录会保留。`);
      if (!ok) return;
      await api(`/api/outreach/${encodeURIComponent(state.selectedOutreach.advisorId)}`, { method: "DELETE" });
      state.selectedOutreach = null;
      await loadOutreach();
    });
  }
  const eventForm = $("outreachEventForm");
  if (eventForm && state.selectedOutreach) {
    eventForm.addEventListener("submit", async event => {
      event.preventDefault();
      const detail = $("eventDetail").value.trim();
      if (!detail) {
        $("eventSaveState").textContent = "请先填写记录详情。";
        return;
      }
      $("eventSaveState").textContent = "添加中...";
      const advisorId = state.selectedOutreach.advisorId;
      const result = await api(`/api/outreach/${encodeURIComponent(advisorId)}/events`, {
        method: "POST",
        body: JSON.stringify({
          eventType: "备注",
          eventAt: $("eventAt").value,
          summary: "",
          detail
        })
      });
      state.selectedOutreach = result.item;
      state.outreach = state.outreach.map(row => row.advisorId === advisorId ? { ...row, ...result.item } : row);
      renderOutreachMain();
    });
  }
  $("main").querySelectorAll("[data-outreach-event-id]").forEach(button => {
    button.addEventListener("click", async () => {
      if (!state.selectedOutreach) return;
      const ok = window.confirm("确认删除这条沟通记录吗？");
      if (!ok) return;
      const advisorId = state.selectedOutreach.advisorId;
      const result = await api(`/api/outreach/${encodeURIComponent(advisorId)}/events/${encodeURIComponent(button.dataset.outreachEventId)}`, {
        method: "DELETE"
      });
      state.selectedOutreach = result.item;
      state.outreach = state.outreach.map(row => row.advisorId === advisorId ? { ...row, ...result.item } : row);
      renderOutreachMain();
    });
  });
  bindAiAdvisorActions();
}

function renderProgramSidebar() {
  const filters = state.programFilters;
  $("sidebar").innerHTML = `
    <div class="filter-sidebar-layout">
      <div class="filter-sidebar-scroll">
        <div class="side-title">申请跟踪</div>
        <div class="side-section filter-search-section">
          <label>搜索申请</label>
          <input class="filter-search-input" id="programSearch" value="${escapeHtml(filters.search)}" placeholder="学校、项目、院系、备注">
        </div>
        ${compactFilterButtons("申请状态", "status", programStatuses, filters, "program")}
        ${compactFilterButtons("优先级", "priority", programPriorities, filters, "program")}
      </div>
      <div class="filter-sidebar-actions sidebar-action-stack">
        <button class="sidebar-primary-button" id="newProgram" type="button">新增申请</button>
        <button class="sidebar-clear-button" id="clearProgramFilters" type="button">清空筛选</button>
      </div>
    </div>
  `;
  $("programSearch").addEventListener("input", event => {
    state.programFilters.search = event.target.value;
    window.clearTimeout(programSearchTimer);
    programSearchTimer = window.setTimeout(() => loadPrograms({ renderSidebarPanel: false }), 280);
  });
  $("sidebar").querySelectorAll("[data-program-all]").forEach(button => {
    button.addEventListener("click", () => {
      state.programFilters[button.dataset.programAll] = [];
      loadPrograms();
    });
  });
  $("sidebar").querySelectorAll("[data-program-filter]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.programFilter;
      const value = button.dataset.filterValue;
      const current = new Set(selectedFilterValues(state.programFilters, key));
      if (current.has(value)) current.delete(value);
      else current.add(value);
      state.programFilters[key] = Array.from(current);
      loadPrograms();
    });
  });
  $("newProgram").addEventListener("click", () => {
    state.selectedProgram = null;
    state.programFormOpen = true;
    renderProgramsMain();
  });
  $("clearProgramFilters").addEventListener("click", () => {
    state.programFilters = createEmptyProgramFilters();
    loadPrograms();
  });
}

function programsQuery() {
  const params = new URLSearchParams();
  if (state.programFilters.search) params.set("search", state.programFilters.search);
  ["status", "priority"].forEach(key => {
    selectedFilterValues(state.programFilters, key).forEach(value => params.append(key, value));
  });
  return params.toString();
}

async function loadPrograms(options = {}) {
  const { renderSidebarPanel = true } = options;
  const payload = await api(`/api/programs?${programsQuery()}`);
  state.programs = payload.items || [];
  if (state.selectedProgram && !state.programs.some(item => item.id === state.selectedProgram.id)) {
    state.selectedProgram = null;
  }
  if (renderSidebarPanel) renderProgramSidebar();
  renderProgramsMain();
}

function renderProgramRows() {
  if (!state.programs.length) {
    return `<div class="empty">还没有申请记录。点击左侧“新增申请”，手动录入已确认的学校和项目要求。</div>`;
  }
  return `
    <div class="program-list">
      ${state.programs.map(item => `
        <button type="button" class="program-row ${state.selectedProgram?.id === item.id ? "selected" : ""}" data-program-id="${escapeHtml(item.id)}">
          <div>
            <strong>${escapeHtml(item.school)}</strong>
            <div class="small muted">${escapeHtml(item.programName)} · ${escapeHtml(item.degree || "PhD")}</div>
          </div>
          <div class="status-stack align-right">
            <span class="badge ${badgeClass(item.status)}">${escapeHtml(item.status || "候选")}</span>
            ${item.priority ? `<span class="badge ${badgeClass(item.priority)}">${escapeHtml(item.priority)}</span>` : ""}
            <span class="small muted">${escapeHtml(item.deadline || "无截止日期")}</span>
          </div>
        </button>
      `).join("")}
    </div>
  `;
}

function blankProgram() {
  return {
    id: null,
    school: "",
    department: "",
    programName: "",
    degree: "PhD",
    deadline: "",
    status: "候选",
    priority: "",
    requirements: "",
    notes: ""
  };
}

function renderProgramForm() {
  const item = state.programFormOpen || state.selectedProgram ? (state.selectedProgram || blankProgram()) : null;
  if (!item) {
    return `<div class="empty">选择一条申请查看详情，或点击左侧“新增申请”。</div>`;
  }
  return `
    <form class="review-form" id="programForm">
      <div class="form-row">
        <label>学校<input id="programSchool" value="${escapeHtml(item.school || "")}" placeholder="例如：University of Toronto"></label>
        <label>院系<input id="programDepartment" value="${escapeHtml(item.department || "")}" placeholder="例如：Computer Science"></label>
      </div>
      <div class="form-row">
        <label>项目名称<input id="programName" value="${escapeHtml(item.programName || "")}" placeholder="例如：PhD in Computer Science"></label>
        <label>学位<input id="programDegree" value="${escapeHtml(item.degree || "PhD")}"></label>
      </div>
      <div class="form-row">
        <label>截止日期<input id="programDeadline" value="${escapeHtml(item.deadline || "")}" placeholder="YYYY-MM-DD"></label>
        ${selectField("programPriority", "优先级", ["", ...programPriorities], item.priority)}
      </div>
      ${selectField("programStatus", "申请状态", programStatuses, item.status || "候选")}
      <label>材料要求<textarea id="programRequirements" data-autogrow="true" placeholder="记录已确认的材料要求、推荐信数量、成绩单要求等">${escapeHtml(item.requirements || "")}</textarea></label>
      <label>备注<textarea id="programNotes" data-autogrow="true" placeholder="记录申请路径、funding、风险和待确认项">${escapeHtml(item.notes || "")}</textarea></label>
      <div class="toolbar">
        <button class="button primary" type="submit">${item.id ? "保存申请" : "创建申请"}</button>
        ${item.id ? `<button class="button danger" id="deleteProgram" type="button">删除申请</button>` : `<button class="button" id="cancelProgram" type="button">取消</button>`}
        <span class="save-state note-save-state" id="programSaveState">${escapeHtml(noteSavedLabel(item.updatedAt))}</span>
      </div>
    </form>
  `;
}

function renderProgramsMain() {
  $("main").innerHTML = `
    <section class="page work-only-page">
      <div class="program-workspace">
        <div class="panel table-wrap">
          <div class="panel-title">
            <span>申请清单</span>
            <span class="subtle">${state.programs.length} 条申请</span>
          </div>
          <div class="panel-body outreach-scroll">${renderProgramRows()}</div>
        </div>
        <div class="panel detail">
          <div class="panel-title">申请详情</div>
          <div class="panel-body">${renderProgramForm()}</div>
        </div>
      </div>
    </section>
  `;
  bindProgramEvents();
}

function bindProgramEvents() {
  bindAutoGrowTextareas($("main") || document);
  $("main").querySelectorAll("[data-program-id]").forEach(button => {
    button.addEventListener("click", () => {
      const id = Number(button.dataset.programId);
      state.selectedProgram = state.programs.find(item => item.id === id) || null;
      state.programFormOpen = false;
      renderProgramsMain();
    });
  });
  const form = $("programForm");
  if (form) {
    const programNoteSaveState = bindDirtySaveState({
      fieldIds: ["programRequirements", "programNotes"],
      stateId: "programSaveState",
      savedAt: state.selectedProgram?.updatedAt || ""
    });
    const setProgramFormDisabled = disabled => {
      form.querySelectorAll("input, select, textarea, button").forEach(control => {
        control.disabled = disabled;
      });
    };
    form.addEventListener("submit", async event => {
      event.preventDefault();
      programNoteSaveState.markSaving();
      setProgramFormDisabled(true);
      const id = state.selectedProgram?.id;
      const submittedRequirements = $("programRequirements").value;
      const submittedNotes = $("programNotes").value;
      try {
        const result = await api(id ? `/api/programs/${encodeURIComponent(id)}` : "/api/programs", {
          method: "POST",
          body: JSON.stringify({
            school: $("programSchool").value,
            department: $("programDepartment").value,
            programName: $("programName").value,
            degree: $("programDegree").value,
            deadline: $("programDeadline").value,
            status: $("programStatus").value,
            priority: $("programPriority").value,
            requirements: submittedRequirements,
            notes: submittedNotes
          })
        });
        programNoteSaveState.markSaved(result.item?.updatedAt || new Date(), {
          programRequirements: submittedRequirements,
          programNotes: submittedNotes
        });
        state.selectedProgram = result.item;
        state.programFormOpen = false;
        await loadPrograms();
      } catch (error) {
        setProgramFormDisabled(false);
        programNoteSaveState.markError();
        console.warn("申请保存失败", error);
      }
    });
  }
  const deleteButton = $("deleteProgram");
  if (deleteButton && state.selectedProgram) {
    deleteButton.addEventListener("click", async () => {
      const ok = window.confirm(`确认删除申请「${state.selectedProgram.school} - ${state.selectedProgram.programName}」吗？`);
      if (!ok) return;
      await api(`/api/programs/${encodeURIComponent(state.selectedProgram.id)}`, { method: "DELETE" });
      state.selectedProgram = null;
      await loadPrograms();
    });
  }
  const cancelButton = $("cancelProgram");
  if (cancelButton) {
    cancelButton.addEventListener("click", () => {
      state.programFormOpen = false;
      renderProgramsMain();
    });
  }
}

function renderSettingsSidebar() {
  $("sidebar").innerHTML = `
    <div class="side-title">系统设置</div>
    <div class="side-nav">
      <button class="active" type="button">AI API 设置</button>
    </div>
  `;
}

async function renderSettings() {
  if (!aiSettingsLoaded) await loadAiSettings();
  renderSettingsSidebar();
  const settings = state.aiSettings || {};
  const databaseKeyAllowed = settings.databaseKeyAllowed !== false;
  const keyInputDisabled = settings.keyManagedByEnv || !databaseKeyAllowed;
  const keyPlaceholder = settings.keyManagedByEnv
    ? "已由 PHD_PLATFORM_AI_API_KEY 环境变量托管"
    : (!databaseKeyAllowed ? "当前环境不允许保存到数据库" : (settings.hasApiKey ? "已保存；留空表示不修改" : "粘贴 API Key"));
  const keyStorageHint = settings.keyManagedByEnv
    ? "当前 API Key 由环境变量托管，页面不会保存数据库 Key。"
    : (!databaseKeyAllowed
        ? "当前环境不允许把 AI API Key 保存到数据库，请在服务器环境变量中设置 PHD_PLATFORM_AI_API_KEY。"
        : "本地临时开发可以保存数据库 Key；公网部署请使用 PHD_PLATFORM_AI_API_KEY。");
  $("main").innerHTML = `
    <section class="page">
      <div class="page-head">
        <div>
          <h1>系统设置</h1>
          <div class="subtle">配置后才会在导师详情中显示“AI助手”。API Key 不会在前端明文回显。</div>
        </div>
      </div>
      <div class="settings-workspace">
        <div class="panel">
          <div class="panel-title">AI API 设置</div>
          <div class="panel-body">
            <form class="review-form" id="aiSettingsForm">
              <label class="checkbox-row">
                <input id="aiEnabled" type="checkbox" ${settings.enabled ? "checked" : ""}>
                <span>启用 AI助手</span>
              </label>
              <div class="form-row">
                <label>Provider 名称
                  <input id="aiProviderName" value="${escapeHtml(settings.providerName || "")}" placeholder="例如：OpenAI / Kimi / DeepSeek">
                </label>
                <label>模型名
                  <input id="aiModelName" value="${escapeHtml(settings.modelName || "")}" placeholder="例如：gpt-4.1 / moonshot-v1-32k">
                </label>
              </div>
              <label>API 地址（Base URL 或 Chat Completions Endpoint）
                <input id="aiEndpointUrl" value="${escapeHtml(settings.endpointUrl || "")}" placeholder="例如：https://api.kkrich.ltd/v1">
              </label>
              <div class="form-row">
                <label>Temperature（可留空）
                  <input id="aiTemperature" value="${escapeHtml(settings.temperature ?? "")}" placeholder="先留空；需要控制随机性时再填 0.2">
                </label>
                <label>API Key
                  <input id="aiApiKey" type="password" autocomplete="new-password" ${keyInputDisabled ? "disabled" : ""} placeholder="${escapeHtml(keyPlaceholder)}">
                </label>
              </div>
              <div class="subtle">${escapeHtml(keyStorageHint)}</div>
              <label class="checkbox-row">
                <input id="aiClearKey" type="checkbox" ${settings.keyManagedByEnv ? "disabled" : ""}>
                <span>清除已保存的 API Key</span>
              </label>
              <div class="info-block">
                <h3>AI 工具能力</h3>
                <label class="checkbox-row">
                  <input id="aiToolsEnabled" type="checkbox" ${settings.toolsEnabled ? "checked" : ""}>
                  <span>启用联网工具</span>
                </label>
                <label class="checkbox-row">
                  <input id="aiAllowSearchPages" type="checkbox" ${settings.allowSearchPages ? "checked" : ""}>
                  <span>允许抓取搜索结果页</span>
                </label>
                <div class="form-row">
                  <label>最多结果数
                    <input id="aiToolMaxResults" type="number" min="1" max="8" value="${escapeHtml(settings.toolMaxResults || 5)}">
                  </label>
                  <label>单次超时秒数
                    <input id="aiToolTimeoutSeconds" type="number" min="3" max="20" value="${escapeHtml(settings.toolTimeoutSeconds || 8)}">
                  </label>
                </div>
                <label>缓存秒数
                  <input id="aiToolCacheTtlSeconds" type="number" min="300" max="604800" value="${escapeHtml(settings.toolCacheTtlSeconds || 86400)}">
                </label>
              </div>
              <div class="toolbar">
                <button class="button primary" type="submit">保存 AI 设置</button>
                <button class="button" id="aiTestButton" type="button" ${settings.available ? "" : "disabled"}>测试已保存配置</button>
                <span class="save-state" id="aiSettingsState">${settings.available ? "AI 已可用" : settings.enabled ? "AI 已开启，但配置不完整" : "AI 未开启"}</span>
              </div>
            </form>
          </div>
        </div>
        <div class="panel">
          <div class="panel-title">AI助手工作流</div>
          <div class="panel-body">
            <div class="settings-note">
              <p>开启并配置完整后，导师详情右上角会显示“AI助手”，打开绑定当前导师的 Chatbot。</p>
              <p>API 地址可以填写 Base URL，例如 https://api.kkrich.ltd/v1；系统会自动补全聊天接口。</p>
              <p>首次测试建议先把 Temperature 留空，避免部分中转线路不接受可选参数。</p>
              <p>点击后会创建一个绑定当前导师的对话，并把平台已有导师信息作为上下文发给模型。</p>
              <p>联网工具开启后，AI助手会按问题自动查询天气、文献、学校、城市和网页资料；工具结果只进入当前对话，不自动写回导师库。</p>
              <p>模型输出必须区分已知信息、推断和待确认项；公开网页事实仍需要人工复核后再写入导师事实库。</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
  bindAiSettingsForm();
}

function bindAiSettingsForm() {
  const form = $("aiSettingsForm");
  if (!form) return;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    $("aiSettingsState").textContent = "保存中...";
    const result = await api("/api/ai/settings", {
      method: "POST",
      body: JSON.stringify({
        enabled: $("aiEnabled").checked,
        providerName: $("aiProviderName").value,
        endpointUrl: $("aiEndpointUrl").value,
        modelName: $("aiModelName").value,
        temperature: $("aiTemperature").value,
        apiKey: $("aiApiKey").value,
        clearApiKey: $("aiClearKey").checked,
        toolsEnabled: $("aiToolsEnabled").checked,
        allowSearchPages: $("aiAllowSearchPages").checked,
        toolMaxResults: $("aiToolMaxResults").value,
        toolTimeoutSeconds: $("aiToolTimeoutSeconds").value,
        toolCacheTtlSeconds: $("aiToolCacheTtlSeconds").value
      })
    });
    state.aiSettings = result.settings;
    $("aiApiKey").value = "";
    $("aiClearKey").checked = false;
    $("aiTestButton").disabled = !state.aiSettings.available;
    $("aiSettingsState").textContent = state.aiSettings.available ? "已保存，AI 按钮会显示" : "已保存，但配置未完整";
  });
  const testButton = $("aiTestButton");
  if (testButton) {
    testButton.addEventListener("click", async () => {
      testButton.disabled = true;
      $("aiSettingsState").textContent = "测试中...";
      try {
        const result = await api("/api/ai/settings/test", {
          method: "POST",
          body: JSON.stringify({})
        });
        $("aiSettingsState").textContent = `测试通过：${result.message || "连接正常"}`;
      } catch (error) {
        $("aiSettingsState").textContent = `测试失败：${error.message}`;
      } finally {
        testButton.disabled = !state.aiSettings?.available;
      }
    });
  }
}

async function renderDashboard() {
  const summary = await api("/api/summary");
  state.dashboardSummary = summary;
  if (state.dashboardView === "heatmap") {
    $("main").innerHTML = `
      <section class="page dashboard-heatmap-page">
        <div class="panel dashboard-heatmap-panel">
          ${renderDashboardHeatmap(summary.advisorHeatmapItems || [])}
        </div>
      </section>
    `;
    bindDashboardHeatmap();
    return;
  }
  const scopeMeta = dashboardProfileScopeMeta(summary, state.dashboardProfileScope);
  state.dashboardProfileScope = scopeMeta.key;
  const profileItems = dashboardProfileItems(summary, scopeMeta.key);
  const emptyText = dashboardProfileEmptyText(scopeMeta);
  const categoryRows = dashboardProfileRows(profileItems, "category");
  const stageRows = dashboardProfileRows(profileItems, "stage");
  const tierRows = dashboardProfileRows(profileItems, "tier");
  const outreachRows = dashboardProfileRows(profileItems, "outreachStatus");
  $("main").innerHTML = `
    <section class="page dashboard-page">
      <div class="dashboard-grid">
        ${renderDashboardMetricCards(summary)}
      </div>
      <div class="dashboard-panels">
        <div class="panel dashboard-chart-panel research-pool-panel">
          <div class="panel-title">研究池</div>
          <div class="panel-body dashboard-panel-body research-pool-chart">
            ${renderDashboardBars(categoryRows, emptyText)}
          </div>
        </div>
        <div class="panel dashboard-chart-panel advisor-stage-panel">
          <div class="panel-title">导师阶段</div>
          <div class="panel-body dashboard-panel-body advisor-stage-chart">
            ${renderDashboardBars(stageRows, emptyText)}
          </div>
        </div>
        <div class="panel dashboard-chart-panel school-tier-panel">
          <div class="panel-title">学校梯队</div>
          <div class="panel-body dashboard-panel-body school-tier-chart">
            ${renderDashboardBars(tierRows, emptyText)}
          </div>
        </div>
        <div class="panel dashboard-chart-panel outreach-status-panel">
          <div class="panel-title">套磁状态</div>
          <div class="panel-body dashboard-panel-body outreach-status-chart">
            ${renderDashboardBars(outreachRows, emptyText)}
          </div>
        </div>
      </div>
    </section>
  `;
  $("main").querySelectorAll("[data-dashboard-profile-scope]").forEach(button => {
    button.addEventListener("click", () => {
      state.dashboardProfileScope = button.dataset.dashboardProfileScope || "all";
      void renderDashboard();
    });
  });
  equalizeDashboardChartPanels();
}

function refreshDashboardHeatmapPanel() {
  const panel = $("main").querySelector(".dashboard-heatmap-panel");
  if (!panel || !state.dashboardSummary) {
    void renderDashboard();
    return;
  }
  panel.innerHTML = renderDashboardHeatmap(state.dashboardSummary.advisorHeatmapItems || []);
  bindDashboardHeatmap();
}

function bindDashboardHeatmap() {
  const rows = $("dashboardHeatmapRows");
  const cols = $("dashboardHeatmapCols");
  if (!rows || !cols) return;
  rows.addEventListener("change", event => {
    state.dashboardHeatmapRows = event.target.value;
    ensureDashboardHeatmapDimensions();
    refreshDashboardHeatmapPanel();
  });
  cols.addEventListener("change", event => {
    state.dashboardHeatmapCols = event.target.value;
    ensureDashboardHeatmapDimensions();
    refreshDashboardHeatmapPanel();
  });
  $("main").querySelectorAll("[data-heatmap-filter-all]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.heatmapFilterAll;
      state.dashboardHeatmapFilters = state.dashboardHeatmapFilters || createEmptyDashboardHeatmapFilters();
      state.dashboardHeatmapFilters[key] = [];
      refreshDashboardHeatmapPanel();
    });
  });
  $("main").querySelectorAll("[data-heatmap-filter-clear]").forEach(button => {
    button.addEventListener("click", () => {
      state.dashboardHeatmapFilters = createEmptyDashboardHeatmapFilters();
      refreshDashboardHeatmapPanel();
    });
  });
  $("main").querySelectorAll("[data-heatmap-filter-value]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.heatmapFilterKey;
      const value = button.dataset.heatmapFilterValue;
      state.dashboardHeatmapFilters = state.dashboardHeatmapFilters || createEmptyDashboardHeatmapFilters();
      const current = new Set(selectedDashboardHeatmapValues(key));
      if (current.has(value)) {
        current.delete(value);
      } else {
        current.add(value);
      }
      state.dashboardHeatmapFilters[key] = Array.from(current);
      refreshDashboardHeatmapPanel();
    });
  });
}

function equalizeDashboardChartPanels() {
  window.requestAnimationFrame(() => {
    const panels = [...$("main").querySelectorAll(".dashboard-chart-panel")];
    if (!panels.length) return;
    panels.forEach(panel => {
      panel.style.height = "";
    });
    const maxHeight = Math.ceil(Math.max(...panels.map(panel => panel.getBoundingClientRect().height)));
    panels.forEach(panel => {
      panel.style.height = `${maxHeight}px`;
    });
  });
}

async function loadAdvisors(options = {}) {
  if (state.page !== "advisors") return;
  const { renderSidebarPanel = true, append = false, useCache = true } = options;
  const queryKey = advisorFilterKey();
  const requestId = state.advisorListRequestId + 1;
  state.advisorListRequestId = requestId;
  state.advisorListQueryKey = queryKey;
  state.advisorDetailError = "";

  if (append) {
    state.advisorLoadingMore = true;
    renderAdvisorMain();
  } else {
    state.advisorListScrollTop = 0;
    state.advisorLoading = true;
    state.advisorLoadingMore = false;
    state.advisorHasMore = false;
    const cached = useCache ? cachedAdvisorList(queryKey) : null;
    if (cached) {
      state.advisors = cached.items || [];
      state.advisorTotal = cached.total || state.advisors.length;
      state.advisorHasMore = Boolean(cached.hasMore);
      if (!state.selectedAdvisor || !state.advisors.some(item => item.id === state.selectedAdvisor.id)) {
        state.selectedAdvisor = state.advisors[0] || null;
      }
      if (renderSidebarPanel) renderSidebar();
      renderAdvisorMain();
      if (state.selectedAdvisor?.id) {
        void loadAdvisorDetail(state.selectedAdvisor.id, { useCache: true });
      }
    } else {
      state.advisors = [];
      state.advisorTotal = 0;
      state.selectedAdvisor = null;
      if (renderSidebarPanel) renderSidebar();
      renderAdvisorMain();
    }
  }

  const offset = append ? state.advisors.length : 0;
  try {
    const payload = await api(`/api/advisors?${buildAdvisorQuery({ limit: advisorPageSize, offset })}`);
    if (state.page !== "advisors" || requestId !== state.advisorListRequestId || queryKey !== state.advisorListQueryKey) return;
    const nextItems = (payload.items || []).map(advisorListSummary);
    state.advisors = append ? [...state.advisors, ...nextItems] : nextItems;
    state.advisorTotal = payload.total || state.advisors.length;
    state.advisorHasMore = Boolean(payload.hasMore);
    state.advisorLoading = false;
    state.advisorLoadingMore = false;
    if (!state.selectedAdvisor || !state.advisors.some(item => item.id === state.selectedAdvisor.id)) {
      state.selectedAdvisor = state.advisors[0] || null;
    } else {
      const latestSummary = state.advisors.find(item => item.id === state.selectedAdvisor.id);
      state.selectedAdvisor = mergeAdvisorCollaborativeState(state.selectedAdvisor, latestSummary);
    }
    if (!append) cacheAdvisorList(queryKey, payload);
    if (renderSidebarPanel) renderSidebar();
    renderAdvisorMain();
    if (!append && state.selectedAdvisor?.id) {
      void loadAdvisorDetail(state.selectedAdvisor.id, { useCache: true });
    }
  } catch (error) {
    if (state.page !== "advisors" || requestId !== state.advisorListRequestId) return;
    state.advisorLoading = false;
    state.advisorLoadingMore = false;
    renderAdvisorMain();
    throw error;
  }
}

async function loadAdvisorDetail(advisorId, options = {}) {
  if (state.page !== "advisors") return;
  const summary = state.advisors.find(item => item.id === advisorId);
  if (!summary) return;
  const { useCache = true } = options;
  const requestId = state.advisorDetailRequestId + 1;
  state.advisorDetailRequestId = requestId;
  state.advisorDetailLoadingId = advisorId;
  state.advisorDetailError = "";

  const cached = useCache ? cachedAdvisorDetail(advisorId) : null;
  if (cached) {
    const merged = { ...mergeAdvisorCollaborativeState(cached, summary), _detailLoaded: true };
    state.selectedAdvisor = merged;
    state.advisors = state.advisors.map(item => item.id === advisorId ? { ...item, ...merged } : item);
  } else {
    state.selectedAdvisor = { ...summary, _detailLoading: true };
  }
  renderAdvisorMain();

  try {
    const detail = await api(`/api/advisors/${encodeURIComponent(advisorId)}`);
    if (state.page !== "advisors" || requestId !== state.advisorDetailRequestId || state.selectedAdvisor?.id !== advisorId) return;
    const merged = { ...mergeAdvisorCollaborativeState(detail, summary), _detailLoaded: true };
    state.selectedAdvisor = merged;
    state.advisors = state.advisors.map(item => item.id === advisorId ? { ...item, ...merged } : item);
    state.advisorDetailLoadingId = "";
    cacheAdvisorDetail(advisorId, merged);
    renderAdvisorMain();
  } catch (error) {
    if (state.page !== "advisors" || requestId !== state.advisorDetailRequestId || state.selectedAdvisor?.id !== advisorId) return;
    state.advisorDetailLoadingId = "";
    state.advisorDetailError = error.message;
    state.selectedAdvisor = { ...summary, _detailError: error.message };
    renderAdvisorMain();
  }
}

function maybeAutoLoadAdvisors(panel = $("advisorListPanel")) {
  if (!panel || state.page !== "advisors") return;
  state.advisorListScrollTop = panel.scrollTop;
  if (!state.advisorHasMore || state.advisorLoading || state.advisorLoadingMore) return;
  const remaining = panel.scrollHeight - panel.scrollTop - panel.clientHeight;
  if (remaining <= advisorAutoLoadThresholdPx) {
    void loadAdvisors({ renderSidebarPanel: false, append: true, useCache: false });
  }
}

function bindAdvisorListAutoLoad() {
  const panel = $("advisorListPanel");
  if (!panel) return;
  if (state.advisorListScrollTop > 0) {
    panel.scrollTop = state.advisorListScrollTop;
  }
  panel.addEventListener("scroll", () => {
    maybeAutoLoadAdvisors(panel);
  }, { passive: true });
  window.requestAnimationFrame(() => {
    if ($("advisorListPanel") !== panel) return;
    if (state.advisorListScrollTop > 0) {
      panel.scrollTop = state.advisorListScrollTop;
    }
    maybeAutoLoadAdvisors(panel);
  });
}

function selectAdvisor(advisorId) {
  const nextAdvisor = state.advisors.find(item => item.id === advisorId);
  if (!nextAdvisor) return;
  const wasAiOpen = state.aiPanelOpen;
  if (nextAdvisor.id !== state.selectedAdvisor?.id) {
    resetAiState(false);
  }
  state.selectedAdvisor = nextAdvisor;
  renderAdvisorMain();
  void loadAdvisorDetail(nextAdvisor.id, { useCache: true });
  if (wasAiOpen) {
    void openAdvisorAiConversation(nextAdvisor.id);
  }
}

function badgeClass(value) {
  if (["已回复", "已面试", "已申请", "已查询", "积极", "高", "高兴趣", "很有兴趣", "保留", "AP / 早期", "已加入", "已提交", "已录取"].includes(value)) return "green";
  if (["已发送", "跟进中", "请求查询", "需查询", "中性", "中", "一般", "有兴趣", "待讨论", "准备中", "需跟进", "待判断", "候选", "准备套磁"].includes(value)) return "amber";
  if (["低", "不感兴趣", "排除", "拒绝", "不继续", "已取消", "不申请", "已拒绝"].includes(value)) return "red";
  return "";
}

function normalizeOutreachStatus(value) {
  if (["准备中", "待联系"].includes(value)) return "待联系";
  if (["已回复", "需跟进", "已面试", "已申请"].includes(value)) return "已回复";
  if (value === "已发送") return "已发送";
  return value || "待联系";
}

function normalizeOutreachResponse(value) {
  if (["", "未回复", "待回复", "待判断", "自动回复"].includes(value || "")) return "待回复";
  if (["积极", "中性", "拒绝"].includes(value)) return value;
  return "待回复";
}

function normalizeOutreachStage(value) {
  if (["已面试", "面试中"].includes(value)) return "已面试";
  if (["已申请", "申请中"].includes(value)) return "已申请";
  if (["", "准备套磁", "首次邮件", "等待回复", "跟进中", "结束"].includes(value || "")) return "跟进中";
  return value || "跟进中";
}

function isEmail(value) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(value || "").trim());
}

function isUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function applyContactSummary(item, contacts) {
  const rows = contacts || [];
  const primary = rows.find(contact => contact.isPrimary) || rows.find(contact => isEmail(contact.value)) || rows[0] || null;
  item.contacts = rows;
  item.contactCount = rows.length;
  item.hasEmail = rows.some(contact => isEmail(contact.value));
  item.primaryContact = primary?.value || "";
  item.primaryContactType = primary?.contactType || "";
  return item;
}

function contactHref(value) {
  if (isEmail(value)) return `mailto:${value}`;
  if (isUrl(value)) return value;
  return "";
}

function contactSourceText(contact) {
  return contact.evidenceText || contact.sourceUrl || "来源待补";
}

function isPlaceholderContact(contact) {
  const value = String(contact?.value || "").trim();
  const text = `${value} ${contact?.sourceUrl || ""} ${contact?.evidenceText || ""}`;
  return !value
    || value === "未找到公开联系方式"
    || value === "未找到"
    || text.includes("已并发联网尝试")
    || text.includes("未发现可确认")
    || text.includes("页面访问失败")
    || text.includes("未找到导师本人邮箱");
}

function renderContactRows(contacts = []) {
  const visibleContacts = contacts.filter(contact => !isPlaceholderContact(contact));
  if (!visibleContacts.length) return `<p>未找到</p>`;
  return `
    <div class="contact-list">
      ${visibleContacts.map(contact => {
        const href = contactHref(contact.value);
        return `
          <div class="contact-row">
            ${href ? `<a href="${escapeHtml(href)}"${isEmail(contact.value) ? "" : ` target="_blank" rel="noopener noreferrer"`}>${escapeHtml(contact.value)}</a>` : `<strong>${escapeHtml(contact.value)}</strong>`}
            <span class="small muted">${escapeHtml(contactSourceText(contact))}</span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderAdvisorContactSection(item) {
  return `
    <div class="info-block contact-block">
      <h3>联系方式</h3>
      ${renderContactRows(item.contacts || [])}
    </div>
  `;
}

function renderReadOnlyContactSection(contacts = []) {
  return `
    <div class="info-block contact-block">
      <h3>联系方式</h3>
      ${renderContactRows(contacts)}
    </div>
  `;
}

function normalizeHighlightItems(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.flatMap(item => normalizeHighlightItems(item));
  }
  if (typeof value === "object") {
    return normalizeHighlightItems(Object.values(value));
  }
  const text = String(value).trim();
  if (!text) return [];
  return text
    .split(/\n|；|;|•|·/)
    .map(item => item.replace(/^[-\d.、\s]+/, "").trim())
    .filter(Boolean);
}

function advisorHighlightItems(item) {
  return normalizeHighlightItems(
    item.advisorHighlights
    || item.advisor_highlights
    || item.highlights
    || item.fitHighlights
    || item.fit_highlights
    || item.keyPoints
    || item.key_points
  ).slice(0, 3);
}

function renderAdvisorHighlights(item) {
  const highlights = advisorHighlightItems(item);
  if (!highlights.length) return `<p>待补充</p>`;
  return `<ul class="highlight-list">${highlights.map(highlight => `<li>${escapeHtml(highlight)}</li>`).join("")}</ul>`;
}

function splitReadableText(value, { minSplitLength = 52 } = {}) {
  const text = String(value || "").trim();
  if (!text) return [];
  const firstPass = text
    .split(/\r?\n+/)
    .map(part => part.trim())
    .filter(Boolean);
  return firstPass.flatMap(part => {
    if (part.length < minSplitLength || /^https?:\/\//i.test(part)) return [part];
    const pieces = part
      .replace(/([。！？!?])\s*/g, "$1\n")
      .replace(/；\s*/g, "；\n")
      .replace(/;\s+(?=[A-Z\\u4e00-\\u9fff])/g, ";\n")
      .split("\n")
      .map(piece => piece.trim())
      .filter(Boolean);
    return pieces.length > 1 ? pieces : [part];
  });
}

function renderInfoLines(lines, emptyText = "未知") {
  const normalized = (Array.isArray(lines) ? lines : [lines])
    .flatMap(line => splitReadableText(line))
    .map(line => String(line || "").trim())
    .filter(Boolean);
  if (!normalized.length) return `<div class="info-lines"><div class="info-line muted">${escapeHtml(emptyText)}</div></div>`;
  return `<div class="info-lines">${normalized.map(line => `<div class="info-line">${escapeHtml(line)}</div>`).join("")}</div>`;
}

function renderInfoBlock(title, lines, emptyText = "未知") {
  return `<div class="info-block"><h3>${escapeHtml(title)}</h3>${renderInfoLines(lines, emptyText)}</div>`;
}

function renderAdvisorMain() {
  $("main").innerHTML = `
    <section class="page work-only-page">
      <div class="advisor-workspace ${state.aiPanelOpen ? "with-ai" : ""}">
        <div class="panel table-wrap" id="advisorListPanel">
          ${renderAdvisorTable()}
        </div>
        <div class="panel detail advisor-detail-panel" id="advisorDetail">
          ${renderAdvisorDetail()}
        </div>
        ${state.aiPanelOpen ? `<div class="panel detail ai-panel"><div class="panel-title"><span>AI助手</span><button class="button" id="closeAiPanel" type="button">关闭</button></div><div class="panel-body">${renderAiConversationPanel()}</div></div>` : ""}
      </div>
    </section>
  `;
  $("main").querySelectorAll("[data-advisor-id]").forEach(row => {
    row.addEventListener("click", () => {
      selectAdvisor(row.dataset.advisorId);
    });
  });
  bindAdvisorListAutoLoad();
  const retryDetail = $("retryAdvisorDetail");
  if (retryDetail && state.selectedAdvisor?.id) {
    retryDetail.addEventListener("click", () => {
      void loadAdvisorDetail(state.selectedAdvisor.id, { useCache: false });
    });
  }
  bindReviewForm();
  bindAiAdvisorActions();
  bindOutreachToggle();
}

function renderAdvisorTable() {
  if (state.advisorLoading && !state.advisors.length) {
    return `<div class="empty advisor-loading-state">正在加载导师清单...</div>`;
  }
  if (!state.advisors.length) return `<div class="empty">当前筛选条件下没有导师。</div>`;
  return `
    <div class="advisor-table-shell">
      <table>
        <thead>
          <tr>
            <th style="width:52px">#</th>
            <th>导师</th>
            <th>学校</th>
            <th>研究池</th>
            <th>阶段</th>
            <th>套磁</th>
          </tr>
        </thead>
        <tbody>
          ${state.advisors.map((item, index) => `
            <tr data-advisor-id="${escapeHtml(item.id)}" class="${state.selectedAdvisor?.id === item.id ? "selected" : ""}">
              <td>${index + 1}</td>
              <td><div class="name-cell">${escapeHtml(item.name)}</div><div class="small muted">${escapeHtml(item.city || "")}${item.city && item.state ? ", " : ""}${escapeHtml(item.state || "")}</div></td>
              <td>${escapeHtml(item.firstInstitution || item.institution || "")}<div class="small muted">${escapeHtml(item.firstInstitutionZh || item.institutionZh || "")}</div></td>
              <td>${escapeHtml(displayFilterLabel("category", item.primaryCategory || ""))}</td>
              <td><span class="badge ${badgeClass(displayFilterLabel("stage", item.stageKey || item.stageLabel || ""))}">${escapeHtml(displayFilterLabel("stage", item.stageKey || item.stageLabel || ""))}</span></td>
              <td><span class="badge ${badgeClass(item.outreachActive ? "已加入" : "未加入")}">${escapeHtml(item.outreachActive ? (item.outreachStatus || "已加入") : "未加入")}</span></td>
            </tr>
          `).join("")}
          ${state.advisorLoadingMore ? `<tr class="table-status-row"><td colspan="6">加载中...</td></tr>` : ""}
          ${!state.advisorHasMore && !state.advisorLoadingMore ? `<tr class="table-status-row"><td colspan="6">已加载完毕</td></tr>` : ""}
        </tbody>
      </table>
    </div>
  `;
}

function renderAdvisorDetail() {
  const item = state.selectedAdvisor;
  if (!item) return `<div class="empty">请选择一位导师。</div>`;
  if (item._detailError) {
    return `
      <div class="panel-title">
        <span>导师详情</span>
      </div>
      <div class="panel-body">
        <div class="detail-heading">
          <div>
            <h2>${escapeHtml(item.name)}</h2>
            <div class="subtle">${escapeHtml(item.firstInstitution || item.institution || "")} / ${escapeHtml(item.firstInstitutionZh || item.institutionZh || "")}</div>
          </div>
        </div>
        <div class="empty">导师详情加载失败：${escapeHtml(item._detailError)}</div>
        <button class="button" id="retryAdvisorDetail" type="button">重新加载</button>
      </div>
    `;
  }
  if (item._detailLoading && state.advisorDetailLoadingId === item.id) {
    return `
      <div class="panel-title">
        <span>导师详情</span>
      </div>
      <div class="panel-body">
        <div class="detail-heading">
          <div>
            <h2>${escapeHtml(item.name)}</h2>
            <div class="subtle">${escapeHtml(item.firstInstitution || item.institution || "")} / ${escapeHtml(item.firstInstitutionZh || item.institutionZh || "")}</div>
          </div>
        </div>
        <div class="detail-grid">
          <div class="info-block loading-block"><h3>研究匹配</h3><p>正在加载导师详情...</p></div>
          <div class="info-block loading-block"><h3>导师看点</h3><p>正在加载导师详情...</p></div>
          <div class="info-block loading-block"><h3>联系方式</h3><p>正在加载导师详情...</p></div>
        </div>
      </div>
    `;
  }
  const links = renderAdvisorLinks(item.links || []);
  const outreachStatus = normalizeOutreachStatus(item.outreachStatus);
  const outreachResponseStatus = normalizeOutreachResponse(item.outreachResponseStatus);
  const outreachStage = normalizeOutreachStage(item.outreachStage);
  const advisorStageLabel = displayFilterLabel("stage", item.stageKey || item.stageLabel || "");
  return `
    <div class="panel-title">
      <span>导师详情</span>
      <div class="toolbar">
        ${state.aiSettings?.available ? `<button class="button" id="advisorAiLookup" type="button">${state.aiBusy ? "打开中..." : "AI助手"}</button>` : ""}
        <button class="button ${item.outreachActive ? "danger" : "primary"}" id="toggleOutreach" type="button">${item.outreachActive ? "取消套磁" : "加入套磁"}</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="detail-heading">
        <div>
          <h2>${escapeHtml(item.name)}</h2>
          <div class="subtle">${escapeHtml(item.firstInstitution || item.institution)} / ${escapeHtml(item.firstInstitutionZh || item.institutionZh || "")}</div>
        </div>
        ${item.outreachActive ? `
          <div class="status-stack align-right">
            <span class="badge ${badgeClass(outreachStatus)}">${escapeHtml(outreachStatus)}</span>
            <span class="badge ${badgeClass(outreachResponseStatus)}">${escapeHtml(outreachResponseStatus)}</span>
            <span class="badge ${badgeClass(outreachStage)}">${escapeHtml(outreachStage)}</span>
          </div>
        ` : ""}
      </div>
      <div class="link-list">${links}</div>
      <div class="detail-grid">
        ${renderInfoBlock("研究证据准入", [
          `${item.researchFitStatus || "未判定"}；证据等级：${item.researchEvidenceLevel || "未判定"}`,
          item.researchFitReason || "",
          ...(item.researchEvidenceSignals || [])
        ], "暂无")}
        ${renderInfoBlock("研究匹配", [displayFilterLabel("category", item.primaryCategory || ""), item.matchedKeywords || ""])}
        ${renderInfoBlock("学校与位置", [item.schoolTierLabel || "", `${item.locationLabelEn || ""} / ${item.locationLabelZh || ""}`])}
        ${renderInfoBlock("导师阶段", [`${advisorStageLabel}；证据等级：${item.stageEvidenceLevel || "低"}`, item.stageEvidence || ""])}
        <div class="info-block"><h3>导师看点</h3>${renderAdvisorHighlights(item)}</div>
        ${renderInfoBlock("招生与指导", [item.phdAdvisingStatus || "未知", item.recruitingStatus || "未知"])}
        ${renderInfoBlock("学生背景", [`${item.studentBackgroundStatus || "未知"}；证据等级：${item.studentBackgroundEvidenceLevel || "低"}`, item.studentBackgroundEvidence || ""])}
        ${renderInfoBlock("证据可靠度", `${item.evidenceReliability || "低"}；检查页面数：${item.evidencePagesChecked || "0"}`)}
        ${renderAdvisorContactSection(item)}
      </div>
      <div style="margin-top:10px">${renderInfoBlock("论文 / 来源证据", item.evidence || [], "暂无")}</div>
      <div class="review-form outreach-form advisor-marker-form">
        <div class="outreach-control-grid advisor-marker-grid">
          ${choiceField("interest", "兴趣标记", advisorInterestOptions, normalizeAdvisorInterest(item.interest) || "待判断", {
            "待判断": "neutral",
            "高兴趣": "green",
            "有兴趣": "amber",
            "不感兴趣": "red"
          }, "待判断")}
          ${choiceField("queryStatus", "查询标记", advisorQueryStatusOptions, normalizeAdvisorQueryStatus(item.queryStatus || item.reviewStatus || "") || "待请求", {
            "待请求": "neutral",
            "请求查询": "amber",
            "已查询": "green"
          }, "待请求")}
        </div>
        <label>备注<textarea id="reviewNote" data-autogrow="true">${escapeHtml(item.note || "")}</textarea></label>
        <div class="toolbar">
          <button class="button primary" id="saveReview">保存</button>
          <span class="save-state note-save-state" id="reviewNoteSaveState">${escapeHtml(noteSavedLabel(item.updatedAt))}</span>
        </div>
      </div>
    </div>
  `;
}

function selectField(id, label, values, current) {
  return `<label>${escapeHtml(label)}<select id="${id}">${values.map(value => `<option value="${escapeHtml(value)}" ${current === value ? "selected" : ""}>${escapeHtml(value || "未设置")}</option>`).join("")}</select></label>`;
}

function choiceDisplayMeta(value) {
  const labels = {
    "待判断": ["待判", "待"],
    "高兴趣": ["高兴", "高"],
    "有兴趣": ["有兴", "有"],
    "不感兴趣": ["不感", "不"],
    "待请求": ["待请", "待"],
    "请求查询": ["请求", "查"],
    "已查询": ["已查", "已"],
    "待联系": ["待联", "待"],
    "已发送": ["已发", "发"],
    "已回复": ["已回", "回"],
    "跟进中": ["跟进", "跟"],
    "已面试": ["面试", "面"],
    "已申请": ["申请", "申"],
    "待回复": ["待回", "待"],
    "积极": ["积极", "积"],
    "中性": ["中性", "中"],
    "拒绝": ["拒绝", "拒"]
  };
  const [shortLabel, tinyLabel] = labels[value] || [value, value.slice(0, 1)];
  return { full: value, short: shortLabel, tiny: tinyLabel };
}

function choiceField(id, label, values, current, colorMap = {}, defaultValue = "") {
  return `
    <div class="choice-field" data-choice-field="${escapeHtml(id)}" data-choice-default="${escapeHtml(defaultValue || "")}">
      <div class="choice-label">${escapeHtml(label)}</div>
      <input type="hidden" id="${escapeHtml(id)}" value="${escapeHtml(current || "")}">
      <div class="choice-button-row">
        ${values.map(value => {
          const color = colorMap[value] || "";
          const display = choiceDisplayMeta(value);
          return `
            <button class="choice-button ${escapeHtml(color)} ${current === value ? "active" : ""}" type="button" data-choice-target="${escapeHtml(id)}" data-choice-value="${escapeHtml(value)}" aria-label="${escapeHtml(value)}" title="${escapeHtml(value)}">
              <span class="choice-button-text" data-full="${escapeHtml(display.full)}" data-short="${escapeHtml(display.short)}" data-tiny="${escapeHtml(display.tiny)}"></span>
            </button>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function setChoiceFieldValue(field, value) {
  const input = field?.querySelector("input[type='hidden']");
  if (input) input.value = value || "";
  field?.querySelectorAll("[data-choice-value]").forEach(option => {
    option.classList.toggle("active", option.dataset.choiceValue === (value || ""));
  });
}

function bindChoiceButtons(root = document, onChange = null) {
  root.querySelectorAll("[data-choice-value]").forEach(button => {
    button.addEventListener("click", async () => {
      const target = button.dataset.choiceTarget || "";
      const input = $(target);
      if (!input) return;
      const value = button.dataset.choiceValue || "";
      const previousValue = input.value || "";
      const field = button.closest("[data-choice-field]");
      if (!field) return;
      const defaultValue = field.dataset.choiceDefault || "";
      const nextValue = input.value === value ? defaultValue : value;
      setChoiceFieldValue(field, nextValue);
      if (!onChange) return;
      try {
        await onChange({ target, value: nextValue, previousValue, field });
      } catch (error) {
        if (input.value === nextValue) {
          setChoiceFieldValue(field, previousValue);
        }
        console.warn("标记保存失败", error);
      }
    });
  });
}

function applyAdvisorReviewState(item, payload, result) {
  const review = result.review || {};
  const reviewState = {
    interest: Object.prototype.hasOwnProperty.call(review, "interest") ? review.interest : (payload.interest ?? item.interest ?? ""),
    queryStatus: Object.prototype.hasOwnProperty.call(review, "queryStatus") ? review.queryStatus : (payload.queryStatus ?? item.queryStatus ?? ""),
    reviewStatus: Object.prototype.hasOwnProperty.call(review, "reviewStatus") ? review.reviewStatus : (payload.queryStatus ?? item.reviewStatus ?? ""),
    note: Object.prototype.hasOwnProperty.call(review, "note") ? review.note : (payload.note ?? item.note ?? ""),
    reviewer: review.reviewer || state.sessionUser || state.reviewer,
    updatedAt: review.updatedAt || result.updatedAt
  };
  Object.assign(item, reviewState);
  if (state.selectedAdvisor?.id === item.id) {
    state.selectedAdvisor = { ...state.selectedAdvisor, ...reviewState };
  }
  state.advisors = state.advisors.map(row => row.id === item.id ? { ...row, ...reviewState } : row);
  cacheAdvisorDetail(item.id, { ...item, ...reviewState });
  if (state.advisorListQueryKey) {
    cacheAdvisorList(state.advisorListQueryKey, {
      offset: 0,
      total: state.advisorTotal,
      hasMore: state.advisorHasMore,
      items: state.advisors
    });
  }
}

function enqueueAdvisorReviewSave(operation) {
  const next = state.reviewSaveQueue.catch(() => {}).then(operation);
  state.reviewSaveQueue = next.catch(() => {});
  return next;
}

async function saveAdvisorReview(item, { fields, values = {} } = {}) {
  const payload = {
    advisorId: item.id,
    fields,
    ...values
  };
  return enqueueAdvisorReviewSave(async () => {
    const result = await api("/api/reviews", { method: "POST", body: JSON.stringify(payload) });
    applyAdvisorReviewState(item, payload, result);
    void refreshAdvisorOptions();
    return result;
  });
}

function bindReviewForm() {
  const item = state.selectedAdvisor;
  const save = $("saveReview");
  if (!item || !save) return;
  bindAutoGrowTextareas($("advisorDetail") || document);
  const noteSaveState = bindDirtySaveState({
    fieldIds: ["reviewNote"],
    stateId: "reviewNoteSaveState",
    savedAt: item.updatedAt || ""
  });
  bindChoiceButtons($("advisorDetail") || document, async ({ target, value }) => {
    await saveAdvisorReview(item, { fields: [target], values: { [target]: value } });
  });
  save.addEventListener("click", async () => {
    try {
      noteSaveState.markSaving();
      const submittedNote = $("reviewNote")?.value || "";
      const result = await saveAdvisorReview(item, { fields: ["note"], values: { note: submittedNote } });
      noteSaveState.markSaved(result.review?.updatedAt || result.updatedAt || new Date(), { reviewNote: submittedNote });
    } catch (error) {
      noteSaveState.markError();
      console.warn("备注保存失败", error);
    }
  });
}

function renderAiConversationPanel() {
  const conversation = state.selectedAiConversation;
  const messages = [...(conversation?.messages || []).filter(message => !isHiddenAiMessage(message))];
  if (state.pendingAiMessage) {
    messages.push(state.pendingAiMessage);
  }
  if (state.aiBusy || state.aiSending) {
    messages.push({
      role: "assistant",
      content: state.aiBusy ? "正在基于当前导师和最新 CV 生成匹配反馈..." : (state.aiSettings?.toolsEnabled ? "正在查询资料并思考..." : "正在思考..."),
      createdAt: new Date().toISOString(),
      pending: true
    });
  }
  if (!conversation) {
    if (messages.length) {
      return `
        <div class="ai-conversation">
          <div class="ai-message-list">
            ${renderAiMessages(messages)}
          </div>
        </div>
      `;
    }
    return `<div class="empty">点击导师详情右上角“AI助手”后，这里会打开绑定该导师的 Chatbot。</div>`;
  }
  const canSend = Boolean(conversation.id) && !state.aiBusy && !state.aiSending;
  const title = normalizeAiConversationTitle(conversation.title || "AI助手");
  return `
    <div class="ai-conversation">
      <div class="ai-chat-meta">${escapeHtml(title)}</div>
      <div class="ai-message-list">
        ${renderAiMessages(messages)}
      </div>
      <form class="ai-input-form" id="aiFollowupForm">
        <div class="ai-composer">
          <textarea id="aiFollowupText" ${canSend ? "" : "disabled"} rows="1" placeholder="问这个导师：套磁切入点、风险、核查网页线索。Enter 发送，Shift+Enter 换行"></textarea>
          <button class="ai-send-button" type="submit" ${canSend ? "" : "disabled"} aria-label="发送">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 19V5"></path>
              <path d="M5 12l7-7 7 7"></path>
            </svg>
          </button>
        </div>
        <span class="save-state" id="aiFollowupState"></span>
      </form>
    </div>
  `;
}

function renderAiMessages(messages) {
  return messages.map(message => {
    const displayMessage = aiDisplayMessage(message);
    return `
    <div class="ai-message ${escapeHtml(message.role)} ${message.pending ? "pending" : ""}">
      <div class="small muted">${escapeHtml(aiMessageAuthorLabel(displayMessage))} · ${escapeHtml(aiMessageTimeLabel(displayMessage))}</div>
      <div class="ai-markdown">${markdownToHtml(displayMessage.content)}${displayMessage.typing ? `<span class="typing-cursor"></span>` : ""}</div>
    </div>
  `;
  }).join("");
}

function aiMessageTimeLabel(message) {
  if (message.pending && message.role === "assistant") return "处理中";
  return formatAiTimestamp(message.createdAt);
}

function aiDisplayMessage(message) {
  const typing = state.aiTyping;
  if (
    typing
    && message.role === "assistant"
    && String(message.id || "") === String(typing.messageId || "")
    && String(message.conversationId || "") === String(typing.conversationId || "")
  ) {
    return { ...message, content: typing.visibleContent, typing: true };
  }
  return message;
}

function aiMessageAuthorLabel(message) {
  if (message.role === "assistant") return message.createdBy || "AI";
  return message.createdBy || state.sessionUser || "用户";
}

function normalizeAiConversationTitle(title) {
  return String(title || "").replace(/^AI 导师助手：/, "AI助手：") || "AI助手";
}

async function loadOrCreateAdvisorAiConversation(advisorId) {
  const list = await api(`/api/ai/conversations?advisorId=${encodeURIComponent(advisorId)}`);
  const reusable = (list.items || []).find(item => {
    const title = String(item.title || "");
    return title.startsWith("AI助手：") || title.startsWith("AI 导师助手：");
  });
  if (reusable?.id) {
    return api(`/api/ai/conversations/${encodeURIComponent(reusable.id)}`);
  }
  const result = await api(`/api/ai/advisors/${encodeURIComponent(advisorId)}/conversations`, {
    method: "POST",
    body: JSON.stringify({})
  });
  return { ...result.conversation, justCreated: true };
}

function renderAiHostMain() {
  if (state.page === "outreach") {
    void renderOutreachMain();
    scheduleAiScrollToBottom();
    return;
  }
  renderAdvisorMain();
  scheduleAiScrollToBottom();
}

function scheduleAiScrollToBottom() {
  window.requestAnimationFrame(() => {
    const list = $("main")?.querySelector(".ai-message-list");
    if (!list) return;
    list.scrollTop = list.scrollHeight;
  });
}

function latestAssistantMessage(conversation) {
  return [...(conversation?.messages || [])].reverse().find(message => message.role === "assistant" && message.content);
}

function startAiTypewriter(conversation) {
  const message = latestAssistantMessage(conversation);
  if (!message?.id || !message.content) return;
  cancelAiTyping();
  const fullContent = String(message.content);
  state.aiTyping = {
    conversationId: message.conversationId || conversation.id,
    messageId: message.id,
    fullContent,
    visibleContent: "",
    index: 0,
    chunkSize: Math.max(10, Math.ceil(fullContent.length / 45)),
    timer: null
  };
  const step = () => {
    const typing = state.aiTyping;
    if (
      !typing
      || String(state.selectedAiConversation?.id || "") !== String(typing.conversationId || "")
      || !state.aiPanelOpen
    ) {
      cancelAiTyping();
      return;
    }
    typing.index = Math.min(typing.fullContent.length, typing.index + typing.chunkSize);
    typing.visibleContent = typing.fullContent.slice(0, typing.index);
    if (typing.index >= typing.fullContent.length) {
      cancelAiTyping();
    }
    renderAiHostMain();
  };
  state.aiTyping.timer = window.setInterval(step, 16);
  step();
}

async function openAdvisorAiConversation(advisorId) {
  cancelAiTyping();
  state.aiPanelOpen = true;
  state.aiBusy = true;
  state.aiSending = false;
  state.pendingAiMessage = null;
  state.selectedAiConversation = null;
  renderAiHostMain();
  try {
    const conversation = await loadOrCreateAdvisorAiConversation(advisorId);
    if (currentAiAdvisorId() === advisorId && state.aiPanelOpen) {
      state.aiBusy = false;
      state.selectedAiConversation = conversation;
      if (conversation.justCreated) {
        startAiTypewriter(conversation);
      }
    }
  } catch (error) {
    if (currentAiAdvisorId() === advisorId && state.aiPanelOpen) {
      state.selectedAiConversation = {
        title: "AI 调用失败",
        messages: [{
          role: "assistant",
          content: `AI 调用失败：${error.message}`,
          createdAt: new Date().toISOString()
        }]
      };
    }
  } finally {
    state.aiBusy = false;
    renderAiHostMain();
  }
}

function bindAiAdvisorActions() {
  const closeButton = $("closeAiPanel");
  if (closeButton) {
    closeButton.addEventListener("click", () => {
      state.aiPanelOpen = false;
      renderAiHostMain();
    });
  }
  const aiButton = $("advisorAiLookup");
  const activeAdvisorId = currentAiAdvisorId();
  if (aiButton && activeAdvisorId) {
    aiButton.addEventListener("click", async () => {
      await openAdvisorAiConversation(activeAdvisorId);
    });
  }
  const followupForm = $("aiFollowupForm");
  if (followupForm && state.selectedAiConversation?.id) {
    const textarea = $("aiFollowupText");
    const fitTextarea = () => {
      if (!textarea) return;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    };
    if (textarea) {
      fitTextarea();
      textarea.addEventListener("input", fitTextarea);
      textarea.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          followupForm.requestSubmit();
        }
      });
    }
    followupForm.addEventListener("submit", async event => {
      event.preventDefault();
      const content = $("aiFollowupText").value.trim();
      if (!content) return;
      const conversationId = state.selectedAiConversation.id;
      const clientCreatedAt = new Date().toISOString();
      $("aiFollowupState").textContent = "发送中...";
      state.aiSending = true;
      state.pendingAiMessage = {
        role: "user",
        content,
        createdBy: state.sessionUser || "",
        createdAt: clientCreatedAt,
        pending: true
      };
      renderAiHostMain();
      try {
      const result = await api(`/api/ai/conversations/${encodeURIComponent(conversationId)}/messages`, {
          method: "POST",
          body: JSON.stringify({ content, clientCreatedAt })
        });
        if (state.selectedAiConversation?.id === conversationId) {
          state.pendingAiMessage = null;
          state.aiSending = false;
          state.selectedAiConversation = result.conversation;
          startAiTypewriter(result.conversation);
          return;
        }
      } catch (error) {
        if (state.selectedAiConversation?.id === conversationId) {
          state.selectedAiConversation.messages = [
            ...(state.selectedAiConversation.messages || []),
            {
              ...state.pendingAiMessage,
              pending: false
            },
            {
              role: "assistant",
              content: `发送失败：${error.message}`,
              createdAt: new Date().toISOString()
            }
          ];
        }
        state.pendingAiMessage = null;
        state.aiSending = false;
        renderAiHostMain();
        return;
      }
      state.pendingAiMessage = null;
      state.aiSending = false;
      renderAiHostMain();
    });
  }
}

function bindOutreachToggle() {
  const item = state.selectedAdvisor;
  const button = $("toggleOutreach");
  if (!item || !button) return;
  button.addEventListener("click", async () => {
    const nextActive = !item.outreachActive;
    if (!nextActive) {
      const ok = window.confirm(`确认把 ${item.name} 从套磁跟踪中移出吗？历史记录会保留，但默认不再显示在套磁清单里。`);
      if (!ok) return;
    }
    button.disabled = true;
    button.textContent = nextActive ? "加入中..." : "取消中...";
    const result = await api("/api/outreach/toggle", {
      method: "POST",
      body: JSON.stringify({ advisorId: item.id, active: nextActive })
    });
    const outreach = result.item || {};
    Object.assign(item, {
      outreachActive: Boolean(outreach.active),
      outreachStatus: outreach.status || "",
      outreachResponseStatus: outreach.responseStatus || "",
      outreachStage: outreach.stage || "",
      outreachNextAction: outreach.nextAction || ""
    });
    state.advisors = state.advisors.map(row => row.id === item.id ? { ...row, ...item } : row);
    cacheAdvisorDetail(item.id, item);
    if (state.advisorListQueryKey) {
      cacheAdvisorList(state.advisorListQueryKey, {
        offset: 0,
        total: state.advisorTotal,
        hasMore: state.advisorHasMore,
        items: state.advisors
      });
    }
    state.focusOutreachAdvisorId = nextActive ? item.id : "";
    if (state.page === "outreach") {
      await loadOutreach();
      return;
    }
    if (state.page === "advisors") {
      renderAdvisorMain();
    }
  });
}

function documentTypeLabel(value) {
  const item = (state.documentTypes || defaultDocumentTypes).find(row => row.value === value)
    || defaultDocumentTypes.find(row => row.value === value);
  return item?.label || value || "文书";
}

function formatFileSize(bytes) {
  const size = Number(bytes || 0);
  if (!size) return "暂无文件";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatTimestamp(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}

function formatAiTimestamp(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function todayDate() {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateInputValue(value, fallback = "") {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];
  if (text) {
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return `${year}-${month}-${day}`;
    }
  }
  return fallback;
}

function formatDateLabel(value) {
  return dateInputValue(value) || value || "未知日期";
}

function fileExtension(name) {
  const match = String(name || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : "";
}

function documentPreviewKind(item) {
  const mime = String(item?.mimeType || "").toLowerCase();
  const ext = fileExtension(item?.originalFilename || "");
  if (!item?.hasFile) return "none";
  if (mime === "application/pdf" || ext === "pdf") return "pdf";
  if (mime.startsWith("image/")) return "image";
  if (mime.includes("wordprocessingml.document") || ["docx", "docm"].includes(ext)) return "docx";
  if (ext === "doc") return "legacy-word";
  if (mime.startsWith("text/") && mime !== "text/html") return "text";
  if (["md", "markdown", "txt", "csv", "json"].includes(ext)) return "text";
  return "unsupported";
}

function renderDocumentUploadPanel() {
  if (!state.uploadOpen) return "";
  const selectedName = state.pendingUploadFile?.name || "还没有选择文件";
  return `
    <div class="panel upload-panel">
      <div class="panel-title">上传文书版本</div>
      <form class="panel-body upload-form" id="documentUploadForm">
        <div class="form-row">
          <label>文书类型
            <select id="uploadDocType">
              ${(state.documentTypes || defaultDocumentTypes).map(item => `
                <option value="${escapeHtml(item.value)}" ${state.selectedDocType === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>
              `).join("")}
            </select>
          </label>
          <label>版本标题
            <input id="uploadTitle" placeholder="不填则使用文件名">
          </label>
        </div>
        <div class="drop-zone" id="documentDropZone">
          <input id="documentFileInput" type="file" hidden>
          <div>
            <strong>拖拽文件到这里</strong>
            <span>或点击选择文件；支持 PDF、Word、Markdown、TXT、图片等文书材料。</span>
            <em id="selectedFileName">${escapeHtml(selectedName)}</em>
          </div>
        </div>
        <label>备注
          <textarea id="uploadNotes" data-autogrow="true" placeholder="例如：导师反馈后版本、申请老师修改版、Applicant 自改版"></textarea>
        </label>
        <div class="toolbar">
          <button class="button primary" type="submit">上传并生成版本</button>
          <button class="button" id="cancelUpload" type="button">取消</button>
          <span class="save-state" id="uploadState"></span>
        </div>
      </form>
    </div>
  `;
}

function renderDocumentRows() {
  if (!state.documents.length) {
    return `<div class="empty">当前文书类型还没有上传版本。</div>`;
  }
  return `
    <div class="doc-list">
      ${state.documents.map(item => `
        <div class="doc-row ${state.selectedDocument?.id === item.id ? "selected" : ""}">
          <div class="doc-main">
            <div class="doc-title-row">
              <strong>${escapeHtml(item.title)}</strong>
              <span class="badge">${escapeHtml(item.versionLabel)}</span>
            </div>
            <div class="doc-file-name">${escapeHtml(item.originalFilename || "暂无文件副本")}</div>
            <div class="doc-meta-line">${escapeHtml(formatTimestamp(item.createdAt))} · ${escapeHtml(item.uploadedBy || item.owner || "未知上传者")} · ${escapeHtml(formatFileSize(item.fileSize))}</div>
            ${item.notes ? `<div class="doc-note">${escapeHtml(item.notes)}</div>` : ""}
          </div>
          <div class="doc-actions">
            <button class="button" data-preview-doc="${escapeHtml(item.id)}" ${item.hasFile ? "" : "disabled"} type="button">预览</button>
            <button class="button danger" data-delete-doc="${escapeHtml(item.id)}" type="button">删除</button>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderDocumentPreview() {
  const item = state.selectedDocument;
  if (!item) {
    return `<div class="empty">选择一个版本后进入预览模式。</div>`;
  }
  const fileUrl = `/api/documents/${encodeURIComponent(item.id)}/file`;
  const previewUrl = `/api/documents/${encodeURIComponent(item.id)}/preview`;
  const previewKind = documentPreviewKind(item);
  let previewBody = "";
  if (!item.hasFile) {
    previewBody = `<div class="empty">这个版本还没有上传文件副本。</div>`;
  } else if (previewKind === "image") {
    previewBody = `<div class="preview-frame image-preview"><img src="${fileUrl}" alt="${escapeHtml(item.title)}"></div>`;
  } else if (previewKind === "pdf") {
    previewBody = `<iframe class="preview-frame" src="${fileUrl}#toolbar=1&navpanes=0" title="${escapeHtml(item.title)}"></iframe>`;
  } else if (previewKind === "docx" || previewKind === "legacy-word") {
    previewBody = `<iframe class="preview-frame word-preview-frame" src="${previewUrl}" title="${escapeHtml(item.title)}" sandbox=""></iframe>`;
  } else if (previewKind === "text") {
    previewBody = `<iframe class="preview-frame" src="${fileUrl}" title="${escapeHtml(item.title)}"></iframe>`;
  } else {
    previewBody = `
      <div class="empty">
        当前文件类型暂不支持内嵌预览。<br>
        <a class="button preview-file-button" href="${fileUrl}" target="_blank" rel="noopener noreferrer">打开或下载文件</a>
      </div>
    `;
  }
  return `
    <div class="preview-head">
      <div>
        <h2>${escapeHtml(item.title)}</h2>
        <div class="subtle">${escapeHtml(documentTypeLabel(item.docType))} · ${escapeHtml(item.versionLabel)} · ${escapeHtml(formatTimestamp(item.createdAt))}</div>
      </div>
      ${item.hasFile ? `<a class="button preview-file-button" href="${fileUrl}" target="_blank" rel="noopener noreferrer">打开文件</a>` : ""}
    </div>
    ${previewBody}
  `;
}

async function renderDocuments() {
  const payload = await api(`/api/documents?type=${encodeURIComponent(state.selectedDocType)}`);
  state.documentTypes = payload.types || defaultDocumentTypes;
  state.documents = payload.items || [];
  if (state.selectedDocument && !state.documents.some(item => item.id === state.selectedDocument.id)) {
    state.selectedDocument = null;
  }
  renderDocumentSidebar();
  $("main").innerHTML = `
    <section class="page work-only-page">
      <div class="documents-workspace">
        <div class="documents-left ${state.uploadOpen ? "" : "no-upload"}">
          ${renderDocumentUploadPanel()}
          <div class="panel document-version-panel">
            <div class="panel-title">${escapeHtml(documentTypeLabel(state.selectedDocType))} 版本</div>
            <div class="panel-body">
              ${renderDocumentRows()}
            </div>
          </div>
        </div>
        <div class="panel document-preview">
          <div class="panel-title">预览模式</div>
          <div class="panel-body preview-body">
            ${renderDocumentPreview()}
          </div>
        </div>
      </div>
    </section>
  `;
  bindDocumentEvents();
}

function updateSelectedFileName() {
  const target = $("selectedFileName");
  if (target) target.textContent = state.pendingUploadFile?.name || "还没有选择文件";
}

function bindDocumentEvents() {
  bindAutoGrowTextareas($("main") || document);
  $("main").querySelectorAll("[data-preview-doc]").forEach(button => {
    button.addEventListener("click", () => {
      const id = Number(button.dataset.previewDoc);
      state.selectedDocument = state.documents.find(item => item.id === id) || null;
      renderDocuments();
    });
  });

  $("main").querySelectorAll("[data-delete-doc]").forEach(button => {
    button.addEventListener("click", async () => {
      const id = Number(button.dataset.deleteDoc);
      const item = state.documents.find(row => row.id === id);
      if (!item) return;
      const ok = window.confirm(`确认删除「${item.title}」${item.versionLabel} 吗？这个操作会删除平台里的上传副本。`);
      if (!ok) return;
      await api(`/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.selectedDocument?.id === id) state.selectedDocument = null;
      await renderDocuments();
    });
  });

  const cancelUpload = $("cancelUpload");
  if (cancelUpload) {
    cancelUpload.addEventListener("click", () => {
      state.uploadOpen = false;
      state.pendingUploadFile = null;
      renderDocuments();
    });
  }

  const dropZone = $("documentDropZone");
  const fileInput = $("documentFileInput");
  if (dropZone && fileInput) {
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
      state.pendingUploadFile = fileInput.files?.[0] || null;
      updateSelectedFileName();
    });
    dropZone.addEventListener("dragover", event => {
      event.preventDefault();
      dropZone.classList.add("dragging");
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("dragging");
    });
    dropZone.addEventListener("drop", event => {
      event.preventDefault();
      dropZone.classList.remove("dragging");
      state.pendingUploadFile = event.dataTransfer.files?.[0] || null;
      updateSelectedFileName();
    });
  }

  const uploadForm = $("documentUploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async event => {
      event.preventDefault();
      const file = state.pendingUploadFile || $("documentFileInput")?.files?.[0];
      if (!file) {
        $("uploadState").textContent = "请先选择一个文件。";
        return;
      }
      $("uploadState").textContent = "上传中...";
      const formData = new FormData();
      formData.append("file", file);
      formData.append("docType", $("uploadDocType").value);
      formData.append("title", $("uploadTitle").value);
      formData.append("notes", $("uploadNotes").value);
      try {
        const result = await api("/api/documents/upload", { method: "POST", body: formData });
        state.selectedDocType = result.item.docType;
        state.selectedDocument = result.item;
        state.uploadOpen = false;
        state.pendingUploadFile = null;
        await renderDocuments();
      } catch (error) {
        $("uploadState").textContent = `上传失败：${error.message}`;
      }
    });
  }
}

function renderPlaceholder(title, description, items) {
  $("main").innerHTML = `
    <section class="page">
      <div class="page-head">
        <div>
          <h1>${escapeHtml(title)}</h1>
          <div class="subtle">${escapeHtml(description)}</div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title">后续模块</div>
        <div class="panel-body">
          <table>
            <tbody>
              ${items.map(item => `<tr><td>${escapeHtml(item)}</td><td class="muted">待接入</td></tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  `;
}

async function renderMain() {
  if (state.page === "dashboard") return renderDashboard();
  if (state.page === "advisors") {
    renderAdvisorMain();
    void ensureAdvisorOptions();
    return loadAdvisors({ renderSidebarPanel: false, append: false, useCache: true });
  }
  if (state.page === "documents") return renderDocuments();
  if (state.page === "programs") return loadPrograms();
  if (state.page === "outreach") {
    if (!state.options) await ensureAdvisorOptions();
    return loadOutreach();
  }
  if (state.page === "settings") return renderSettings();
}

function renderLogin(message = "") {
  document.body.classList.add("login-mode");
  $("topnav").innerHTML = "";
  $("sidebar").innerHTML = "";
  $("main").innerHTML = `
    <section class="login-shell">
      <form class="login-panel" id="loginForm">
        <div>
          <h1>登录申请协作平台</h1>
          <div class="subtle">导师库、人工标记和后续文书版本需要登录后查看。</div>
        </div>
        <label>账号
          <select id="loginUser">
            ${accountNames.map(name => `<option value="${name}">${name}</option>`).join("")}
          </select>
        </label>
        <label>访问密码
          <input id="loginPassword" type="password" autocomplete="current-password" autofocus>
        </label>
        <button class="button primary" type="submit">登录</button>
        <div class="login-message" id="loginMessage">${escapeHtml(message)}</div>
      </form>
    </section>
  `;
  $("loginUser").value = state.reviewer;
  $("loginForm").addEventListener("submit", async event => {
    event.preventDefault();
    const form = $("loginForm");
    const submitButton = form.querySelector("button[type='submit']");
    $("loginMessage").classList.add("info");
    $("loginMessage").textContent = "正在登录...";
    submitButton.disabled = true;
    const reviewer = $("loginUser").value;
    let response;
    try {
      response = await fetch("/api/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user: reviewerLabels[reviewer] || "协作者",
          password: $("loginPassword").value
        })
      });
    } catch (error) {
      $("loginMessage").classList.remove("info");
      $("loginMessage").textContent = `登录失败：${error.message}`;
      submitButton.disabled = false;
      return;
    }
    if (!response.ok) {
      $("loginMessage").classList.remove("info");
      $("loginMessage").textContent = "密码不正确，或当前会话无权限。";
      submitButton.disabled = false;
      return;
    }
    const payload = await response.json();
    state.authenticated = true;
    state.sessionUser = payload.user || "";
    state.reviewer = accountNames.includes(payload.user) ? payload.user : reviewer;
    state.dashboardView = "overview";
    setCurrentPage("dashboard");
    localStorage.setItem("phd-platform-reviewer", state.reviewer);
    await loadAiSettings();
    render();
  });
}

async function logout() {
  await fetch("/api/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" }
  });
  state.authenticated = false;
  state.sessionUser = "";
  state.options = null;
  state.advisors = [];
  state.selectedAdvisor = null;
  state.aiSettings = { enabled: false, available: false, hasApiKey: false };
  state.selectedAiConversation = null;
  state.aiPanelOpen = false;
  aiSettingsLoaded = false;
  renderLogin("已退出登录。");
}

function render() {
  if (!state.authenticated) {
    renderLogin();
    return;
  }
  const leavingLogin = document.body.classList.contains("login-mode") || Boolean($("main").querySelector(".login-shell"));
  document.body.classList.remove("login-mode");
  renderTopNav();
  renderSidebar();
  if (leavingLogin) renderMainLoading(state.page === "dashboard" ? "正在打开总览..." : "正在进入协作平台...");
  renderMain().catch(error => {
    if (error.message === "unauthorized") return;
    $("main").innerHTML = `<div class="panel"><div class="panel-body"><div class="empty">加载失败：${escapeHtml(error.message)}</div></div></div>`;
  });
}

async function boot() {
  try {
    const response = await fetch("/api/session", { credentials: "same-origin" });
    const payload = response.ok ? await response.json() : { authenticated: false };
    state.authenticated = Boolean(payload.authenticated);
    state.sessionUser = payload.user || "";
    if (state.authenticated && accountNames.includes(state.sessionUser)) {
      state.reviewer = state.sessionUser;
      localStorage.setItem("phd-platform-reviewer", state.reviewer);
    }
  } catch {
    state.authenticated = false;
    state.sessionUser = "";
  }
  if (state.authenticated) {
    await loadAiSettings();
    render();
  } else {
    renderLogin();
  }
}

boot();
