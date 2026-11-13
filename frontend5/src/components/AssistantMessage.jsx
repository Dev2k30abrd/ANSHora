import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import ChartRenderer from "./ChartRenderer";
import ConversationalEmailPreviewCard from "./ConversationalEmailPreviewCard";
import StepsTimeline from "./StepsTimeline";
import VerificationBadge from "./VerificationBadge";

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="msg-action"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

const OPENABLE = ["profit_impact", "dashboard", "sensitivity", "table"];

function AssistantMessage({ message, isLast, onFollowup, onRegenerate, onOpenArtifact, live }) {
  const meta = message.meta || {};
  const runs = meta.tool_runs || [];
  const steps = runs.map((r) => ({
    id: r.id, name: r.name, arguments: r.arguments, status: r.ok ? "ok" : "error", summary: r.summary, ms: r.ms,
  }));
  const artifacts = runs.filter((r) => r.ok && OPENABLE.includes(r.artifact_kind));
  const inlineCharts = runs.filter((r) => r.ok && !OPENABLE.includes(r.artifact_kind)).flatMap((r) => r.charts || []).slice(0, 2);
  const emailPreview = meta.email_preview || runs.find((r) => r.name === "prepare_email_delivery" && r.ok)?.result;

  return (
    <div className="message-row assistant">
      <div className="message-content">
        <StepsTimeline steps={steps} onOpenArtifact={onOpenArtifact} />

        <div className="assistant-answer markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || ""}</ReactMarkdown>
        </div>

        {emailPreview && (
          <ConversationalEmailPreviewCard preview={emailPreview} />
        )}

        {artifacts.length > 0 && (
          <div className="artifact-cards">
            {artifacts.map((a) => (
              <button key={a.id} type="button" className="artifact-card" onClick={() => onOpenArtifact(a.id)}>
                <span className="artifact-card-icon">{a.artifact_kind === "profit_impact" ? "₹" : a.artifact_kind === "table" ? "▦" : a.artifact_kind === "dashboard" ? "◧" : "◇"}</span>
                <span>
                  <b>{{ profit_impact: "Profit impact", dashboard: "Dashboard", sensitivity: "Sensitivity grid", table: "Result table" }[a.artifact_kind]}</b>
                  <small>{a.summary}</small>
                </span>
                <span className="artifact-card-open">Open ›</span>
              </button>
            ))}
          </div>
        )}

        {inlineCharts.map((c, i) => (
          <ChartRenderer key={i} chart={c} />
        ))}

        {!live && (
          <>
            <div className="msg-footer">
              <VerificationBadge verification={meta.verification} confidence={meta.confidence} />
              <div className="msg-actions">
                <CopyButton text={message.content || ""} />
                {isLast && (
                  <button type="button" className="msg-action" onClick={onRegenerate}>
                    Regenerate
                  </button>
                )}
                {meta.demo && <span className="demo-tag">demo analyst</span>}
                {meta.stopped && <span className="demo-tag">stopped</span>}
              </div>
            </div>
            {isLast && meta.followups?.length > 0 && (
              <div className="followups">
                {meta.followups.map((q) => (
                  <button key={q} type="button" className="followup" onClick={() => onFollowup(q)}>
                    {q}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default AssistantMessage;
