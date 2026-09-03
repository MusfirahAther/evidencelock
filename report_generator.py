"""In-memory PDF generation for EvidenceLock verification results."""

from datetime import datetime
from html import escape
from io import BytesIO
import unicodedata

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INDIGO = colors.HexColor("#4F46E5")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
CORRECT = colors.HexColor("#059669")
WRONG = colors.HexColor("#DC2626")
UNCLEAR = colors.HexColor("#D97706")


def _pdf_text(value):
    """Convert dynamic text to a safe, Helvetica-compatible PDF string."""
    value = "" if value is None else str(value)
    value = value.replace("—", "-").replace("–", "-").replace("•", "-")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def _format_value(result, field):
    """Format a claimed or calculated value while retaining percentage context."""
    value = result.get(field)
    if value is None:
        return "Not available"

    is_percentage = "%" in result.get("original_sentence", "") or "percent" in result.get("original_sentence", "").lower()
    if isinstance(value, float):
        formatted = f"{value:+.2f}" if is_percentage else f"{value:,.2f}"
    elif isinstance(value, int):
        formatted = f"{value:,}"
    else:
        formatted = str(value)
    return f"{formatted}%" if is_percentage else formatted


def _verdict_color(verdict):
    """Return the shared EvidenceLock status color for a verdict."""
    return {"CORRECT": CORRECT, "WRONG": WRONG, "UNCLEAR": UNCLEAR}.get(verdict, UNCLEAR)


def generate_verification_report(dataset_name, report_source, verification_results, corrected_report_text, generated_at=None):
    """Build the complete Verification Report as PDF bytes without writing to disk."""
    generated_at = generated_at or datetime.now()
    results = verification_results or []
    correct_count = sum(result.get("verdict") == "CORRECT" for result in results)
    wrong_count = sum(result.get("verdict") == "WRONG" for result in results)
    unclear_count = sum(result.get("verdict") == "UNCLEAR" for result in results)
    evaluated_count = correct_count + wrong_count
    accuracy_rate = (correct_count / evaluated_count * 100) if evaluated_count else 0.0

    # Build the PDF in a byte buffer so it can be sent directly from a serverless function.
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title="EvidenceLock Verification Report",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=INDIGO, spaceAfter=6)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=9, leading=13, textColor=MUTED)
    heading_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=SLATE, spaceBefore=16, spaceAfter=8)
    body_style = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8, leading=11, textColor=SLATE)
    table_header_style = ParagraphStyle("TableHeader", parent=body_style, fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white)
    table_cell_style = ParagraphStyle("TableCell", parent=body_style, fontSize=7.3, leading=9)
    verdict_style = ParagraphStyle("Verdict", parent=table_cell_style, fontName="Helvetica-Bold", alignment=TA_CENTER)
    corrected_style = ParagraphStyle("CorrectedReport", parent=body_style, fontName="Helvetica", fontSize=8, leading=11, backColor=colors.HexColor("#F8FAFC"), borderColor=colors.HexColor("#E2E8F0"), borderWidth=0.5, borderPadding=10)

    story = []

    # Header: identify this audit, when it ran, and the exact two active sources.
    story.append(Paragraph("EvidenceLock Verification Report", title_style))
    header_data = [
        ["Verification run", generated_at.strftime("%Y-%m-%d %H:%M:%S")],
        ["Data source", _pdf_text(dataset_name)],
        ["Report checked", _pdf_text(report_source)],
    ]
    header_table = Table(header_data, colWidths=[1.15 * inch, 8.25 * inch])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LEADING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([header_table, Spacer(1, 4)])

    # Summary: surface every verdict count and calculate accuracy without unclear claims.
    story.append(Paragraph("Summary", heading_style))
    summary_data = [[
        Paragraph("Total claims checked<br/><b>%s</b>" % len(results), body_style),
        Paragraph("<font color=\"#059669\">Correct</font><br/><b>%s</b>" % correct_count, body_style),
        Paragraph("<font color=\"#DC2626\">Wrong</font><br/><b>%s</b>" % wrong_count, body_style),
        Paragraph("<font color=\"#D97706\">Unclear</font><br/><b>%s</b>" % unclear_count, body_style),
        Paragraph("Accuracy rate<br/><b>%.1f%%</b>" % accuracy_rate, body_style),
    ]]
    summary_table = Table(summary_data, colWidths=[1.85 * inch] * 5)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#EEF2FF")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#ECFDF5")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FEF2F2")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#FFFBEB")),
        ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(summary_table)
    story.append(Paragraph("Accuracy is Correct divided by Correct plus Wrong. Unclear claims are excluded.", subtitle_style))

    # Detailed findings: preserve the audit trail for each individual extracted claim.
    story.append(Paragraph("Detailed Findings", heading_style))
    findings_data = [[
        Paragraph("Original claim", table_header_style),
        Paragraph("Verdict", table_header_style),
        Paragraph("Claimed vs real", table_header_style),
        Paragraph("Evidence", table_header_style),
    ]]
    for result in results:
        verdict = _pdf_text(result.get("verdict", "UNCLEAR")).upper()
        findings_data.append([
            Paragraph(escape(_pdf_text(result.get("original_sentence", ""))), table_cell_style),
            Paragraph(f'<font color="#{_verdict_color(verdict).hexval()[2:]}">{verdict}</font>', verdict_style),
            Paragraph(f"Claimed: {escape(_pdf_text(_format_value(result, 'claimed_value')))}<br/>Real: {escape(_pdf_text(_format_value(result, 'real_value')))}", table_cell_style),
            Paragraph(escape(_pdf_text(result.get("evidence", ""))), table_cell_style),
        ])
    if not results:
        findings_data.append([Paragraph("No checkable claims were available for this report.", table_cell_style), "", "", ""])

    findings_table = Table(findings_data, colWidths=[2.45 * inch, 0.8 * inch, 1.25 * inch, 4.7 * inch], repeatRows=1)
    findings_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INDIGO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(findings_table)

    # Corrected report: include the complete machine-corrected text after the evidence table.
    story.append(Paragraph("Corrected Report", heading_style))
    corrected_html = escape(_pdf_text(corrected_report_text)).replace("\n", "<br/>")
    story.append(Paragraph(corrected_html or "No report text was available.", corrected_style))

    # Footer: make the automated provenance clear at the end of every generated PDF.
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "This report was generated automatically by EvidenceLock, an automated fact-checking tool for business reports.",
        subtitle_style,
    ))

    document.build(story)
    return buffer.getvalue()
