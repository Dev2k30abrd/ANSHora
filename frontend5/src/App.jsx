import { useCallback, useEffect, useMemo, useState } from "react";

import AuthScreen from "./components/AuthScreen";
import ChatInterface from "./components/ChatInterface";
import EmailReportModal from "./components/EmailReportModal";
import Header from "./components/Header";
import LandingScreen from "./components/LandingScreen";
import Sidebar from "./components/Sidebar";
import Modal from "./components/Modal";
import AlertsPanel from "./components/panels/AlertsPanel";
import ConnectorsPanel from "./components/panels/ConnectorsPanel";
import ContextPanel from "./components/panels/ContextPanel";
import DashboardPanel from "./components/panels/DashboardPanel";
import DecisionsPanel from "./components/panels/DecisionsPanel";
import HealthPanel from "./components/panels/HealthPanel";
import InsightsPanel from "./components/panels/InsightsPanel";
import MonitorsPanel from "./components/panels/MonitorsPanel";
import NotificationsPanel from "./components/panels/NotificationsPanel";
import ProfitPanel from "./components/panels/ProfitPanel";
import ReportPanel from "./components/panels/ReportPanel";
import SettingsPanel from "./components/panels/SettingsPanel";
import WorkspacesPanel from "./components/panels/WorkspacesPanel";
import {
  deleteChat, deleteDataset, downloadChatMarkdown, getChat, getDatasetSummary, getGmailStatus, getMe, getNotifications, getPacks,
  getSystemStatus, getToken, listChats, listDatasets, listProjects, logoutUser, renameChat, setDatasetSettings, setToken,
  updateChatDataset,
} from "./services/api";

import "./App.css";

const ANALYZE_ACTIONS = [
  { key: "profit", label: "Profit Impact", title: "Profit Impact — where the money is", Panel: ProfitPanel, wide: true, primary: true },
  { key: "dashboard", label: "Dashboard", title: "Auto Dashboard", Panel: DashboardPanel, wide: true },
  { key: "health", label: "Data Health", title: "Data Health Center", Panel: HealthPanel },
  { key: "insights", label: "Proactive Insights", title: "Proactive Insights", Panel: InsightsPanel },
  { key: "report", label: "Executive Report", title: "Executive Report", Panel: ReportPanel, wide: true },
  { key: "decisions", label: "Decision Log", title: "Decision Log — did it pay off?", Panel: DecisionsPanel },
  { key: "monitors", label: "Monitors", title: "Monitors & scheduled alerts", Panel: MonitorsPanel },
  { key: "context", label: "Business Context", title: "Business Context", Panel: ContextPanel },
  { key: "alerts", label: "Alert Rules", title: "Smart Alerts", Panel: AlertsPanel },
];

