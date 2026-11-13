import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  createChat, errorText, getChat, getProfitImpact, listSamples, loadSample, streamAgentQuery, streamChat, uploadDataset,
} from "../services/api";
import ArtifactPanel from "./ArtifactPanel";
import AssistantMessage from "./AssistantMessage";
import StepsTimeline from "./StepsTimeline";

const GENERIC_STARTERS = [
  { title: "Where am I losing money?", detail: "Where am I losing money, and what should I fix first?" },
  { title: "Why did it change?", detail: "Why did the main metric change in the latest period?" },
  { title: "Dashboard", detail: "Give me a dashboard of the key numbers" },
  { title: "What if?", detail: "What if prices change by 5%? Show the profit impact" },
];

const AUTO_OPEN = ["profit_impact", "dashboard", "sensitivity"];

function ChatInterface({ chatId, dataset, pack, project, user, onChatCreated, onChatsChanged, onDatasetUpload, onLogDecision, onOpenConnectors }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [live, setLive] = useState(null); // streaming state
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [samples, setSamples] = useState([]);
  const [editing, setEditing] = useState(null); // {id, text}
  const [artifact, setArtifact] = useState(null); // {runs, activeId}
  const [dragOver, setDragOver] = useState(false);

  const abortRef = useRef(null);
  const fileRef = useRef(null);
  const textareaRef = useRef(null);
  const endRef = useRef(null);
  const chatIdRef = useRef(chatId);
  const justCreated = useRef(null);
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const isGuest = !user || user?.is_guest || user?.role === "guest" || user?.email?.startsWith("guest_");
  const busy = !!live;

  /* ---------- load history from the server ---------- */
  useEffect(() => {
    chatIdRef.current = chatId;
    if (chatId && justCreated.current === chatId) {
      justCreated.current = null; // created mid-run: keep the live state, don't reload
      return;
    }
    setArtifact(null);
    setError("");
    if (!chatId || isGuest) {
      if (!isGuest || !chatId) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- reset UI when switching to a blank chat
        setMessages([]);
      }
      return;
    }
    let off = false;
    getChat(chatId)
      .then((r) => !off && setMessages(r.messages))
      .catch((e) => !off && setError(errorText(e)));
    return () => {
      off = true;
    };
  }, [chatId, isGuest]);

  /* ---------- welcome: money snapshot (deterministic, no LLM) ---------- */
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale snapshot while the new one loads
    setSnapshot(null);
    if (!dataset?.id) return;
    let off = false;
    getProfitImpact(dataset.id).then((d) => !off && setSnapshot(d)).catch(() => {});
    return () => {
      off = true;
    };
  }, [dataset?.id, dataset?.summary?.duplicates_excluded]);

  useEffect(() => {
    if (!dataset) listSamples().then(setSamples).catch(() => {});
  }, [dataset]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, live?.text, live?.steps?.length]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  }, [question]);

  useEffect(() => () => abortRef.current?.abort(), []);

  /* ---------- run the agent ---------- */
  const run = useCallback(
    async (body, { optimisticUser } = {}) => {
      let activeDs = dataset;
      if (!activeDs) {
        if (samples && samples.length > 0) {
          try {
            setUploading(true);
            const loaded = await loadSample(samples[0].name);
            onDatasetUpload(loaded);
            activeDs = loaded;
          } catch (e) {
            setError("Upload or connect a dataset first: " + errorText(e));
            return;
          } finally {
            setUploading(false);
          }
        } else {
          setError("Upload or connect a dataset first.");
          return;
        }
      }
      setError("");
      let cid = chatIdRef.current;
      if (!isGuest) {
        try {
          if (!cid) {
            const chat = await createChat(activeDs.id, activeDs.project_id || project?.id);
            cid = chat.id;
            chatIdRef.current = cid;
            justCreated.current = cid;
            onChatCreated(chat);
          }
        } catch (e) {
          setError(errorText(e));
          return;
        }
      }

      if (optimisticUser) setMessages((m) => [...m, { id: `tmp-${Date.now()}`, role: "user", content: optimisticUser, meta: {} }]);

      const state = { steps: [], runs: [], text: "", thinking: "", status: "Reading your data…", pendingThought: "" };
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLive({ ...state });
      const push = () => setLive({ ...state, steps: [...state.steps] });
      let finished = false;

      try {
        const streamRunner = isGuest
          ? (onEvent, sig) =>
              streamAgentQuery(
                {
                  question: body.question,
                  dataset_id: activeDs.id,
                  history: messagesRef.current.map((m) => ({ role: m.role, content: m.content })),
                  pending_action: body.pending_action,
                },
                onEvent,
                sig
              )
          : (onEvent, sig) => streamChat(cid, body, onEvent, sig);

        await streamRunner(
          (ev) => {
            switch (ev.type) {
              case "meta":
                break;
              case "status":
                state.status = ev.message;
                break;
              case "thinking":
                state.thinking += ev.text;
                break;
              case "thought":
                state.pendingThought = ev.text;
                break;
              case "chunk":
                state.text += ev.text;
                break;
              case "retract":
                state.text = "";
                break;
              case "tool_start":
                state.steps.push({ id: ev.id, name: ev.name, arguments: ev.arguments, status: "running", thought: state.pendingThought });
                state.pendingThought = "";
                break;
              case "tool_result": {
                const s = state.steps.find((x) => x.id === ev.id);
                if (s) Object.assign(s, { status: ev.ok ? "ok" : "error", summary: ev.summary, ms: ev.ms });
                state.runs.push(ev);
                break;
              }
              case "done": {
                finished = true;
                const msg = {
                  id: ev.message_id || `a-${Date.now()}`, role: "assistant", content: ev.answer,
                  meta: {
                    tool_runs: ev.tool_runs,
                    verification: ev.verification,
                    confidence: ev.confidence,
                    followups: ev.followups,
                    demo: ev.demo,
                    pending_action: ev.pending_action,
                    email_preview: ev.email_preview,
                  },
                };
                setMessages((m) => [...m, msg]);
                const open = ev.tool_runs.filter((r) => r.ok && AUTO_OPEN.includes(r.artifact_kind));
                if (open.length) setArtifact({ runs: ev.tool_runs, activeId: open[open.length - 1].id });
                break;
              }
              case "error":
                throw new Error(ev.message);
              default:
            }
            push();
          },
          ctrl.signal
        );
      } catch (e) {
        if (e.name === "AbortError") {
          if (state.text.trim()) setMessages((m) => [...m, { id: `s-${Date.now()}`, role: "assistant", content: state.text, meta: { stopped: true } }]);
          finished = true;
        } else {
          setError(e.message || "Something went wrong while analyzing your data.");
        }
      } finally {
        setLive(null);
        abortRef.current = null;
        onChatsChanged();
        if (!finished && cid) {
          // keep UI consistent with what the server persisted
          getChat(cid).then((r) => setMessages(r.messages)).catch(() => {});
        }
      }
    },
    [dataset, project, isGuest, onChatCreated, onChatsChanged, samples, onDatasetUpload]
  );

  const send = (text) => {
    const t = (text ?? question).trim();
    if (!t || busy) return;
    setQuestion("");
    run({ question: t }, { optimisticUser: t });
  };

  const stop = () => abortRef.current?.abort();

  const regenerate = () => {
    if (busy) return;
    setMessages((m) => {
      const copy = [...m];
      while (copy.length && copy[copy.length - 1].role === "assistant") copy.pop();
      return copy;
    });
    run({ regenerate: true });
  };

  const saveEdit = () => {
    if (!editing?.text.trim() || busy) return;
    const idx = messages.findIndex((m) => m.id === editing.id);
    if (idx < 0) return;
    const text = editing.text.trim();
    setMessages(messages.slice(0, idx));
    setEditing(null);
    run({ question: text, edit_message_id: editing.id }, { optimisticUser: text });
  };

  /* ---------- upload ---------- */
  const doUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      onDatasetUpload(await uploadDataset(file, { projectId: project?.id }));
    } catch (e) {
      setError(errorText(e, "Unable to upload the dataset."));
    } finally {
      setUploading(false);
    }
  };

  const loadSampleData = async (name) => {
    setUploading(true);
    try {
      onDatasetUpload(await loadSample(name));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setUploading(false);
    }
  };

  const openArtifact = (messageRuns, id) => setArtifact({ runs: messageRuns, activeId: id });

  const hasMessages = messages.length > 0 || busy;
  const starters = pack?.starter_questions?.length
    ? pack.starter_questions.slice(0, 4).map((q) => ({ title: q, detail: q }))
    : GENERIC_STARTERS;
  const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf("assistant");
  const topFindings = (snapshot?.findings || []).filter((f) => f.counts_toward_total).slice(0, 3);

  return (
    <div
      className={`chat-layout ${artifact ? "with-artifact" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); doUpload(e.dataTransfer.files?.[0]); }}
    >
      <div className="chat-interface">
        {dragOver && <div className="drop-overlay">Drop a data file to analyze it</div>}

        {!hasMessages && (
          <div className="chat-welcome">
            <div className="welcome-content">
              <div className="welcome-mark" aria-hidden="true" />
              <h1>{dataset ? "What would you like to know?" : "Bring your data. Find the money."}</h1>

              {!dataset && (
                <>
                  <p>Upload a file, connect a database, or try sample data. Every answer comes with its proof and its price tag.</p>
                  <div className="welcome-actions">
                    <button className="upload-button big" onClick={() => fileRef.current?.click()} disabled={uploading}>
                      {uploading ? <span className="spinner" /> : "Upload CSV / Excel / JSON / Parquet"}
                    </button>
                    <button className="ghost-button" onClick={onOpenConnectors}>Connect URL or database</button>
                  </div>
                  {samples.length > 0 && (
                    <div className="sample-row">
                      <span>or try:</span>
                      {samples.map((s) => (
                        <button key={s.name} className="followup" onClick={() => loadSampleData(s.name)} disabled={uploading}>{s.name}</button>
                      ))}
                    </div>
                  )}
                </>
              )}

              {dataset && (
                <>
                  {pack && <p className="welcome-sub">{pack.icon} {pack.name} · {dataset.summary?.rows ?? "—"} rows</p>}

                  {snapshot && snapshot.mode !== "none" && (
                    <div className="snapshot">
                      <div className="snapshot-head">
                        <span>Money snapshot</span>
                        <b>{snapshot.total_at_stake_formatted} at stake</b>
                      </div>
                      {topFindings.map((f) => (
                        <button key={f.id} className="snapshot-item" onClick={() => send(`Tell me more about: ${f.title}. What should we do?`)}>
                          <span>{f.title}</span>
                          <b>{f.impact_formatted}</b>
                        </button>
                      ))}
                      {topFindings.length === 0 && <small>No material money-impacting findings detected.</small>}
                    </div>
                  )}

                  <div className="suggestion-pills">
                    {starters.map((item) => (
                      <button key={item.title} className="pill-button" onClick={() => send(item.detail)}>
                        {item.title}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {hasMessages && (
          <div className="messages-container">
            {messages.map((m, i) => {
              if (m.role === "user") {
                if (editing?.id === m.id) {
                  return (
                    <div key={m.id} className="message-row user">
                      <div className="message-content edit-box">
                        <textarea value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} rows={3} autoFocus />
                        <div className="edit-actions">
                          <button className="mini-btn" onClick={() => setEditing(null)}>Cancel</button>
                          <button className="upload-button" onClick={saveEdit}>Save & rerun</button>
                        </div>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={m.id} className="message-row user">
                    <div className="message-content">
                      <p>{m.content}</p>
                      {!busy && !String(m.id).startsWith("tmp-") && (
                        <button className="msg-edit" onClick={() => setEditing({ id: m.id, text: m.content })} title="Edit and rerun">✎</button>
                      )}
                    </div>
                  </div>
                );
              }
              return (
                <AssistantMessage
                  key={m.id}
                  message={m}
                  isLast={i === lastAssistantIdx && !busy}
                  onFollowup={send}
                  onRegenerate={regenerate}
                  onOpenArtifact={(id) => openArtifact(m.meta?.tool_runs || [], id)}
                />
              );
            })}

            {live && (
              <div className="message-row assistant processing-message">
                <div className="message-content">
                  <StepsTimeline steps={live.steps} thinking={live.thinking} live />
                  {live.text ? (
                    <div className="assistant-answer markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{live.text}</ReactMarkdown>
                      <span className="stream-cursor" />
                    </div>
                  ) : (
                    <div className="thinking-content">
                      <div className="thinking-dots"><span /><span /><span /></div>
                      {live.status}
                    </div>
                  )}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}

        <div className="chat-input-wrapper">
          {error && (
            <div className="message-error chat-error-alert">
              <span className="error-text">⚠️ {error}</span>
              <div className="error-actions">
                <button
                  type="button"
                  className="btn-error-retry"
                  onClick={() => {
                    setError("");
                    regenerate();
                  }}
                >
                  🔄 Retry
                </button>
                <button
                  type="button"
                  className="btn-error-dismiss"
                  onClick={() => setError("")}
                  title="Dismiss error"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="chat-composer">
            <input ref={fileRef} type="file" accept=".csv,.tsv,.xlsx,.xls,.json,.parquet" hidden onChange={(e) => { doUpload(e.target.files?.[0]); e.target.value = ""; }} />
            <button type="button" className="attach-button" onClick={() => fileRef.current?.click()} disabled={busy || uploading} title="Upload dataset">
              {uploading ? <span className="spinner small" /> : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
              )}
            </button>

            <textarea
              ref={textareaRef}
              placeholder={dataset ? "Ask anything about your data" : "Ask anything about your business or try sample data"}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={1}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />

            {busy ? (
              <button type="button" className="send-button stop" onClick={stop} aria-label="Stop generating" title="Stop">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2" /></svg>
              </button>
            ) : (
              <button type="submit" className="send-button" disabled={!question.trim()} aria-label="Send message">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            )}
          </form>
          <p className="input-footer">Anshora checks every figure against your data, but can still make mistakes.</p>
        </div>
      </div>

      {artifact && (
        <ArtifactPanel
          runs={artifact.runs}
          activeId={artifact.activeId}
          onSelect={(id) => setArtifact({ ...artifact, activeId: id })}
          onClose={() => setArtifact(null)}
          onLogDecision={onLogDecision}
        />
      )}
    </div>
  );
}

export default ChatInterface;
