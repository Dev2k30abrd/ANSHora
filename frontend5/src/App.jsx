import { useState } from "react";

import Header from "./components/Header";
import ChatInterface from "./components/ChatInterface";
import DatasetUpload from "./components/DatasetUpload";
import DatasetInfo from "./components/DatasetInfo";

import "./App.css";

const createChat = () => ({
  id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(),
  title: "New conversation",
  messages: [],
  dataset: null,
});

function App() {
  const [chats, setChats] = useState([createChat()]);
  const [activeChatId, setActiveChatId] = useState(chats[0].id);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const activeChat = chats.find((chat) => chat.id === activeChatId) || chats[0];

  const createNewChat = () => {
    const newChat = createChat();
    setChats((previous) => [newChat, ...previous]);
    setActiveChatId(newChat.id);
    setSidebarOpen(false);
  };

  const updateActiveChat = (patch) => {
    setChats((previous) =>
      previous.map((chat) =>
        chat.id === activeChatId ? { ...chat, ...patch } : chat
      )
    );
  };

  const handleMessagesChange = (messages) => {
    const patch = { messages };

    // auto-title the chat from the first user message
    if (activeChat.title === "New conversation") {
      const firstUser = messages.find((m) => m.role === "user");
      if (firstUser) {
        patch.title =
          firstUser.content.length > 42
            ? firstUser.content.slice(0, 42).trimEnd() + "…"
            : firstUser.content;
      }
    }

    updateActiveChat(patch);
  };

  const handleDatasetUpload = (dataset) => {
    updateActiveChat({ dataset });
  };

  return (
    <div className="app-shell">
      <Header
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        sidebarOpen={sidebarOpen}
      />

      <div className="app-layout">
        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="sidebar-content">
            <button className="new-chat-button" onClick={createNewChat}>
              <span className="icon-plus" aria-hidden="true">
                +
              </span>
              New chat
            </button>

            <div className="sidebar-section">
              <p className="sidebar-label">Dataset</p>

              {activeChat.dataset ? (
                <DatasetInfo dataset={activeChat.dataset} />
              ) : (
                <DatasetUpload onUploadSuccess={handleDatasetUpload} compact />
              )}
            </div>

            <div className="sidebar-section history-section">
              <p className="sidebar-label">Recent</p>

              <div className="chat-history">
                {chats.map((chat) => (
                  <button
                    key={chat.id}
                    className={
                      activeChatId === chat.id
                        ? "history-item active"
                        : "history-item"
                    }
                    onClick={() => {
                      setActiveChatId(chat.id);
                      setSidebarOpen(false);
                    }}
                    title={chat.title}
                  >
                    {chat.title}
                  </button>
                ))}
              </div>
            </div>

            <div className="sidebar-footer">
              <span className="status-dot" />
              Connected
            </div>
          </div>
        </aside>

        {sidebarOpen && (
          <div
            className="sidebar-scrim"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <main className="chat-area">
          <ChatInterface
            key={activeChat.id}
            chat={activeChat}
            onMessagesChange={handleMessagesChange}
            onDatasetUpload={handleDatasetUpload}
          />
        </main>
      </div>
    </div>
  );
}

export default App;
