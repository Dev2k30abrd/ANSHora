import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { uploadDataset, getAutoInsights, streamAgentResponse } from "../services/api";
import ChartRenderer from "./ChartRenderer";

const SUGGESTED_QUESTIONS = [
  {
    title: "Key insights",
    detail: "What are the most important insights in this dataset?",
  },
  {
    title: "Summary",
    detail: "Give me a summary of this dataset",
  },
  {
    title: "Patterns",
    detail: "What patterns or correlations can you find?",
  },
  {
    title: "Where to start",
    detail: "Which columns should I analyze first?",
  },
];

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      className="copy-button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard unavailable, ignore */
        }
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function ChatInterface({ chat, onMessagesChange, onDatasetUpload }) {
  const [messages, setMessages] = useState(chat?.messages || []);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("Analyzing your data…");
  const [streamingAnswer, setStreamingAnswer] = useState(null);

  const dataset = chat?.dataset || null;

  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  }, [question]);

  const updateMessages = (next) => {
    setMessages(next);
    onMessagesChange(next);
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setLoading(true);
      setErrorMessage("");

      const uploadMessage = {
        role: "system",
        type: "uploading",
        content: `Uploading ${file.name}…`,
      };

      updateMessages([...messages, uploadMessage]);

      const uploadedDataset = await uploadDataset(file);
      onDatasetUpload(uploadedDataset);

      const withoutUploading = messages.filter(
        (m) => m.type !== "uploading"
      );

      const afterConnect = [
        ...withoutUploading,
        {
          role: "system",
          type: "dataset",
          content: `Dataset connected: ${uploadedDataset.filename}`,
        },
      ];

      updateMessages(afterConnect);

      // proactively run a first-look EDA briefing, like a senior analyst would
      try {
        const insights = await getAutoInsights(uploadedDataset.id);

        updateMessages([
          ...afterConnect,
          {
            role: "assistant",
            content: insights.answer,
            analysis: insights.analysis_result,
            isAutoInsight: true,
          },
        ]);
      } catch (insightError) {
        console.error("Auto-insights failed:", insightError);
      }
    } catch (error) {
      console.error(error);
      setErrorMessage(
        error.response?.data?.detail || "Unable to upload the dataset."
      );
      updateMessages(messages.filter((m) => m.type !== "uploading"));
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  };

  const submitQuestion = async (text) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    if (!dataset) {
      setErrorMessage("Upload a dataset before asking a question.");
      return;
    }

    const userMessage = { role: "user", content: trimmed };
    const newMessages = [...messages, userMessage];

    updateMessages(newMessages);
    setQuestion("");
    setLoading(true);
    setErrorMessage("");
    setStatusMessage("Analyzing your data…");
    setStreamingAnswer({ content: "", tool: null, analysis: null });

    let finalContent = "";
    let finalMeta = { tool: null, analysis: null };

    try {
      await streamAgentResponse(trimmed, dataset.id, messages, (event) => {
        if (event.type === "status") {
          setStatusMessage(event.message);
        } else if (event.type === "metadata") {
          finalMeta = { tool: event.tool_used, analysis: event.analysis_result };
          setStreamingAnswer((prev) => ({ ...prev, ...finalMeta }));
        } else if (event.type === "chunk") {
          finalContent += event.content;
          setStreamingAnswer((prev) => ({ ...prev, content: finalContent }));
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      });

      updateMessages([
        ...newMessages,
        {
          role: "assistant",
          content: finalContent,
          tool: finalMeta.tool,
          analysis: finalMeta.analysis,
        },
      ]);
    } catch (error) {
      console.error(error);
      setErrorMessage(
        error.message || "Something went wrong while analyzing your data."
      );
    } finally {
      setLoading(false);
      setStreamingAnswer(null);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    submitQuestion(question);
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="chat-interface">
      {!hasMessages && (
        <div className="chat-welcome">
          <div className="welcome-content">
            <h1>How can I help you analyze your data?</h1>

            {!dataset && (
              <p>Upload a dataset to explore patterns, trends, and insights.</p>
            )}

            {dataset && (
              <div className="dataset-ready-card">
                <div className="dataset-icon">
                  {(dataset.filename?.split(".").pop() || "file").toUpperCase().slice(0, 4)}
                </div>
                <div>
                  <strong>{dataset.filename}</strong>
                  <span>
                    {dataset.summary?.rows ?? "—"} rows ·{" "}
                    {dataset.summary?.columns ?? "—"} columns
                  </span>
                </div>
              </div>
            )}

            {dataset && (
              <div className="suggestion-grid">
                {SUGGESTED_QUESTIONS.map((item) => (
                  <button
                    key={item.title}
                    className="suggestion-button"
                    onClick={() => submitQuestion(item.detail)}
                  >
                    <span>{item.title}</span>
                    <small>{item.detail}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {hasMessages && (
        <div className="messages-container">
          {messages.map((message, index) => {
            if (message.type === "uploading") {
              return (
                <div key={index} className="message-row system">
                  <div className="system-pill">
                    <span className="spinner" />
                    {message.content}
                  </div>
                </div>
              );
            }

            if (message.type === "dataset") {
              return (
                <div key={index} className="message-row system">
                  <div className="system-pill success">
                    <span className="check-icon">✓</span>
                    {message.content}
                  </div>
                </div>
              );
            }

            if (message.role === "user") {
              return (
                <div key={index} className="message-row user">
                  <div className="message-content">
                    <p>{message.content}</p>
                  </div>
                </div>
              );
            }

            return (
              <div key={index} className="message-row assistant">
                <div className="message-content">
                  <div className="assistant-label">DataMind</div>

                  <div className="assistant-answer markdown-body">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>

                  {message.analysis?.chart && (
                    <ChartRenderer chart={message.analysis.chart} />
                  )}

                  {message.tool && (
                    <div className="tool-info">
                      Used <span>{message.tool}</span>
                    </div>
                  )}

                  {message.analysis && (
                    <details className="analysis-details">
                      <summary>View analysis details</summary>
                      <pre>{JSON.stringify(message.analysis, null, 2)}</pre>
                    </details>
                  )}

                  <CopyButton text={message.content} />
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="message-row assistant processing-message">
              <div className="message-content">
                <div className="assistant-label">DataMind</div>

                {streamingAnswer?.content ? (
                  <>
                    <div className="assistant-answer markdown-body">
                      <ReactMarkdown>{streamingAnswer.content}</ReactMarkdown>
                      <span className="stream-cursor" />
                    </div>
                    {streamingAnswer.analysis?.chart && (
                      <ChartRenderer chart={streamingAnswer.analysis.chart} />
                    )}
                  </>
                ) : (
                  <div className="thinking-content">
                    <div className="thinking-dots">
                      <span />
                      <span />
                      <span />
                    </div>
                    {statusMessage}
                  </div>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      <div className="chat-input-wrapper">
        {errorMessage && <div className="message-error">{errorMessage}</div>}

        <form onSubmit={handleSubmit} className="chat-composer">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.tsv,.xlsx,.xls,.json,.parquet"
            hidden
            onChange={handleFileUpload}
          />

          <button
            type="button"
            className="attach-button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            title="Upload dataset"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>

          <textarea
            ref={textareaRef}
            placeholder={
              dataset
                ? "Ask anything about your data…"
                : "Upload a dataset or ask a question…"
            }
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            disabled={loading}
            rows={1}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit(event);
              }
            }}
          />

          <button
            type="submit"
            className="send-button"
            disabled={loading || !question.trim()}
            aria-label="Send message"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </form>

        <p className="input-footer">DataMind can make mistakes. Verify important results.</p>
      </div>
    </div>
  );
}

export default ChatInterface;
