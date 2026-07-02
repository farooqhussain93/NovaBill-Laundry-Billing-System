from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import DEFAULT_LOGO_PATH, INVOICES_DIR
from ..utils.files import ensure_unique_path, safe_filename
from ..utils.money import money_text, to_money

BRAND = colors.HexColor("#14CFE0")
BRAND_DARK = colors.HexColor("#2F3746")
LIGHT_BG = colors.HexColor("#E7FBFF")
SOFT_ROW = colors.HexColor("#F3FDFF")
MUTED = colors.HexColor("#5E6C78")
BORDER = colors.HexColor("#BFEFF4")
DARK_TEXT = colors.HexColor("#202A36")


def _esc(text: Any) -> str:
    return escape(str(text or "")).replace("\n", "<br/>")


def _para(markup: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(markup or ""), style)


def _user_para(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_esc(text), style)


def _logo_flowable(settings: dict[str, Any], width: float = 26 * mm, height: float = 26 * mm):
    logo = settings.get("logo_path") or str(DEFAULT_LOGO_PATH)
    path = Path(logo)
    if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        try:
            img = Image(str(path), width=width, height=height)
            img.hAlign = "LEFT"
            return img
        except Exception:
            pass
    styles = getSampleStyleSheet()
    return Paragraph("<b>LOGO</b>", ParagraphStyle("logo", parent=styles["Normal"], textColor=colors.white, backColor=BRAND, alignment=TA_CENTER, fontSize=12, leading=20))


def _draw_footer(canvas, doc, settings: dict[str, Any]) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    footer = settings.get("footer_note") or "Thank you for your business."
    canvas.drawCentredString(A4[0] / 2, 7 * mm, footer[:120])
    canvas.restoreState()


