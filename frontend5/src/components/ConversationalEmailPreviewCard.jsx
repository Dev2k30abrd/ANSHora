import { useState } from "react";
import { authorizeGmail, errorText, sendReportEmail } from "../services/api";

function ConversationalEmailPreviewCard({ preview, onSent, onCancelled }) {
  const [status, setStatus] = useState("ready"); // "ready" | "sending" | "accepted" | "duplicate" | "cancelled" | "failed"
  const [error, setError] = useState("");
  const [deliveryResult, setDeliveryResult] = useState(null);
  const [showHtml, setShowHtml] = useState(false);

  if (!preview) return null;

  const recipients = preview.recipients || (preview.recipient ? preview.recipient.split(",").map((s) => s.trim()) : []);

  const handleConfirm = async () => {
    setStatus("sending");
    setError("");
    try {
      const res = await sendReportEmail({
        dataset_id: preview.dataset_id,
        recipient: preview.recipient,
        subject: preview.subject,
        report_type: preview.report_type || "executive",
        format: preview.format || "pdf",
        confirmation: true,
        preview_token: preview.preview_token,
        action_id: preview.action_id,
      });
      setDeliveryResult(res);
      if (res.deduplicated || res.status === "already_sent") {
        setStatus("duplicate");
      } else {
        setStatus("accepted");
      }
      onSent?.(res);
    } catch (e) {
      setError(errorText(e, "Gmail delivery failed."));
      setStatus("failed");
    }
  };

  const handleCancel = () => {
    setStatus("cancelled");
    onCancelled?.();
  };

  const handleConnectOAuth = async () => {
    try {
      const res = await authorizeGmail(window.location.href);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (e) {
      setError(errorText(e));
    }
  };

  const isOAuthMissing = error && (error.toLowerCase().includes("oauth") || error.toLowerCase().includes("connect") || error.toLowerCase().includes("authenticate"));

  return (
    <div className={`conversational-email-card status-${status}`}>
      {/* Header */}
      <div className="email-card-header">
        <div className="email-card-title">
          <span className="email-card-icon">✉️</span>
          <div>
            <strong>Anshora Email Delivery</strong>
            <span className="email-card-subtitle">Verified Gmail API Integration ({preview.action_id ? `Action #${preview.action_id}` : "Ready"})</span>
          </div>
        </div>
        <div className="email-card-badge">
          {status === "ready" && <span className="badge badge-pending">Preview Prepared</span>}
          {status === "sending" && <span className="badge badge-sending"><span className="spinner small" /> Sending via Gmail…</span>}
          {status === "accepted" && <span className="badge badge-success">✓ Accepted by Gmail</span>}
          {status === "duplicate" && <span className="badge badge-muted">Duplicate Suppressed</span>}
          {status === "cancelled" && <span className="badge badge-muted">Cancelled</span>}
          {status === "failed" && <span className="badge badge-error">Delivery Failed</span>}
        </div>
      </div>

      {/* Meta details */}
      <div className="email-card-meta">
        <div className="meta-field">
          <span className="meta-label">From:</span>
          <span className="meta-value sender-value">{preview.sender || "Anshora AI Agent <anshora.ai.agent@gmail.com>"}</span>
        </div>
        <div className="meta-field">
          <span className="meta-label">To:</span>
          <div className="meta-recipients">
            {recipients.map((r) => (
              <span key={r} className="recipient-pill">{r}</span>
            ))}
          </div>
        </div>
        <div className="meta-field">
          <span className="meta-label">Subject:</span>
          <span className="meta-value subject-value">{preview.subject}</span>
        </div>
        {preview.attachments && preview.attachments.length > 0 && (
          <div className="meta-field">
            <span className="meta-label">Attachments:</span>
            <div className="meta-attachments">
              {preview.attachments.map((att, i) => (
                <span key={i} className="attachment-chip">
                  <span className="att-icon">{att.type?.includes("pdf") ? "📄" : "📊"}</span>
                  <span className="att-name">{att.name}</span>
                  <span className="att-size">({att.size_formatted})</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Expandable Preview Toggle */}
      {preview.html_body && status !== "accepted" && status !== "cancelled" && status !== "duplicate" && (
        <div className="email-preview-toggle-section">
          <button
            type="button"
            className="toggle-preview-btn"
            onClick={() => setShowHtml(!showHtml)}
          >
            {showHtml ? "Hide email body preview ▴" : "View email body preview ▾"}
          </button>
          {showHtml && (
            <div className="email-html-viewport">
              <iframe
                title="Email Preview"
                srcDoc={preview.html_body}
                className="email-iframe"
                sandbox="allow-same-origin"
              />
            </div>
          )}
        </div>
      )}

      {/* Accepted by Gmail Notification */}
      {status === "accepted" && deliveryResult && (
        <div className="email-success-banner">
          <div className="success-icon">✓</div>
          <div>
            <strong>Accepted by Gmail API for Delivery</strong>
            <p>
              Message ID: <code className="msg-id">{deliveryResult.message_id}</code> · Handed off to Google mail servers for <b>{deliveryResult.recipient}</b>.
            </p>
            <p className="delivery-disclaimer">
              <em>Note: Gmail API acceptance confirms Google accepted the message for transmission. Final inbox arrival depends on recipient mailbox provider policies.</em>
            </p>
          </div>
        </div>
      )}

      {/* Duplicate suppressed notice */}
      {status === "duplicate" && deliveryResult && (
        <div className="email-cancelled-banner">
          <span>Notice: An identical email was already dispatched within the last 60 seconds (Message ID: <code>{deliveryResult.message_id}</code>). Duplicate send was prevented.</span>
        </div>
      )}

      {/* Cancelled notice */}
      {status === "cancelled" && (
        <div className="email-cancelled-banner">
          <span>Email delivery request was cancelled. Confirmation token invalidated and no message was dispatched.</span>
        </div>
      )}

      {/* Error notification */}
      {status === "failed" && (
        <div className="email-error-banner">
          <div>
            <strong>Delivery Error:</strong>
            <p style={{ margin: "4px 0 0" }}>{error}</p>
          </div>
          {isOAuthMissing && (
            <button type="button" className="oauth-connect-btn" onClick={handleConnectOAuth}>
              Connect Google Account
            </button>
          )}
        </div>
      )}

      {/* Actions */}
      {status === "ready" && (
        <div className="email-card-actions">
          <button
            type="button"
            className="btn-confirm-send"
            onClick={handleConfirm}
          >
            <span className="send-icon">🚀</span> Confirm & Send via Gmail
          </button>
          <button
            type="button"
            className="btn-cancel-delivery"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      )}

      {status === "failed" && !isOAuthMissing && (
        <div className="email-card-actions">
          <button
            type="button"
            className="btn-confirm-send"
            onClick={handleConfirm}
          >
            Retry Delivery
          </button>
          <button
            type="button"
            className="btn-cancel-delivery"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

export default ConversationalEmailPreviewCard;
