import { useState } from "react";

import { toolLabel } from "../utils/toolLabels";

function Args({ step }) {
  const a = step.arguments || {};
  if (step.name === "sql_query" && a.query) return <pre className="step-code">{a.query}</pre>;
  if (step.name === "python_analysis" && a.code) return <pre className="step-code">{a.code}</pre>;
  const entries = Object.entries(a).filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && !v.length));
  if (!entries.length) return null;
  return (
    <div className="step-args">
      {entries.map(([k, v]) => (
        <span key={k} className="step-chip">
          {k.replace(/_/g, " ")}: <b>{Array.isArray(v) ? v.join(", ") : String(v)}</b>
        </span>
      ))}
    </div>
  );
}

/** steps: [{id, name, arguments, status: running|ok|error, summary, ms, thought}] */
function StepsTimeline({ steps, thinking, live, onOpenArtifact }) {
  const [open, setOpen] = useState(!!live);
  if (!steps?.length && !thinking) return null;

  const running = steps?.some((s) => s.status === "running");
  const total = steps?.length || 0;

  return (
    <div className="steps">
      <button type="button" className="steps-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className={`steps-caret ${open ? "open" : ""}`}>›</span>
        {running ? (
          <>
            <span className="spinner small" /> Working… ({total} step{total === 1 ? "" : "s"})
          </>
        ) : (
          <>
            Analysis steps <span className="steps-count">{total}</span>
          </>
        )}
      </button>

      {open && (
        <div className="steps-body">
          {thinking && <div className="steps-thinking">{thinking}</div>}
          {steps.map((s, i) => (
            <div key={s.id || i} className={`step ${s.status}`}>
              <div className="step-dot" />
              <div className="step-main">
                {s.thought && <div className="step-thought">{s.thought}</div>}
                <div className="step-title">
                  <b>{toolLabel(s.name)}</b>
                  {s.status === "running" && <span className="spinner small" />}
                  {s.status === "ok" && <span className="step-meta">{s.summary} · {s.ms} ms</span>}
                  {s.status === "error" && <span className="step-meta error">{s.summary}</span>}
                  {s.status === "ok" && onOpenArtifact && (
                    <button type="button" className="step-open" onClick={() => onOpenArtifact(s.id)}>
                      Open
                    </button>
                  )}
                </div>
                <Args step={s} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default StepsTimeline;
