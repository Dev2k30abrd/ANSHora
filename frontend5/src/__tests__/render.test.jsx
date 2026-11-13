// @vitest-environment jsdom
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import ArtifactPanel from "../components/ArtifactPanel";
import AssistantMessage from "../components/AssistantMessage";
import ChartRenderer from "../components/ChartRenderer";
import ConversationalEmailPreviewCard from "../components/ConversationalEmailPreviewCard";
import EmailReportModal from "../components/EmailReportModal";
import Header from "../components/Header";
import DecisionsPanel from "../components/panels/DecisionsPanel";
import ProfitImpact from "../components/ProfitImpact";
import Sidebar from "../components/Sidebar";
import VerificationBadge from "../components/VerificationBadge";

const profit = {
  mode: "full", currency: "₹", total_at_stake_formatted: "₹1.26 L", total_note: "Upper bound",
  headline: { formatted: { revenue: "₹9.09 L", profit: "₹1.57 L", margin: "16.8%" } },
  notes: ["1 exact duplicate row(s) excluded from every figure."],
  findings: [{ id: "f1", rank: 1, type: "leak", title: "Discount leakage", impact_amount: 126000, impact_formatted: "₹1.26 L",
    detail: "Discounts gave away about ₹1.26 L.", how: "revenue × d / (1 − d)", confidence: "high", counts_toward_total: true }],
};

const run = { id: "c1", name: "profit_impact_analysis", ok: true, ms: 40, summary: "1 finding", artifact_kind: "profit_impact", result: profit, arguments: {} };
const meta = {
  tool_runs: [run], demo: true,
  verification: { status: "verified", checked: 3, verified: 3, derived: 0, unverified: [], score: 1 },
  confidence: { score: 88, label: "High", reasons: ["Every figure traced to the computed results."] },
  followups: ["What if we cut discounts by 20%?"],
};

describe("render smoke", () => {
  it("sidebar", () => {
    const html = renderToString(
      <Sidebar open user={{ name: "Devansh", workspace: { name: "Acme" } }} datasets={[{ id: "d", filename: "data2.csv" }]}
        dataset={{ id: "d", filename: "data2.csv", summary: { rows: 31, columns: 9, duplicate_rows: 1, duplicates_excluded: 1 } }}
        chats={[{ id: "c", title: "Margins" }]} chatId="c" hasDataset
        onNewChat={() => {}} onSelectDataset={() => {}} onDeleteDataset={() => {}} onAddData={() => {}} onToggleDuplicates={() => {}}
        onOpenTool={() => {}} onSelectChat={() => {}} onRenameChat={() => {}} onDeleteChat={() => {}} onExportChat={() => {}}
        onSettings={() => {}} onSignOut={() => {}} />
    );
    expect(html).toContain("data2.csv");
    expect(html).toContain("1 duplicate row excluded");
    expect(html).not.toMatch(/nemotron|gpt|model/i);
  });

  it("header never shows a model name", () => {
    const html = renderToString(<Header title="Chat" onToggleSidebar={() => {}} theme="light" onToggleTheme={() => {}} unread={2} onBell={() => {}} />);
    expect(html).toContain("Chat");
    expect(html).not.toMatch(/nemotron|model/i);
  });

  it("assistant message with proof badge, artifact card and follow-ups", () => {
    const html = renderToString(
      <AssistantMessage message={{ id: "m", role: "assistant", content: "**Key insight:** margin is 16.8%.", meta }}
        isLast onFollowup={() => {}} onRegenerate={() => {}} onOpenArtifact={() => {}} />
    );
    expect(html).toContain("Figures verified");
    expect(html).toContain("Profit impact");
    expect(html).toContain("cut discounts");
  });

  it("artifact panel + profit view", () => {
    expect(renderToString(<ProfitImpact data={profit} />)).toContain("Discount leakage");
    const html = renderToString(<ArtifactPanel runs={[run]} activeId="c1" onSelect={() => {}} onClose={() => {}} />);
    expect(html).toContain("Money at stake");
  });

  it("verification badge flags unverified figures", () => {
    const html = renderToString(<VerificationBadge verification={{ status: "unverified", checked: 2, verified: 0, unverified: [{ text: "₹8.08 L" }] }} confidence={{ score: 40, label: "Low", reasons: [] }} />);
    expect(html).toContain("Unverified figures");
  });

  it("email report modal renders sender and confirmation options", () => {
    const html = renderToString(<EmailReportModal datasetId="ds_1" onClose={() => {}} />);
    expect(html).toContain("Email Executive Report via Gmail");
    expect(html).toContain("anshora.ai.agent@gmail.com");
    expect(html).toContain("Explicit Confirm &amp; Send");
  });

  it("chart renderer handles semantic charts cleanly", () => {
    const chartData = {
      type: "bar",
      title: "Revenue by Category",
      labels: ["Tech", "Furniture", "Office"],
      series: [{ name: "Revenue", data: [120000, 85000, 43000] }],
    };
    const html = renderToString(<ChartRenderer chart={chartData} />);
    expect(html).toContain("Revenue by Category");
  });

  it("decisions panel renders structured decisions and summary", () => {
    const html = renderToString(
      <DecisionsPanel
        datasetId="ds_1"
        columns={["Sales", "Profit", "Discount"]}
        currency="₹"
      />
    );
    expect(html).toContain("Connect analysis to execution");
    expect(html).toContain("+ Create New Structured Decision");
    expect(html).toContain("No decisions match this filter.");
  });

  it("conversational email preview card renders inline with confirmation actions", () => {
    const preview = {
      sender: "Anshora AI Agent <anshora.ai.agent@gmail.com>",
      recipient: "manager@example.com",
      subject: "Anshora Executive Report: Sales Analysis",
      attachments: [{ name: "report.pdf", size_formatted: "142 KB", type: "application/pdf" }],
      preview_token: "tok_test_123",
      format: "pdf",
      report_type: "executive",
    };
    const html = renderToString(<ConversationalEmailPreviewCard preview={preview} />);
    expect(html).toContain("Anshora Email Delivery");
    expect(html).toContain("Preview Prepared");
    expect(html).toContain("manager@example.com");
    expect(html).toContain("Confirm &amp; Send via Gmail");
    expect(html).toContain("report.pdf");
  });

  it("assistant message renders conversational email card when email_preview is present in meta", () => {
    const msg = {
      id: "a1",
      role: "assistant",
      content: "I have prepared your executive report email.",
      meta: {
        email_preview: {
          recipient: "cfo@example.com",
          subject: "Q4 Financial Overview",
          preview_token: "tok_abc",
          format: "pdf",
          report_type: "executive",
        },
      },
    };
    const html = renderToString(<AssistantMessage message={msg} />);
    expect(html).toContain("I have prepared your executive report email.");
    expect(html).toContain("cfo@example.com");
    expect(html).toContain("Confirm &amp; Send via Gmail");
  });
});
