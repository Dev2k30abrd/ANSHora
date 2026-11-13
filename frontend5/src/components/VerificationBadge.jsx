import { useState } from "react";

const TONE = { verified: "good", partial: "warn", unverified: "bad", no_numbers: "neutral" };
const TEXT = {
  verified: "Figures verified",
  partial: "Partly verified",
  unverified: "Unverified figures",
  no_numbers: "No figures stated",
};

function VerificationBadge({ verification, confidence }) {
  const [open, setOpen] = useState(false);
  if (!verification && !confidence) return null;
  const tone = TONE[verification?.status] || "neutral";

  return (
    <div className="verify-wrap">
      <button type="button" className={`verify-badge ${tone}`} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="verify-icon">{tone === "good" ? "✓" : tone === "bad" ? "!" : tone === "warn" ? "≈" : "·"}</span>
        {TEXT[verification?.status] || "Checked"}
        {confidence && <span className="verify-conf">· {confidence.label} confidence {confidence.score}</span>}
      </button>

      {open && (
        <div className="verify-pop">
          {verification && verification.status !== "no_numbers" && (
            <p>
              <strong>{verification.verified}</strong> of {verification.checked} figures matched the computed results
              {verification.derived > 0 && <>, {verification.derived} derived from them</>}.
              {verification.auto_corrected && " The answer was automatically rewritten once to remove unsupported figures."}
            </p>
          )}
          {verification?.unverified?.length > 0 && (
            <p className="verify-bad">
              Could not trace: {verification.unverified.map((u) => u.text).join(", ")}
            </p>
          )}
          {confidence?.reasons?.length > 0 && (
            <ul>
              {confidence.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
          <small>Checked deterministically against the tool results — not by another AI.</small>
        </div>
      )}
    </div>
  );
}

export default VerificationBadge;
