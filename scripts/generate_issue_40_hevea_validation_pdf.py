"""Génère le formulaire PDF remplissable de validation native hévéa (#40).

Le fichier source contient uniquement des brouillons. Ce script ne modifie
jamais le corpus IVR de production.

Usage :
    uv run --with reportlab --with pypdf \
        python scripts/generate_issue_40_hevea_validation_pdf.py
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
from pathlib import Path

import reportlab
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "issue_40_hevea_validation_draft.json"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "output"
    / "pdf"
    / "issue-40-validation-hevea-dioula-remplissable.pdf"
)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 18 * mm
FOOTER_Y = 10 * mm

INK = HexColor("#172033")
MUTED = HexColor("#607089")
GREEN = HexColor("#137553")
PALE_GREEN = HexColor("#EAF6F1")
PALE_BLUE = HexColor("#EEF4FF")
PALE_AMBER = HexColor("#FFF7E8")
BORDER = HexColor("#CBD7E8")
FORM_FONT_NAME = "/Wourri"
FORM_DEFAULT_APPEARANCE = f"{FORM_FONT_NAME} 9 Tf 0 g"


def find_font_file(*, bold: bool, explicit: Path | None) -> Path:
    """Trouve une fonte Unicode sans imposer un chemin propre au dépôt."""
    if explicit:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    windows_dir = os.environ.get("WINDIR")
    if windows_dir:
        filename = "arialbd.ttf" if bold else "arial.ttf"
        path = Path(windows_dir) / "Fonts" / filename
        if path.is_file():
            return path

    fc_match = shutil.which("fc-match")
    if fc_match:
        family = "DejaVu Sans:style=Bold" if bold else "DejaVu Sans"
        result = subprocess.run(
            [fc_match, "-f", "%{file}", family],
            check=True,
            capture_output=True,
            text=True,
        )
        path = Path(result.stdout.strip())
        if path.is_file():
            return path

    fonts_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    fallback = fonts_dir / ("VeraBd.ttf" if bold else "Vera.ttf")
    if fallback.is_file():
        return fallback
    raise FileNotFoundError("Aucune fonte Unicode utilisable n'a été trouvée.")


def register_fonts(
    regular_font: Path | None = None,
    bold_font: Path | None = None,
) -> None:
    """Enregistre les fontes Unicode utilisées pour le texte statique."""
    pdfmetrics.registerFont(
        TTFont("Wourri", find_font_file(bold=False, explicit=regular_font))
    )
    pdfmetrics.registerFont(
        TTFont("Wourri-Bold", find_font_file(bold=True, explicit=bold_font))
    )


def paragraph(
    pdf: canvas.Canvas,
    text: str,
    *,
    x: float,
    y_top: float,
    width: float,
    font_size: float = 10.5,
    leading: float = 14,
    color=INK,
    bold_prefix: str | None = None,
) -> float:
    """Dessine un paragraphe et retourne sa hauteur."""
    if bold_prefix and text.startswith(bold_prefix):
        body = html.escape(text[len(bold_prefix) :])
        markup = f"<b>{html.escape(bold_prefix)}</b>{body}"
    else:
        markup = html.escape(text)
    style = ParagraphStyle(
        name="wourri",
        fontName="Wourri",
        fontSize=font_size,
        leading=leading,
        textColor=color,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    block = Paragraph(markup, style)
    _, height = block.wrap(width, PAGE_HEIGHT)
    block.drawOn(pdf, x, y_top - height)
    return height


def draw_footer(pdf: canvas.Canvas, page_number: int) -> None:
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(MARGIN_X, FOOTER_Y + 5 * mm, PAGE_WIDTH - MARGIN_X, FOOTER_Y + 5 * mm)
    pdf.setFont("Wourri", 7.8)
    pdf.setFillColor(MUTED)
    pdf.drawString(
        MARGIN_X,
        FOOTER_Y,
        "Wourri - Issue #40 - Brouillon, ne pas intégrer avant validation native",
    )
    pdf.drawRightString(PAGE_WIDTH - MARGIN_X, FOOTER_Y, f"Page {page_number}")


def draw_box(
    pdf: canvas.Canvas,
    *,
    x: float,
    y_top: float,
    width: float,
    height: float,
    fill,
) -> None:
    pdf.setFillColor(fill)
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.6)
    pdf.rect(x, y_top - height, width, height, fill=1, stroke=1)


def draw_cover(pdf: canvas.Canvas, data: dict, page_number: int) -> None:
    content_width = PAGE_WIDTH - 2 * MARGIN_X
    y = PAGE_HEIGHT - 24 * mm

    pdf.setFillColor(INK)
    pdf.setFont("Wourri-Bold", 24)
    pdf.drawString(MARGIN_X, y, "Issue #40 - Validation hévéa")
    y -= 12 * mm
    pdf.setFont("Wourri", 12)
    pdf.setFillColor(MUTED)
    pdf.drawString(
        MARGIN_X,
        y,
        "15 propositions dioula pour compléter le corpus IVR hévéa",
    )

    y -= 11 * mm
    draw_box(
        pdf,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        height=21 * mm,
        fill=PALE_AMBER,
    )
    paragraph(
        pdf,
        "Important : les phrases dioula sont des brouillons. Elles ne sont pas "
        "validées et ne figurent pas dans le corpus IVR de production.",
        x=MARGIN_X + 5 * mm,
        y_top=y - 5 * mm,
        width=content_width - 10 * mm,
        font_size=10.5,
        leading=14,
    )

    y -= 31 * mm
    pdf.setFillColor(GREEN)
    pdf.setFont("Wourri-Bold", 15)
    pdf.drawString(MARGIN_X, y, "Termes hévéa déjà validés")
    y -= 7 * mm
    draw_box(
        pdf,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        height=19 * mm,
        fill=PALE_GREEN,
    )
    paragraph(
        pdf,
        "mana su et mána yiri : deux synonymes valides, sans terme principal.",
        x=MARGIN_X + 5 * mm,
        y_top=y - 5 * mm,
        width=content_width - 10 * mm,
        font_size=10.5,
        leading=14,
    )

    y -= 29 * mm
    pdf.setFillColor(GREEN)
    pdf.setFont("Wourri-Bold", 15)
    pdf.drawString(MARGIN_X, y, "Mode d'emploi")
    y -= 8 * mm
    instructions = [
        "1. Pour chaque phrase, choisir une seule décision : Valide ou À corriger.",
        "2. Si la phrase est à corriger, écrire la formulation dioula CI recommandée.",
        "3. Vérifier le sens, la grammaire SOV, le registre et les emprunts techniques.",
        "4. Les champs sont remplissables dans un lecteur PDF compatible AcroForm.",
    ]
    for instruction in instructions:
        height = paragraph(
            pdf,
            instruction,
            x=MARGIN_X,
            y_top=y,
            width=content_width,
            font_size=10.2,
            leading=13,
        )
        y -= height + 2 * mm

    y -= 6 * mm
    pdf.setFillColor(GREEN)
    pdf.setFont("Wourri-Bold", 15)
    pdf.drawString(MARGIN_X, y, "Sources agronomiques")
    y -= 8 * mm
    for code, source in data["source_codes"].items():
        label = f"{code} : {source['title']} ({source['organization']})."
        height = paragraph(
            pdf,
            label,
            x=MARGIN_X,
            y_top=y,
            width=content_width,
            font_size=9.2,
            leading=12,
        )
        y -= height + 1.5 * mm

    y -= 4 * mm
    draw_box(
        pdf,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        height=23 * mm,
        fill=PALE_BLUE,
    )
    paragraph(
        pdf,
        "Les termes techniques empruntés (saignée, latex, coagulum, encoche "
        "sèche, mycélium, etc.) doivent eux aussi être confirmés ou remplacés "
        "par l'usage naturel en dioula ivoirien.",
        x=MARGIN_X + 5 * mm,
        y_top=y - 5 * mm,
        width=content_width - 10 * mm,
        font_size=9.6,
        leading=13,
    )

    # Force l'inclusion des glyphes usuels du dioula dans la fonte TrueType
    # sous-ensemblée. Le texte est blanc et placé hors de la zone utile.
    pdf.setFillColor(white)
    pdf.setFont("Wourri", 1)
    pdf.drawString(
        0,
        0,
        "a à á â ä e è é ê ë ɛ ɛ̀ ɛ́ i ì í î ï n ɲ ŋ o ò ó ô ö ɔ ɔ̀ ɔ́ "
        "u ù ú û ü A À Á E Ɛ I Ɲ Ŋ O Ɔ U",
    )

    draw_footer(pdf, page_number)


def draw_item_card(
    pdf: canvas.Canvas,
    item: dict,
    *,
    sequence: int,
    x: float,
    y_top: float,
    width: float,
    height: float,
    fill,
) -> None:
    draw_box(pdf, x=x, y_top=y_top, width=width, height=height, fill=fill)
    inner_x = x + 5 * mm
    inner_width = width - 10 * mm
    y = y_top - 5 * mm

    header = (
        f"{sequence:02d} - {item['intent']} - "
        f"{item['source']} p.{item['source_page']}"
    )
    header_height = paragraph(
        pdf,
        header,
        x=inner_x,
        y_top=y,
        width=inner_width,
        font_size=8.2,
        leading=10.5,
        color=MUTED,
    )
    y -= header_height + 3 * mm

    french_height = paragraph(
        pdf,
        f"Français : {item['french']}",
        x=inner_x,
        y_top=y,
        width=inner_width,
        font_size=9.5,
        leading=12.5,
        bold_prefix="Français : ",
    )
    y -= french_height + 3 * mm

    dioula_height = paragraph(
        pdf,
        f"Dioula proposé : {item['dioula_draft']}",
        x=inner_x,
        y_top=y,
        width=inner_width,
        font_size=9.5,
        leading=12.5,
        bold_prefix="Dioula proposé : ",
    )
    y -= dioula_height + 4 * mm

    field_prefix = f"H_{sequence:02d}"
    radio_y = y - 1.2 * mm
    pdf.setFillColor(INK)
    pdf.setFont("Wourri", 9)
    pdf.drawString(inner_x, radio_y, "Décision :")

    valide_x = inner_x + 25 * mm
    radio_size = 3.5 * mm
    radio_bottom = radio_y - 1.2 * mm
    pdf.acroForm.radio(
        name=f"{field_prefix}_decision",
        value="valide",
        selected=False,
        x=valide_x,
        y=radio_bottom,
        buttonStyle="circle",
        shape="circle",
        borderColor=MUTED,
        fillColor=white,
        textColor=GREEN,
        size=radio_size,
    )
    pdf.drawString(valide_x + 5 * mm, radio_y, "Valide")

    correction_x = valide_x + 31 * mm
    pdf.acroForm.radio(
        name=f"{field_prefix}_decision",
        value="a_corriger",
        selected=False,
        x=correction_x,
        y=radio_bottom,
        buttonStyle="circle",
        shape="circle",
        borderColor=MUTED,
        fillColor=white,
        textColor=GREEN,
        size=radio_size,
    )
    pdf.drawString(correction_x + 5 * mm, radio_y, "À corriger")

    text_y = y - 15 * mm
    pdf.setFont("Wourri", 8.8)
    pdf.drawString(inner_x, text_y + 7 * mm, "Correction dioula :")
    pdf.acroForm.textfield(
        name=f"{field_prefix}_correction",
        tooltip=f"Correction dioula de {item['id']}",
        x=inner_x,
        y=text_y - 4 * mm,
        width=inner_width,
        height=10 * mm,
        borderStyle="underlined",
        borderColor=MUTED,
        fillColor=white,
        textColor=INK,
        forceBorder=True,
        fontName="Helvetica",
        fontSize=9,
        fieldFlags="multiline",
    )


def draw_items(pdf: canvas.Canvas, data: dict, first_page_number: int) -> int:
    content_width = PAGE_WIDTH - 2 * MARGIN_X
    items = data["items"]
    page_number = first_page_number
    items_per_page = 3
    card_height = 72 * mm
    card_gap = 4 * mm

    for page_start in range(0, len(items), items_per_page):
        page_items = items[page_start : page_start + items_per_page]
        pdf.setFillColor(GREEN)
        pdf.setFont("Wourri-Bold", 17)
        pdf.drawString(MARGIN_X, PAGE_HEIGHT - 19 * mm, "H - Hévéa")
        pdf.setFillColor(MUTED)
        pdf.setFont("Wourri", 8.8)
        pdf.drawRightString(
            PAGE_WIDTH - MARGIN_X,
            PAGE_HEIGHT - 19 * mm,
            f"Propositions {page_start + 1} à {page_start + len(page_items)} sur 15",
        )

        y_top = PAGE_HEIGHT - 29 * mm
        for offset, item in enumerate(page_items):
            sequence = page_start + offset + 1
            draw_item_card(
                pdf,
                item,
                sequence=sequence,
                x=MARGIN_X,
                y_top=y_top,
                width=content_width,
                height=card_height,
                fill=white if sequence % 2 else PALE_BLUE,
            )
            y_top -= card_height + card_gap

        draw_footer(pdf, page_number)
        pdf.showPage()
        page_number += 1

    return page_number


def build_pdf(
    input_path: Path,
    output_path: Path,
    *,
    regular_font: Path | None = None,
    bold_font: Path | None = None,
) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if data["status"] != "pending_native_validation":
        raise ValueError("Le générateur attend un brouillon en validation native.")
    if len(data["items"]) != 15:
        raise ValueError("Le formulaire hévéa doit contenir exactement 15 propositions.")

    register_fonts(regular_font, bold_font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=A4, pageCompression=1)
    pdf.setTitle("Issue 40 - Validation hévéa dioula - formulaire remplissable")
    pdf.setAuthor("Projet Wourri")
    pdf.setSubject("Validation native de 15 brouillons IVR hévéa")
    pdf.setKeywords("Wourri, Dioula, hévéa, validation, corpus, formulaire PDF")

    draw_cover(pdf, data, page_number=1)
    pdf.showPage()
    draw_items(pdf, data, first_page_number=2)
    pdf.save()
    configure_unicode_form_font(output_path)


def configure_unicode_form_font(output_path: Path) -> None:
    """Réutilise la fonte TrueType embarquée pour les champs de correction."""
    reader = PdfReader(output_path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    regular_font_reference = None
    for page in writer.pages:
        font_resources = page.get("/Resources", {}).get("/Font", {})
        for font_reference in font_resources.values():
            font = font_reference.get_object()
            base_font = str(font.get("/BaseFont", ""))
            if font.get("/Subtype") == "/TrueType" and "Bold" not in base_font:
                regular_font_reference = font_reference
                break
        if regular_font_reference is not None:
            break
    if regular_font_reference is None:
        raise ValueError("Fonte TrueType Unicode régulière introuvable dans le PDF.")

    acroform = writer.root_object["/AcroForm"].get_object()
    default_resources = acroform.setdefault(
        NameObject("/DR"),
        DictionaryObject(),
    )
    form_fonts = default_resources.setdefault(
        NameObject("/Font"),
        DictionaryObject(),
    )
    form_fonts[NameObject(FORM_FONT_NAME)] = regular_font_reference
    acroform[NameObject("/DA")] = TextStringObject(FORM_DEFAULT_APPEARANCE)

    for page in writer.pages:
        for annotation_reference in page.get("/Annots", []):
            annotation = annotation_reference.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            parent = (
                annotation["/Parent"].get_object()
                if annotation.get("/Parent")
                else annotation
            )
            if parent.get("/FT") == "/Tx":
                annotation[NameObject("/DA")] = TextStringObject(
                    FORM_DEFAULT_APPEARANCE
                )

    temporary_path = output_path.with_suffix(".unicode.pdf")
    with temporary_path.open("wb") as stream:
        writer.write(stream)
    temporary_path.replace(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--font-regular", type=Path)
    parser.add_argument("--font-bold", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    build_pdf(
        arguments.input.resolve(),
        arguments.output.resolve(),
        regular_font=arguments.font_regular,
        bold_font=arguments.font_bold,
    )
    print(arguments.output.resolve())