def build_invoice_pdf(invoice: dict[str, Any], items: list[dict[str, Any]], settings: dict[str, Any]) -> str:
    invoice_no = invoice["invoice_no"]
    try:
        inv_date = datetime.fromisoformat(invoice.get("invoice_date") or datetime.now().date().isoformat())
        folder_name = inv_date.strftime("%Y-%m")
    except Exception:
        folder_name = datetime.now().strftime("%Y-%m")

    output_dir = INVOICES_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = ensure_unique_path(output_dir / f"{safe_filename(invoice_no)}.pdf")

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"Invoice {invoice_no}",
        author=settings.get("shop_name") or "NovaBill Laundry",
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NormalPro", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=DARK_TEXT)
    small = ParagraphStyle("SmallPro", parent=normal, fontSize=8, leading=10, textColor=MUTED)
    tiny = ParagraphStyle("TinyPro", parent=normal, fontSize=7.5, leading=9, textColor=MUTED)
    title = ParagraphStyle("InvoiceTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=BRAND_DARK, alignment=TA_RIGHT)
    subheading = ParagraphStyle("SubheadingPro", parent=normal, fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=BRAND_DARK)
    right = ParagraphStyle("RightPro", parent=normal, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("RightBold", parent=right, fontName="Helvetica-Bold", textColor=BRAND_DARK)

    story: list[Any] = []
    currency = settings.get("currency", "PKR")

    shop_name = settings.get("shop_name") or "Laundry Business"
    tagline = settings.get("shop_tagline") or "Professional Laundry Service"
    contact_lines = [settings.get("shop_address"), settings.get("shop_phone"), settings.get("shop_email")]
    contact_html = "<br/>".join(_esc(x) for x in contact_lines if x)

    shop_markup = f"<b>{_esc(shop_name)}</b><br/><font color='#5E6C78'>{_esc(tagline)}</font>"
    if contact_html:
        shop_markup += f"<br/>{contact_html}"

    header_left = Table([[_logo_flowable(settings), _para(shop_markup, normal)]], colWidths=[31 * mm, 78 * mm])
    header_left.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    meta_lines = [
        f"<b>INVOICE</b>",
        f"<font size='10'>#{_esc(invoice_no)}</font>",
        f"<font color='#5E6C78'>Date: {_esc(invoice.get('invoice_date') or '')}</font>",
    ]
    if invoice.get("due_date"):
        meta_lines.append(f"<font color='#5E6C78'>Due: {_esc(invoice.get('due_date'))}</font>")
    header = Table([[header_left, _para("<br/>".join(meta_lines), title)]], colWidths=[112 * mm, 66 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header)

    # Divider
    divider = Table([[""]], colWidths=[178 * mm], rowHeights=[1.2 * mm])
    divider.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND)]))
    story.append(divider)
    story.append(Spacer(1, 7 * mm))

    customer_lines = [f"<b>{_esc(invoice.get('customer_name') or '')}</b>"]
    if invoice.get("customer_phone"):
        customer_lines.append(f"Phone: {_esc(invoice.get('customer_phone'))}")
    if invoice.get("customer_email"):
        customer_lines.append(f"Email: {_esc(invoice.get('customer_email'))}")
    if invoice.get("customer_address"):
        customer_lines.append(f"Address: {_esc(invoice.get('customer_address'))}")

    status = invoice.get("payment_status") or "Unpaid"
    payment_html = (
        f"Status: <b>{_esc(status)}</b><br/>"
        f"Method: {_esc(invoice.get('payment_method') or '-')}<br/>"
        f"Paid: {money_text(invoice.get('paid_amount'), currency)}<br/>"
        f"Balance: <b>{money_text(invoice.get('balance'), currency)}</b>"
    )

    info_box = Table([
        [_para("BILL TO", subheading), _para("PAYMENT", subheading)],
        [_para("<br/>".join(customer_lines), normal), _para(payment_html, normal)],
    ], colWidths=[91 * mm, 87 * mm])
    info_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DARK),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(info_box)
    story.append(Spacer(1, 8 * mm))

    table_data: list[list[Any]] = [["#", "Service / Item", "Qty", "Unit Price", "Total"]]
    for idx, item in enumerate(items, 1):
        qty = to_money(item.get("quantity"))
        table_data.append([
            str(idx),
            _user_para(item.get("description") or "Laundry Service", normal),
            f"{qty:g}",
            money_text(item.get("unit_price"), currency),
            money_text(item.get("line_total"), currency),
        ])

    items_table = Table(table_data, colWidths=[10 * mm, 78 * mm, 18 * mm, 35 * mm, 37 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT_ROW]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 6 * mm))

    totals_data = [
        ["Subtotal", money_text(invoice.get("subtotal"), currency)],
        ["Discount", f"- {money_text(invoice.get('discount'), currency)}"],
        [f"Tax ({to_money(invoice.get('tax_rate')):g}%)", money_text(invoice.get("tax_amount"), currency)],
        ["Grand Total", money_text(invoice.get("total"), currency)],
        ["Paid", money_text(invoice.get("paid_amount"), currency)],
        ["Balance", money_text(invoice.get("balance"), currency)],
    ]
    totals = Table(totals_data, colWidths=[35 * mm, 42 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("BACKGROUND", (0, 3), (-1, 3), BRAND_DARK),
        ("TEXTCOLOR", (0, 3), (-1, 3), colors.white),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
        ("BACKGROUND", (0, 5), (-1, 5), LIGHT_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(totals)
    story.append(Spacer(1, 8 * mm))

    if invoice.get("notes") or settings.get("terms_note"):
        note_text = ""
        if invoice.get("notes"):
            note_text += f"<b>Invoice Notes:</b><br/>{_esc(invoice.get('notes'))}<br/><br/>"
        if settings.get("terms_note"):
            note_text += f"<b>Terms:</b><br/>{_esc(settings.get('terms_note'))}"
        notes_table = Table([[_para(note_text, small)]], colWidths=[178 * mm])
        notes_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(notes_table)
        story.append(Spacer(1, 5 * mm))

    doc.build(story, onFirstPage=lambda c, d: _draw_footer(c, d, settings), onLaterPages=lambda c, d: _draw_footer(c, d, settings))
    return str(pdf_path)