function App() {
  const [status, setStatus] = useState(null);
  const [user, setUser] = useState(undefined); // undefined = checking, null = signed out / landing
  const [gmailStatus, setGmailStatus] = useState(null);
  const [packs, setPacks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [dataset, setDataset] = useState(null);
  const [chats, setChats] = useState([]);
  const [chatId, setChatId] = useState(null);
  const [panel, setPanel] = useState(null); // {key, props}
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 900);
  const [unread, setUnread] = useState(0);
  const [bootError, setBootError] = useState("");
  const [emailModalDatasetId, setEmailModalDatasetId] = useState(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem("anshora-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      const incomingToken = url.searchParams.get("token");
      if (incomingToken) {
        setToken(incomingToken);
        // eslint-disable-next-line react-hooks/set-state-in-effect -- check OAuth callback params on mount
        setToast("Signed in successfully!");
        window.history.replaceState({}, document.title, window.location.pathname);
        getMe().then((u) => {
          setUser(u);
          setChatId(null);
          setDataset(null);
        }).catch(() => {});
      } else if (url.searchParams.get("auth_error")) {
        setToast("Sign-in failed: " + url.searchParams.get("auth_error"));
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (url.searchParams.get("gmail") === "connected") {
        setToast("Google OAuth connected successfully! Anshora is ready to deliver verified reports.");
        window.history.replaceState({}, document.title, window.location.pathname);
        getGmailStatus().then(setGmailStatus).catch(() => {});
      } else if (url.searchParams.get("gmail_error")) {
        setToast("Google OAuth Notice: " + url.searchParams.get("gmail_error"));
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("anshora-theme", theme);
  }, [theme]);

  /* ---------- boot: system status + session ---------- */
  useEffect(() => {
    getSystemStatus().then(setStatus).catch(() => setBootError("Cannot reach the backend. Start it and refresh."));
    const storedToken = getToken();
    if (storedToken) {
      getMe().then((u) => {
        // Ephemeral guest sessions must NEVER persist across reload or fresh launch!
        if (u?.is_guest || u?.role === "guest" || u?.email?.startsWith("guest_")) {
          setToken(null);
          setUser(null);
        } else {
          setUser(u);
          // PART 3 & PART 14: open fresh chat on launch/reload rather than auto-restoring
          setChatId(null);
          setDataset(null);
        }
      }).catch(() => { setToken(null); setUser(null); });
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- no stored session: open full-page landing experience
      setUser(null);
    }
    const onLogout = () => {
      setUser(null);
      setDataset(null);
      setDatasets([]);
      setChats([]);
      setChatId(null);
      setGmailStatus(null);
      Object.keys(localStorage).forEach((k) => {
        if (k.startsWith("anshora_active_chat_")) localStorage.removeItem(k);
      });
    };
    window.addEventListener("anshora:logout", onLogout);
    return () => window.removeEventListener("anshora:logout", onLogout);
  }, []);

  /* ---------- load workspace data after sign-in ---------- */
  const isGuest = !user || user?.is_guest || user?.role === "guest" || user?.email?.startsWith("guest_");

  const userId = user?.id;
  useEffect(() => {
    getPacks().then(setPacks).catch(() => {});
    if (!userId || isGuest) return;
    listProjects().then(setProjects).catch(() => {});
    listDatasets().then(setDatasets).catch(() => {});
    listChats().then(setChats).catch(() => {});
    getGmailStatus().then(setGmailStatus).catch(() => {});
  }, [userId, isGuest]);

  useEffect(() => {
    if (!user || isGuest) return;
    const tick = () => getNotifications().then((r) => setUnread(r.unread)).catch(() => {});
    tick();
    const t = setInterval(tick, 60000);
    return () => clearInterval(t);
  }, [user, isGuest]);

  const datasetPackId = dataset?.pack_id;
  const pack = useMemo(() => packs.find((p) => p.id === datasetPackId), [packs, datasetPackId]);
  const currency = user?.workspace?.currency || "₹";
  const numericColumns = dataset?.summary?.column_types?.numeric || [];

  /* ---------- handlers ---------- */
  const refreshChats = useCallback(() => {
    if (!isGuest) {
      listChats().then(setChats).catch(() => {});
    }
  }, [isGuest]);

  const handleChatCreated = useCallback((chat) => {
    setChats((prev) => [chat, ...prev.filter((c) => c.id !== chat.id)]);
    setChatId(chat.id);
  }, []);

  const handleDatasetUpload = (ds) => {
    const row = { id: ds.id, filename: ds.filename, rows: ds.summary?.rows, cols: ds.summary?.columns, pack_id: ds.pack_id };
    setDatasets((prev) => [row, ...prev.filter((d) => d.id !== ds.id)]);
    const dsl = { id: ds.id, filename: ds.filename, pack_id: ds.pack_id, summary: ds.summary };
    setDataset(dsl);
    if (chatId && !isGuest) {
      updateChatDataset(chatId, ds.id).catch(() => {});
    }
  };

  const handleSelectDataset = useCallback(async (d) => {
    try {
      const summary = d.summary || (await getDatasetSummary(d.id));
      const dsl = { id: d.id, filename: summary.filename || d.filename, pack_id: summary.pack_id || d.pack_id, summary, project_id: d.project_id };
      setDataset(dsl);
      if (chatId && !isGuest) {
        updateChatDataset(chatId, d.id).catch(() => {});
      }
    } catch {
      setDataset(null);
    }
  }, [chatId, isGuest]);

  const removeDataset = async (id) => {
    if (!window.confirm("Delete this dataset and its analysis history?")) return;
    await deleteDataset(id).catch(() => {});
    const rest = datasets.filter((d) => d.id !== id);
    setDatasets(rest);
    if (dataset?.id === id) {
      setDataset(null);
    }
  };

  const removeChat = async (id, e) => {
    e.stopPropagation();
    await deleteChat(id).catch(() => {});
    setChats((c) => c.filter((x) => x.id !== id));
    if (chatId === id) {
      setChatId(null);
      setDataset(null);
    }
  };

  const rename = async (c) => {
    const title = window.prompt("Rename chat", c.title);
    if (title && title.trim()) {
      await renameChat(c.id, title.trim()).catch(() => {});
      refreshChats();
    }
  };

  const closeOnMobile = () => {
    if (window.innerWidth <= 900) setSidebarOpen(false);
  };

  const openPanel = (key, props = {}) => {
    setPanel({ key, props });
    closeOnMobile();
  };

  const toggleDuplicates = async () => {
    if (!dataset) return;
    const next = !((dataset.summary?.duplicates_excluded || 0) > 0);
    try {
      await setDatasetSettings(dataset.id, next);
      const summary = await getDatasetSummary(dataset.id);
      setDataset((d) => (d ? { ...d, summary } : d));
    } catch {
      /* keep current view */
    }
  };

  const handleSelectChat = async (id) => {
    setChatId(id);
    closeOnMobile();
    try {
      const res = await getChat(id);
      if (res?.chat?.dataset_id) {
        const summary = await getDatasetSummary(res.chat.dataset_id);
        setDataset({
          id: res.chat.dataset_id,
          filename: summary.filename,
          pack_id: summary.pack_id,
          summary,
          project_id: res.chat.project_id,
        });
      } else {
        setDataset(null);
      }
    } catch {
      setDataset(null);
    }
  };

  const handleNewChat = () => {
    setChatId(null);
    setDataset(null);
    setPanel(null);
    closeOnMobile();
  };

  const logout = async () => {
    await logoutUser().catch(() => {});
    setUser(null);
    setDataset(null);
    setDatasets([]);
    setChats([]);
    setChatId(null);
    setGmailStatus(null);
    Object.keys(localStorage).forEach((k) => {
      if (k.startsWith("anshora_active_chat_")) localStorage.removeItem(k);
    });
  };

  /* ---------- render ---------- */
  if (user === undefined) return <div className="boot">{bootError || "Loading…"}</div>;

  // PART 2: Unauthenticated visitors see the full-page LandingScreen first!
  if (user === null) {
    return (
      <LandingScreen
        status={status}
        onAuthed={(u) => {
          setUser(u);
          setChatId(null);
          setDataset(null);
          setToast("Signed in successfully!");
        }}
        onGuest={(guestUser) => {
          setUser({ ...guestUser, is_guest: true });
          setChatId(null);
          setDataset(null);
          setChats([]);
        }}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      />
    );
  }

  const action = ANALYZE_ACTIONS.find((a) => a.key === panel?.key);
  const activeTitle = chats.find((c) => c.id === chatId)?.title || dataset?.filename || (isGuest ? "Anshora (Guest Session)" : "Anshora");

  return (
    <div className="app-shell">
      <Header
        title={activeTitle}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        sidebarOpen={sidebarOpen}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        unread={unread}
        onBell={() => openPanel("notifications")}
        user={user}
        gmailStatus={gmailStatus}
        onOpenWorkspaces={() => openPanel("workspaces")}
        onOpenSettings={() => openPanel("settings")}
        onSignOut={logout}
        onOpenAuth={() => setAuthModalOpen(true)}
      />

      <div className="app-layout">
        <Sidebar
          open={sidebarOpen}
          user={user}
          datasets={datasets}
          dataset={dataset}
          chats={chats}
          chatId={chatId}
          hasDataset={!!dataset}
          onNewChat={handleNewChat}
          onSelectDataset={handleSelectDataset}
          onDeleteDataset={removeDataset}
          onAddData={() => openPanel("connectors")}
          onToggleDuplicates={toggleDuplicates}
          onOpenTool={openPanel}
          onSelectChat={handleSelectChat}
          onRenameChat={rename}
          onDeleteChat={removeChat}
          onExportChat={() => chatId && downloadChatMarkdown(chatId)}
          onSettings={() => openPanel("settings")}
          onSignOut={logout}
          onOpenWorkspaces={() => openPanel("workspaces")}
          onOpenAuth={() => setAuthModalOpen(true)}
        />

        {sidebarOpen && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}

        <main className="chat-area">
          <ChatInterface
            key={chatId ? `chat-${chatId}` : `new-${dataset?.id || "empty"}`}
            chatId={chatId}
            dataset={dataset}
            pack={pack}
            project={projects.find((p) => p.id === dataset?.project_id)}
            user={user}
            onChatCreated={handleChatCreated}
            onChatsChanged={refreshChats}
            onDatasetUpload={handleDatasetUpload}
            onOpenConnectors={() => openPanel("connectors")}
            onLogDecision={(finding) => openPanel("decisions", { prefill: finding })}
          />
        </main>
      </div>

      {panel?.key === "notifications" && (
        <Modal title="Alerts" onClose={() => setPanel(null)}>
          <NotificationsPanel onRead={() => setUnread(0)} />
        </Modal>
      )}
      {panel?.key === "workspaces" && (
        <Modal title="Workspaces" onClose={() => setPanel(null)} wide>
          <WorkspacesPanel
            user={user}
            onWorkspaceChanged={(u) => {
              setUser(u);
              setDatasets([]);
              setDataset(null);
              setChats([]);
              setChatId(null);
            }}
          />
        </Modal>
      )}
      {panel?.key === "settings" && (
        <Modal title="Settings" onClose={() => setPanel(null)}>
          <SettingsPanel
            user={user}
            packs={packs}
            onWorkspaceUpdated={setUser}
            datasetId={dataset?.id}
          />
        </Modal>
      )}
      {panel?.key === "connectors" && (
        <Modal title="Connect data" onClose={() => setPanel(null)}>
          <ConnectorsPanel
            packs={packs}
            projects={projects}
            onDatasetLoaded={(ds) => {
              handleDatasetUpload(ds);
              setPanel(null);
            }}
          />
        </Modal>
      )}
      {action && (
        <Modal title={action.title} onClose={() => setPanel(null)} wide={action.wide}>
          <action.Panel
            datasetId={dataset?.id}
            dataset={dataset}
            currency={currency}
            numericColumns={numericColumns}
            props={panel?.props}
            onOpenEmailModal={(did) => setEmailModalDatasetId(did)}
          />
        </Modal>
      )}

      {emailModalDatasetId && (
        <EmailReportModal
          datasetId={emailModalDatasetId}
          onClose={() => setEmailModalDatasetId(null)}
        />
      )}

      {authModalOpen && (
        <Modal title="Sign in or create workspace" onClose={() => setAuthModalOpen(false)}>
          <AuthScreen
            status={status}
            onAuthed={(u) => {
              setDataset(null);
              setDatasets([]);
              setChats([]);
              setChatId(null);
              setUser(u);
              setAuthModalOpen(false);
              setToast("Signed in successfully!");
            }}
          />
        </Modal>
      )}

      {toast && (
        <div className="global-toast" onClick={() => setToast("")}>
          <span>{toast}</span>
          <button type="button" className="toast-close">×</button>
        </div>
      )}
    </div>
  );
}

export default App;
