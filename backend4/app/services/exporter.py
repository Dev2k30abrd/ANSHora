"""Board-ready exports (PDF / Excel / HTML / Markdown) from the Profit Impact Engine + report narrative."""
import html
import io
import os
from datetime import datetime

from app.core import config as cfg
from app.core import db
from app.core.context import current_workspace
from app.services.dataset_manager import dataset_store

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _currency(dataset_id):
    ws = current_workspace.get()
    row = db.one("SELECT currency FROM workspaces WHERE id=?", (ws,)) if ws else None
    return (row or {}).get("currency") or cfg.DEFAULT_CURRENCY


def build_payload(dataset_id: str, narrative: str | None = None) -> dict:
    from app.services.profit_service import run_profit

    df = dataset_store.get(dataset_id)
    cur = _currency(dataset_id)
    pi = run_profit(dataset_id)
    if narrative is None:
        cached = dataset_store.get_cache(dataset_id, "executive_report")
        if cached:
            narrative = cached.get("narrative")
        else:
            try:
                from app.agents.analytics_agent import ask_llm
                from app.services.executive_report import generate_executive_report

                res = generate_executive_report(df, dataset_id, dataset_store.get_filename(dataset_id), ask_llm)
                dataset_store.set_cache(dataset_id, "executive_report", res)
                narrative = res["narrative"]
            except Exception as e:  # noqa: BLE001
                narrative = f"(Narrative unavailable: {e})"
    return {"title": f"Profit Impact Report — {dataset_store.get_filename(dataset_id)}",
            "generated": datetime.now().strftime("%d %b %Y, %H:%M"), "currency": cur,
            "profit": pi, "narrative": narrative or "", "rows": len(df)}


def to_markdown(p: dict) -> str:
    pi, h = p["profit"], p["profit"].get("headline", {}).get("formatted", {})
    lines = [f"# {p['title']}", f"_Generated {p['generated']} · {p['rows']} rows_", "",
             "## Headline", f"- Revenue: {h.get('revenue')}"]
    if h.get("cost"):
        lines.append(f"- Cost: {h.get('cost')}")
    lines += [f"- Profit: {h.get('profit')}", f"- Margin: {h.get('margin')} (profit ÷ revenue, rows with both)",
             f"- **Money at stake: {pi.get('total_at_stake_formatted')}**", "", "## Findings ranked by impact"]
    main = [f for f in pi.get("findings", []) if f.get("counts_toward_total")]
    other = [f for f in pi.get("findings", []) if not f.get("counts_toward_total")]
    for i, f in enumerate(main, 1):
        lines += [f"{i}. **{f['title']}** — {f['impact_formatted']} ({f['confidence']} confidence)",
                  f"   {f['detail']}", f"   _How: {f['how']}_"]
    if other:
        lines += ["", "## Other signals (not counted in money at stake)"] + [f"- {f['title']}: {f['detail']}" for f in other]
    if pi.get("notes"):
        lines += ["", "## Notes"] + [f"- {n}" for n in pi["notes"]]
    lines += ["", "## Narrative", p["narrative"]]
    return "\n".join(lines)


def to_html(p: dict) -> str:
    pi, h = p["profit"], p["profit"].get("headline", {}).get("formatted", {})
    rows = "".join(
        f"<tr><td>{i}</td><td><b>{html.escape(f['title'])}</b><br><small>{html.escape(f['detail'])}</small></td>"
        f"<td class=n>{html.escape(f['impact_formatted'])}</td><td>{f['confidence']}</td></tr>"
        for i, f in enumerate([x for x in pi.get("findings", []) if x.get("counts_toward_total")], 1))
    narr = "".join(f"<p>{html.escape(x)}</p>" for x in p["narrative"].split("\n\n"))
    return f"""<!doctype html><meta charset=utf-8><title>{html.escape(p['title'])}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 16px;color:#1f2328}}
h1{{font-size:24px}}.k{{display:flex;gap:12px;flex-wrap:wrap}}.k div{{border:1px solid #ddd;border-radius:10px;padding:12px 16px;min-width:140px}}
.k b{{display:block;font-size:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eee;padding:8px;text-align:left;vertical-align:top}}
.n{{text-align:right;font-weight:600;white-space:nowrap}}.risk{{background:#fff4e5;border-radius:10px;padding:12px 16px;margin:16px 0}}</style>
<h1>{html.escape(p['title'])}</h1><small>Generated {p['generated']} · {p['rows']} rows</small>
<div class=k><div>Revenue<b>{h.get('revenue')}</b></div><div>Profit<b>{h.get('profit')}</b></div><div>Margin<b>{h.get('margin')}</b></div></div>
<div class=risk>Money at stake: <b>{pi.get('total_at_stake_formatted')}</b><br><small>{html.escape(pi.get('total_note',''))}</small></div>
<h2>Findings ranked by impact</h2><table><tr><th>#</th><th>Finding</th><th>Impact</th><th>Confidence</th></tr>{rows}</table>
<h2>Narrative</h2>{narr}"""


