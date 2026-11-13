import axios from "axios";

export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "anshora-token";

let guestSessionToken = null;
export const getGuestToken = () => guestSessionToken;
export const setGuestToken = (t) => {
  guestSessionToken = t;
};

export const getToken = () => guestSessionToken || localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => {
  if (t) {
    guestSessionToken = null;
    localStorage.setItem(TOKEN_KEY, t);
  } else {
    guestSessionToken = null;
    localStorage.removeItem(TOKEN_KEY);
  }
};

const api = axios.create({ baseURL: API_URL, timeout: 120000 });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401 && getToken()) {
      setToken(null);
      window.dispatchEvent(new Event("anshora:logout"));
    }
    return Promise.reject(error);
  }
);

export const errorText = (error, fallback = "Something went wrong.") =>
  error?.response?.data?.detail || error?.message || fallback;

const get = async (url, params) => (await api.get(url, { params })).data;
const post = async (url, body, params) => (await api.post(url, body, { params })).data;
const patch = async (url, body) => (await api.patch(url, body)).data;
const del = async (url) => (await api.delete(url)).data;

/* ---------------- system / auth ---------------- */
export const getSystemStatus = () => get("/api/system/status");
export const getPacks = async () => (await get("/api/packs")).packs;
export const register = (body) => post("/api/auth/register", body);
export const login = (body) => post("/api/auth/login", body);
export const loginGuest = () => post("/api/auth/guest");
export const getGoogleAuthUrl = (returnTo, includeGmail = true) =>
  get("/api/auth/google/authorize", { return_to: returnTo, include_gmail: includeGmail });
export const logoutUser = async () => {
  try {
    await post("/api/auth/logout");
  } catch {
    /* ignore */
  } finally {
    setToken(null);
    setGuestToken(null);
    window.dispatchEvent(new Event("anshora:logout"));
  }
};
export const getMe = async () => (await get("/api/auth/me")).user;
export const updateWorkspace = async (body) => (await patch("/api/auth/workspace", body)).user;

/* ---------------- workspaces ---------------- */
export const listWorkspaces = async () => (await get("/api/workspaces")).workspaces;
export const createWorkspace = async (body) => (await post("/api/workspaces", body)).workspace;
export const getWorkspace = (id) => get(`/api/workspaces/${id}`);
export const updateWorkspaceById = async (id, body) => (await patch(`/api/workspaces/${id}`, body)).workspace;
export const switchWorkspace = (id) => post(`/api/workspaces/${id}/switch`);
export const deleteWorkspace = (id) => del(`/api/workspaces/${id}`);

/* ---------------- datasets ---------------- */
const withId = (d) => ({ ...d, id: d.dataset_id });

const ensureSession = async () => {
  if (!getToken()) {
    try {
      const g = await post("/api/auth/guest");
      setGuestToken(g.token);
    } catch {
      /* ignore */
    }
  }
};

