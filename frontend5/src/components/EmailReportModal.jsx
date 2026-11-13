import { useEffect, useState } from "react";
import {
  authorizeGmail,
  errorText,
  getGmailStatus,
  previewReportEmail,
  sendReportEmail,
} from "../services/api";

function EmailReportModal({ datasetId, onClose }) {
  const [recipient, setRecipient] = useState("");
  const [format, setFormat] = useState("pdf");
  const [customNotes, setCustomNotes] = useState("");
  const [status, setStatus] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [sending, setSending] = useState(false);
  const [deliveryResult, setDeliveryResult] = useState(null);
  const [error, setError] = useState("");

  // Load Gmail connection status
  useEffect(() => {
    getGmailStatus()
      .then(setStatus)
      .catch(() => setStatus({ connected: false, configured: false }));
  }, []);

  // Fetch or refresh preview when recipient or options change
  const loadPreview = async () => {
    if (!recipient.trim() || !recipient.includes("@")) {
      setError("Please enter a valid recipient email address first.");
      return;
    }
    setError("");
    setLoadingPreview(true);
    try {
      const p = await previewReportEmail({
        dataset_id: datasetId,
        recipient: recipient.trim(),
        format,
        custom_notes: customNotes,
        report_type: "executive",
      });
      setPreview(p);
    } catch (e) {
      setError(errorText(e, "Failed to generate email preview."));
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleConnectGmail = async () => {
    try {
      const res = await authorizeGmail(window.location.href);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch (e) {
      setError(errorText(e, "Unable to start Google OAuth flow."));
    }
  };

  const handleConfirmSend = async () => {
    if (!recipient.trim()) {
      setError("Recipient is required.");
      return;
    }
    setError("");
    setSending(true);
    try {
      const res = await sendReportEmail({
        dataset_id: datasetId,
        recipient: recipient.trim(),
        confirmation: true,
        format,
        custom_notes: customNotes,
        report_type: "executive",
        subject: preview?.subject,
        idempotency_key: preview?.preview_token,
      });
      setDeliveryResult(res);
    } catch (e) {
      setError(errorText(e, "Failed to deliver email via Gmail API."));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="email-modal-overlay">
      <div className="email-modal">
        <div className="email-modal-header">
          <div className="email-modal-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
              <polyline points="22,6 12,13 2,6" />
            </svg>
            <span>Email Executive Report via Gmail</span>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close modal">×</button>
        </div>

        {deliveryResult ? (
          <div className="email-modal-success">
            <div className="success-icon">✓</div>
            <h3>Report Successfully Delivered</h3>
            <p>
              Your verified executive report has been dispatched to <strong>{deliveryResult.recipient}</strong>.
            </p>
            <div className="delivery-details">
              <div><span>Sender:</span> {deliveryResult.sender || "Anshora <anshora.ai.agent@gmail.com>"}</div>
              <div><span>Provider:</span> Official Gmail API</div>
              <div><span>Message ID:</span> {deliveryResult.message_id}</div>
              <div><span>Dispatched at:</span> {deliveryResult.sent_at}</div>
            </div>
            <button type="button" className="upload-button" onClick={onClose}>Done</button>
          </div>
        ) : (
          <div className="email-modal-body">
            {/* Status notification banner */}
            {status && !status.connected && (
              <div className="oauth-warning-banner">
                <div className="oauth-warning-content">
                  <strong>Gmail API Not Connected</strong>
                  <span>
                    Report generation & email preview work in development mode. To send live emails through Anshora ({status.sender_email}), connect via Google OAuth.
                  </span>
                </div>
                {status.configured ? (
                  <button type="button" className="connect-google-btn" onClick={handleConnectGmail}>
                    Connect with Google
                  </button>
                ) : (
                  <span className="oauth-setup-badge">Requires GOOGLE_CLIENT_ID</span>
                )}
              </div>
            )}

            {error && <div className="panel-error">{error}</div>}

            <div className="email-composer-form">
              <div className="form-row">
                <label>
                  <span>Recipient Email *</span>
                  <div className="input-with-button">
                    <input
                      type="email"
                      placeholder="e.g. manager@company.com"
                      value={recipient}
                      onChange={(e) => setRecipient(e.target.value)}
                      required
                    />
                    <button
                      type="button"
                      className="mini-btn secondary"
                      onClick={loadPreview}
                      disabled={loadingPreview || !recipient.trim()}
                    >
                      {loadingPreview ? "Generating Preview…" : "Generate Preview"}
                    </button>
                  </div>
                </label>
              </div>

              <div className="form-row-grid">
                <label>
                  <span>Attachment Format</span>
                  <select value={format} onChange={(e) => setFormat(e.target.value)}>
                    <option value="pdf">PDF Attachment (Board Report)</option>
                    <option value="csv">CSV Attachment (Raw Verified Data)</option>
                    <option value="both">Both (PDF + CSV)</option>
                    <option value="inline">HTML Email Only (No Attachment)</option>
                  </select>
                </label>
                <label>
                  <span>Sender Account</span>
                  <input
                    type="text"
                    disabled
                    value={`Anshora <${status?.sender_email || "anshora.ai.agent@gmail.com"}>`}
                  />
                </label>
              </div>

              <div className="form-row">
                <label>
                  <span>Briefing Notes for Recipient (Optional)</span>
                  <textarea
                    rows={2}
                    placeholder="e.g. Please review key margin takeaways and action items before tomorrow's team sync."
                    value={customNotes}
                    onChange={(e) => setCustomNotes(e.target.value)}
                  />
                </label>
              </div>
            </div>

            {/* Live Preview Display */}
            {preview && (
              <div className="email-preview-container">
                <div className="preview-meta-bar">
                  <div className="preview-meta-item">
                    <span>Subject:</span> <strong>{preview.subject}</strong>
                  </div>
                  {preview.attachments?.length > 0 && (
                    <div className="preview-attachments">
                      <span>Attachments:</span>
                      {preview.attachments.map((att) => (
                        <span key={att.name} className="attachment-chip">
                          📎 {att.name} ({att.size_formatted})
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div className="preview-viewport">
                  <div
                    className="email-html-render"
                    dangerouslySetInnerHTML={{ __html: preview.html_body }}
                  />
                </div>
              </div>
            )}

            {/* Action Bar */}
            <div className="email-modal-footer">
              <button type="button" className="ghost-button" onClick={onClose} disabled={sending}>
                Cancel
              </button>
              <button
                type="button"
                className="upload-button"
                onClick={handleConfirmSend}
                disabled={sending || !status?.connected || !recipient.trim()}
                title={!status?.connected ? "Connect Gmail account via Google OAuth to send" : ""}
              >
                {sending ? (
                  <>
                    <span className="spinner small" />
                    <span>Sending via Gmail API…</span>
                  </>
                ) : (
                  <span>Explicit Confirm & Send</span>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default EmailReportModal;