def to_xlsx(p: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    pi = p["profit"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    h = pi.get("headline", {})
    for r in [("Report", p["title"]), ("Generated", p["generated"]), ("Rows", p["rows"]), ("Currency", p["currency"]),
              ("Revenue", h.get("revenue")), ("Cost", h.get("cost")), ("Profit", h.get("profit")),
              ("Margin %", round(h["margin_pct"], 2) if h.get("margin_pct") is not None else None),
              ("Money at stake", pi.get("total_at_stake")), ("Note", pi.get("total_note"))]:
        ws.append(list(r))
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 18, 60
    wf = wb.create_sheet("Findings")
    wf.append(["Rank", "Type", "Title", "Impact", "Confidence", "Detail", "How calculated"])
    for c in wf[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F5BEA")
    for f in pi.get("findings", []):
        wf.append([f["rank"], f["type"] + ("" if f.get("counts_toward_total") else " (context)"), f["title"], round(f["impact_amount"], 2), f["confidence"], f["detail"], f["how"]])
    for col, w in zip("ABCDEFG", (6, 12, 48, 14, 12, 70, 50)):
        wf.column_dimensions[col].width = w
    wn = wb.create_sheet("Narrative")
    for line in p["narrative"].split("\n"):
        wn.append([line])
    wn.column_dimensions["A"].width = 120
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(p: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font, fixed = "Helvetica", True
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("AnshoraSans", path))
                bold = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                if os.path.exists(bold):
                    from reportlab.pdfbase.pdfmetrics import registerFontFamily

                    pdfmetrics.registerFont(TTFont("AnshoraSans-Bold", bold))
                    registerFontFamily("AnshoraSans", normal="AnshoraSans", bold="AnshoraSans-Bold",
                                       italic="AnshoraSans", boldItalic="AnshoraSans-Bold")
                font, fixed = "AnshoraSans", False
                break
            except Exception:
                continue

    def t(x):  # Helvetica has no rupee glyph
        x = "" if x is None else str(x)
        return x.replace("₹", "Rs.") if fixed else x

    def esc(x):
        return html.escape(t(x))

    st = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=st["BodyText"], fontName=font, fontSize=10, leading=14)
    small = ParagraphStyle("s", parent=base, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
    h1 = ParagraphStyle("h1", parent=base, fontSize=20, leading=24, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base, fontSize=13, leading=16, spaceBefore=12, spaceAfter=4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    pi, hf = p["profit"], p["profit"].get("headline", {}).get("formatted", {})
    el = [Paragraph(esc(p["title"]), h1), Paragraph(f"Generated {p['generated']} · {p['rows']} rows", small), Spacer(1, 8)]
    kp = Table([["Revenue", "Profit", "Margin", "Money at stake"],
                [t(hf.get("revenue")), t(hf.get("profit")), t(hf.get("margin")), t(pi.get("total_at_stake_formatted"))]],
               colWidths=[40 * mm] * 4)
    kp.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, 0), 8),
                            ("FONTSIZE", (0, 1), (-1, 1), 13), ("TEXTCOLOR", (0, 0), (-1, 0), colors.grey),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                            ("TEXTCOLOR", (3, 1), (3, 1), colors.HexColor("#c2410c")), ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el += [kp, Paragraph(esc(pi.get("total_note", "")), small), Paragraph("Findings ranked by money impact", h2)]
    data = [["#", "Finding", "Impact", "Conf."]]
    main_f = [f for f in pi.get("findings", []) if f.get("counts_toward_total")]
    for i, f in enumerate(main_f, 1):
        data.append([str(i), Paragraph(f"<b>{esc(f['title'])}</b><br/>{esc(f['detail'])}", small),
                     t(f["impact_formatted"]), f["confidence"]])
    if len(data) > 1:
        ft = Table(data, colWidths=[8 * mm, 112 * mm, 28 * mm, 18 * mm], repeatRows=1)
        ft.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f5bea")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey)]))
        el.append(ft)
    else:
        el.append(Paragraph("No material money-impacting findings detected.", base))
    others = [f for f in pi.get("findings", []) if not f.get("counts_toward_total")]
    if others:
        el.append(Paragraph("Other signals (not counted in money at stake)", h2))
        for f in others:
            el.append(Paragraph(f"• <b>{esc(f['title'])}</b> — {esc(f['detail'])}", small))
    for n in pi.get("notes", []):
        el.append(Paragraph("• " + esc(n), small))
    el.append(Paragraph("Narrative", h2))
    for para in p["narrative"].split("\n\n"):
        el.append(Paragraph(esc(para).replace("\n", "<br/>"), base))
        el.append(Spacer(1, 4))
    doc.build(el)
    return buf.getvalue()
