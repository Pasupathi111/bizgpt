"""Final PDF for an approved report (application logic, no AI)."""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .ai import STAGES
from .logic import effective, group

BRAND = colors.HexColor('#1e3a8a')
styles = getSampleStyleSheet()
H1 = ParagraphStyle('H1', parent=styles['Title'], textColor=BRAND, fontSize=20, spaceAfter=4)
H2 = ParagraphStyle('H2', parent=styles['Heading2'], textColor=BRAND, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle('H3', parent=styles['Heading3'], spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle('Body', parent=styles['BodyText'], fontSize=9.5, leading=13)
SMALL = ParagraphStyle('Small', parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor('#374151'))


def _paras(text: str) -> list:
    out = []
    for line in (text or '').split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith(('- ', '• ', '* ')):
            out.append(Paragraph('• ' + escape(line[2:]), BODY))
        else:
            out.append(Paragraph(escape(line), BODY))
    return out or [Paragraph('—', BODY)]


def _thumb(path: str, width: float) -> Image:
    with PILImage.open(path) as img:
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((700, 700))
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=80)
        w, h = img.size
    buf.seek(0)
    return Image(buf, width=width, height=width * h / w)


def _photo_cell(photo: dict, width: float) -> list:
    eff = effective(photo)
    caption = (
        f'<b>{escape(photo["filename"])}</b><br/>'
        f'{escape(eff["location"] or "Unknown location")} · {escape(eff["work_type"] or "Unknown work")}<br/>'
        f'{escape(eff["datetime"] or "Date/time unknown")}'
    )
    return [_thumb(photo['path'], width), Paragraph(caption, SMALL)]


def _photo_section(stage: str, photos: list[dict], zones: list[str], page_width: float) -> list:
    by_id = {p['id']: p for p in photos}
    heading = Paragraph(f'{stage.title()} Photos', H2)
    story = []
    any_photo = False
    cols, gap = 3, 4 * mm
    cell_w = (page_width - gap * (cols - 1)) / cols
    for g in group(photos, zones):
        ids = g['stages'][stage]
        if not ids:
            continue
        any_photo = True
        cells = [_photo_cell(by_id[i], cell_w) for i in ids]
        rows = [cells[i:i + cols] + [''] * (cols - len(cells[i:i + cols])) for i in range(0, len(cells), cols)]
        table = Table(rows, colWidths=[cell_w + gap] * cols)
        table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        # The stage heading travels with its first zone so it is never stranded at a page bottom.
        story.append(KeepTogether([*([heading] if not story else []), Paragraph(escape(g['location']), H3), table]))
    if not any_photo:
        story = [heading, Paragraph(f'No {stage.lower()} photos.', BODY)]
    return story


def build_pdf(out_path, report: dict, project: dict, photos: list[dict], validation: dict, confidence: dict):
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f'Monthly Maintenance Report {report["id"]}', author='Biz GPT')
    width = A4[0] - 32 * mm
    sections = report['content']['sections']
    decision = report.get('decision') or {}
    month_label = datetime.strptime(report['month'], '%Y-%m').strftime('%B %Y')

    meta = Table(
        [
            ['Project', project['name'], 'Report ID', report['id']],
            ['Client', project.get('client') or '—', 'Month', month_label],
            ['Approved by', decision.get('by') or '—', 'Approved at', decision.get('at') or '—'],
        ],
        colWidths=[26 * mm, 70 * mm, 24 * mm, width - 120 * mm],
    )
    meta.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey), ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.lightgrey),
    ]))

    story = [Paragraph('MONTHLY MAINTENANCE REPORT', H1), meta, Spacer(1, 6)]
    for key, title in (('executive_summary', 'Executive Summary'), ('location_summary', 'Location Summary'),
                       ('work_performed', 'Work Performed')):
        story += [Paragraph(title, H2), *_paras(sections.get(key, ''))]

    # Photo coverage table (deterministic validation).
    rows = [['Location', *[s.title() for s in STAGES]]]
    for loc in validation['locations']:
        # Built-in PDF fonts have no check-mark glyphs, so plain words.
        rows.append([loc['location'], *[f'OK ({c["count"]})' if c['ok'] else 'MISSING' for c in loc['checks']]])
    cov = Table(rows, colWidths=[width * 0.31] + [width * 0.23] * 3)
    cov.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2ff')),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))
    story += [Paragraph('Photo Coverage', H2), cov]

    story.append(PageBreak())
    active_photos = [p for p in photos if not p['excluded'] and p['status'] == 'analyzed']
    for stage in STAGES:
        story += _photo_section(stage, active_photos, project['zones'], width)

    story += [Paragraph('Issues / Observations', H2), *_paras(sections.get('issues_observations', ''))]
    story += [Paragraph('Missing Information', H2),
              *_paras('\n'.join(f'- {m}' for m in validation['missing']) or 'None. All locations have Before, During and After photos.')]
    story += [Paragraph('Remarks', H2), *_paras(sections.get('remarks', '')), *_paras(report.get('remarks') or '')]

    conf_rows = [['Field', 'Avg AI confidence', 'Below threshold', 'Unknown', 'Human corrected']]
    for f in confidence['fields'].values():
        avg = f['average_ai_confidence']
        conf_rows.append([f['label'], f'{avg}%' if avg is not None else '—', f['below_threshold'], f['unknown'], f['human_corrected']])
    conf = Table(conf_rows, colWidths=[width * 0.24] + [width * 0.19] * 4)
    conf.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2ff')),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
    ]))
    story += [Paragraph('AI Confidence Summary', H2), conf, Spacer(1, 4),
              Paragraph(f'Review threshold {confidence["threshold"]}%. {confidence["photos_analyzed"]} photos analysed by AI '
                        f'({escape(report["content"].get("model") or "")}); {confidence["human_reviewed_photos"]} confirmed by a coordinator. '
                        'All AI output was reviewed and approved by a human before this report was issued.', SMALL)]
    doc.build(story)
