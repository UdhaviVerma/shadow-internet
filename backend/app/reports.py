import csv
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def csv_report(snapshot: dict) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["domain", "snapshot", "category", "source", "confidence", "observed_at", "evidence"])
    for evidence in snapshot["intelligence"]["evidence"]:
        row = [
            snapshot["domain"],
            snapshot["id"],
            evidence["category"],
            evidence["source"],
            evidence["confidence"],
            evidence["observed_at"],
            evidence["value"],
        ]
        writer.writerow(
            [
                "'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
                for value in row
            ]
        )
    return buffer.getvalue()


def pdf_report(snapshot: dict) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#087f8c")
    intel = snapshot["intelligence"]
    story = [
        Paragraph("SHADOW INTERNET", styles["Title"]),
        Paragraph(escape(f"Infrastructure evidence report: {snapshot['domain']}"), styles["Heading1"]),
        Paragraph(
            escape(f"Snapshot {snapshot['id']} | {snapshot['created_at']} | {intel['mode'].upper()}"), styles["Normal"]
        ),
        Spacer(1, 16),
        Paragraph(
            escape(f"Observation index: {intel['overall_score']}/100; category coverage: {intel['coverage']}%"),
            styles["Heading2"],
        ),
    ]
    for category in intel["scores"]:
        story.append(
            Paragraph(
                escape(
                    f"{category['name']}: {category['score'] if category['score'] is not None else 'Unknown'} — {category['explanation']}"
                ),
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 8))
    story.append(Paragraph("Evidence register", styles["Heading2"]))
    for evidence in intel["evidence"]:
        story.append(
            Paragraph(escape(f"[{evidence['id']}] {evidence['source']} | {evidence['value']}"), styles["Normal"])
        )
        story.append(Spacer(1, 8))
    story.append(Paragraph("Scope and limitations", styles["Heading2"]))
    for warning in intel["warnings"]:
        story.append(Paragraph(escape(warning), styles["Normal"]))
        story.append(Spacer(1, 6))
    SimpleDocTemplate(buffer, title=f"Shadow Internet - {snapshot['domain']}").build(story)
    return buffer.getvalue()