export const uploadDataset = async (file, { projectId, packId } = {}) => {
  await ensureSession();
  const fd = new FormData();
  fd.append("file", file);
  if (projectId) fd.append("project_id", projectId);
  if (packId) fd.append("pack_id", packId);
  const r = await api.post("/api/dataset/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
  return withId(r.data);
};
export const importUrl = async (url, projectId) => {
  await ensureSession();
  return withId(await post("/api/dataset/import-url", { url, project_id: projectId }));
};
export const importSql = async (body) => {
  await ensureSession();
  return withId(await post("/api/dataset/import-sql", body));
};
export const listSamples = async () => (await get("/api/dataset/samples")).samples;
export const loadSample = async (name) => {
  await ensureSession();
  return withId(await post(`/api/dataset/sample/${encodeURIComponent(name)}`));
};
export const listDatasets = async () => (await get("/api/dataset/")).datasets;
export const getDatasetSummary = (id) => get(`/api/dataset/${id}/summary`);
export const deleteDataset = (id) => del(`/api/dataset/${id}`);
export const setDatasetPack = (id, packId) => patch(`/api/dataset/${id}/pack`, { pack_id: packId });
export const setDatasetSettings = (id, excludeDuplicates) => patch(`/api/dataset/${id}/settings`, { exclude_duplicates: excludeDuplicates });
export const getAutoInsights = (id) => get(`/api/dataset/${id}/insights`);

/* ---------------- chats (server-side history) ---------------- */
export const listChats = async (datasetId, projectId) => (await get("/api/chats", { dataset_id: datasetId, project_id: projectId })).chats;
export const searchChats = async (q) => (await get("/api/chats/search", { q })).chats;
export const createChat = async (datasetId, projectId) => (await post("/api/chats", { dataset_id: datasetId, project_id: projectId })).chat;
export const getChat = (id) => get(`/api/chats/${id}`);
export const renameChat = (id, title) => patch(`/api/chats/${id}`, { title });
export const updateChat = (id, body) => patch(`/api/chats/${id}`, body);
export const updateChatDataset = (id, datasetId) => patch(`/api/chats/${id}`, { dataset_id: datasetId });
export const deleteChat = (id) => del(`/api/chats/${id}`);

/** Stream an agent run. Pass an AbortSignal to support the Stop button. */
export const streamChat = async (chatId, body, onEvent, signal) => {
  const response = await fetch(`${API_URL}/api/chats/${chatId}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(body),
    signal,
  });
  if (response.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("anshora:logout"));
  }
  if (!response.ok) {
    let detail = "Failed to start analysis.";
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(part.slice(6)));
      } catch (e) {
        console.error("Stream parse error", e);
      }
    }
  }
};

/** Stream stateless agent run (used for guest sessions, zero persistence). */
export const streamAgentQuery = async (body, onEvent, signal) => {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}/api/agent/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let detail = "Failed to start analysis.";
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      try {
        onEvent(JSON.parse(part.slice(6)));
      } catch (e) {
        console.error("Stream parse error", e);
      }
    }
  }
};

/* ---------------- projects ---------------- */
export const listProjects = async () => (await get("/api/projects")).projects;
export const createProject = async (body) => (await post("/api/projects", body)).project;
export const updateProject = async (id, body) => (await api.put(`/api/projects/${id}`, body)).data.project;
export const deleteProject = (id) => del(`/api/projects/${id}`);

/* ---------------- profit impact / decisions / monitors ---------------- */
export const getProfitImpact = (id) => get(`/api/profit/${id}`);
export const runSensitivity = (id, body) => post(`/api/profit/${id}/sensitivity`, body);

export const listDecisions = async (datasetId) => (await get("/api/decisions", { dataset_id: datasetId })).decisions;
export const getDecisionSummary = () => get("/api/decisions/summary");
export const createDecision = async (body) => (await post("/api/decisions", body)).decision;
export const createDecisionFromFinding = async (datasetId, finding) => (await post("/api/decisions/from-finding", { dataset_id: datasetId, finding })).decision;
export const evaluateDecision = async (id) => (await post(`/api/decisions/${id}/evaluate`)).decision;
export const recordDecisionOutcome = async (id, body) => (await post(`/api/decisions/${id}/outcome`, body)).decision;
export const setDecisionStatus = async (id, status) => (await patch(`/api/decisions/${id}`, { status })).decision;
export const deleteDecision = (id) => del(`/api/decisions/${id}`);

/* ---------------- reports (persistent) ---------------- */
export const listReports = async (datasetId) => (await get("/api/reports", { dataset_id: datasetId })).reports;
export const getReport = (id) => get(`/api/reports/${id}`);
export const deleteReport = (id) => del(`/api/reports/${id}`);

/* ---------------- business memory ---------------- */
export const listMemories = async () => (await get("/api/memory")).memories;
export const searchMemories = async (q) => (await get("/api/memory/search", { q })).memories;
export const addMemory = (body) => post("/api/memory", body);
export const deleteMemory = (id) => del(`/api/memory/${id}`);

/* ---------------- Gmail Delivery & Google OAuth ---------------- */
export const getGmailStatus = () => get("/api/gmail/status");
export const authorizeGmail = (returnTo) => get("/api/gmail/oauth/authorize", { return_to: returnTo });
export const disconnectGmail = () => post("/api/gmail/disconnect");
export const previewReportEmail = (body) => post("/api/gmail/preview", body);
export const sendReportEmail = (body) => post("/api/gmail/send", body);
export const listEmailDeliveries = () => get("/api/gmail/deliveries");

export const listMonitors = async (datasetId) => (await get("/api/monitors", { dataset_id: datasetId })).monitors;
export const createMonitor = async (body) => (await post("/api/monitors", body)).monitor;
export const toggleMonitor = async (id) => (await patch(`/api/monitors/${id}/toggle`)).monitor;
export const runMonitor = (id) => post(`/api/monitors/${id}/run`);
export const deleteMonitor = (id) => del(`/api/monitors/${id}`);
export const getNotifications = () => get("/api/monitors/notifications/list");
export const markAllNotificationsRead = () => post("/api/monitors/notifications/read-all");

/* ---------------- export (authenticated blob download) ---------------- */
export const downloadExport = async (datasetId, format) => {
  const r = await api.get(`/api/export/${datasetId}`, { params: { format }, responseType: "blob", timeout: 180000 });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `profit-report.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
};
export const downloadChatMarkdown = async (chatId) => {
  const r = await api.get(`/api/chats/${chatId}/export`, { responseType: "blob" });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `chat-${chatId.slice(0, 8)}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
};

/* ---------------- existing analysis features (unchanged endpoints) ---------------- */
export const getAutoDashboard = (id, refresh = false) => get(`/api/dashboard/${id}/auto`, { refresh });
export const getProactiveInsights = (id, refresh = false) => get(`/api/insights/${id}/proactive`, { refresh });
export const analyzeRootCause = (datasetId, metricColumn, dateColumn, dimensions) =>
  post("/api/root-cause/analyze", { dataset_id: datasetId, metric_column: metricColumn, date_column: dateColumn, dimensions });
export const runForecast = (datasetId, dateColumn, valueColumn, periods = 6, freq = "M") =>
  post("/api/forecast/analyze", { dataset_id: datasetId, date_column: dateColumn, value_column: valueColumn, periods, freq });
export const runWhatIf = (datasetId, params) => post("/api/whatif/simulate", { dataset_id: datasetId, ...params });
export const getDataHealth = (id, refresh = false) => get(`/api/data-health/${id}`, { refresh });
export const generateExecutiveReport = (id, refresh = false) => post(`/api/reports/${id}/executive`, null, { refresh });

export const listAlertRules = async (id) => (await get(`/api/alerts/${id}/rules`)).rules;
export const createAlertRule = (id, rule) => post(`/api/alerts/${id}/rules`, rule);
export const deleteAlertRule = (id, ruleId) => del(`/api/alerts/${id}/rules/${ruleId}`);
export const evaluateAlerts = (id) => post(`/api/alerts/${id}/evaluate`);
export const getAlertHistory = async (id) => (await get(`/api/alerts/${id}/history`)).history;

export const getBusinessContext = (id) => get(`/api/business-context/${id}`);
export const addMetric = (id, metric) => post(`/api/business-context/${id}/metrics`, metric);
export const deleteMetric = (id, name) => del(`/api/business-context/${id}/metrics/${name}`);
export const addSynonym = (id, alias, canonical) => post(`/api/business-context/${id}/synonyms`, { alias, canonical });
export const deleteSynonym = (id, alias) => del(`/api/business-context/${id}/synonyms/${alias}`);
export const addBusinessRule = (id, rule) => post(`/api/business-context/${id}/rules`, { rule });
export const deleteBusinessRule = (id, index) => del(`/api/business-context/${id}/rules/${index}`);
