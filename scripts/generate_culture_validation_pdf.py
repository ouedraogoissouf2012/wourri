"""Génère un formulaire PDF remplissable de pré-validation native par culture.

Généralisation paramétrable du générateur mil (#55). Un même moteur de mise en
page produit un PDF par culture (coton, banane, tomate, ...), au format validé :
  - Français de référence
  - VERSION A · Brouillon consolidé (draft v3)
  - VERSION B · Ancienne PR (optionnelle : absente = format mono-version hévéa)
  - Alerte de l'audit (mots maliens, incohérences)
  - Repère vérifié (termes attestés)
  - Décision : cases A exacte / B exacte / Correction nécessaire
  - Champ Correction dioula complète (remplissable)
  - Champ Commentaire (remplissable)

Le fichier source (JSON draft) contient uniquement des brouillons. Ce script ne
modifie jamais le corpus IVR de production ni les drafts.

Réutilise le socle du générateur mil : police Unicode (ɛ ɔ ɲ ŋ), champs de
formulaire AcroForm via reportlab + pypdf.

Différences avec le générateur mil :
  - Aucun nombre d'entrées codé en dur : le JSON déclare son propre décompte.
  - VERSION B optionnelle par entrée (mono-version propre quand absente).
  - Textes de couverture / pied de page / préfixe de champ pilotés par le JSON.

Usage :
    uv run --with reportlab --with pypdf \
        python scripts/generate_culture_validation_pdf.py \
        --input data/issue_56_coton_validation_draft.json \
        --output "C:/.../issue-56-coton-prevalidation.pdf"
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

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 18 * mm
FOOTER_Y = 10 * mm

INK = HexColor("#172033")
MUTED = HexColor("#607089")
GREEN = HexColor("#137553")
AMBER_INK = HexColor("#8A5B00")
PALE_GREEN = HexColor("#EAF6F1")
PALE_BLUE = HexColor("#EEF4FF")
PALE_AMBER = HexColor("#FFF7E8")
PALE_GREY = HexColor("#F2F5FA")
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


def measure_paragraph(
    text: str,
    *,
    width: float,
    font_size: float,
    leading: float,
) -> float:
    """Mesure la hauteur d'un paragraphe sans le dessiner."""
    style = ParagraphStyle(
        name="wourri-measure",
        fontName="Wourri",
        fontSize=font_size,
        leading=leading,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    block = Paragraph(html.escape(text), style)
    _, height = block.wrap(width, PAGE_HEIGHT)
    return height


def draw_footer(pdf: canvas.Canvas, page_number: int, footer_label: str) -> None:
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(MARGIN_X, FOOTER_Y + 5 * mm, PAGE_WIDTH - MARGIN_X, FOOTER_Y + 5 * mm)
    pdf.setFont("Wourri", 7.8)
    pdf.setFillColor(MUTED)
    pdf.drawString(MARGIN_X, FOOTER_Y, footer_label)
    pdf.drawRightString(PAGE_WIDTH - MARGIN_X, FOOTER_Y, f"Page {page_number}")


def draw_box(
    pdf: canvas.Canvas,
    *,
    x: float,
    y_top: float,
    width: float,
    height: float,
    fill,
    stroke=BORDER,
) -> None:
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.setLineWidth(0.6)
    pdf.rect(x, y_top - height, width, height, fill=1, stroke=1)


def draw_cover(pdf: canvas.Canvas, data: dict, page_number: int) -> None:
    content_width = PAGE_WIDTH - 2 * MARGIN_X
    issue = data["issue"]
    crop_label = data["crop_label"]
    crop_term = data.get("crop_term", "")
    items = data["items"]
    has_version_b = any(item.get("version_b") for item in items)
    footer_label = data["footer_label"]

    y = PAGE_HEIGHT - 24 * mm

    pdf.setFillColor(INK)
    pdf.setFont("Wourri-Bold", 24)
    pdf.drawString(MARGIN_X, y, f"Issue #{issue} - Pré-validation {crop_label}")
    y -= 12 * mm
    pdf.setFont("Wourri", 12)
    pdf.setFillColor(MUTED)
    if has_version_b:
        subtitle = (
            f"{len(items)} entrées {crop_label}"
            + (f" ({crop_term})" if crop_term else "")
            + " : comparaison Version A / Version B"
        )
    else:
        subtitle = (
            f"{len(items)} entrées {crop_label}"
            + (f" ({crop_term})" if crop_term else "")
            + " : Version A (brouillon consolidé)"
        )
    pdf.drawString(MARGIN_X, y, subtitle)

    y -= 11 * mm
    draw_box(
        pdf,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        height=25 * mm,
        fill=PALE_AMBER,
    )
    if has_version_b:
        important = (
            "Important : les deux versions dioula (A = brouillon consolidé du draft "
            "v3, B = ancienne PR proposée) sont des propositions non validées. Elles "
            "ne figurent pas dans le corpus IVR de production. Le validateur natif "
            "dioula CI tranche entrée par entrée."
        )
    else:
        important = (
            "Important : la version dioula A (brouillon consolidé du draft v3) est une "
            "proposition non validée. Elle ne figure pas dans le corpus IVR de "
            "production. Le validateur natif dioula CI tranche entrée par entrée."
        )
    paragraph(
        pdf,
        important,
        x=MARGIN_X + 5 * mm,
        y_top=y - 5 * mm,
        width=content_width - 10 * mm,
        font_size=10.5,
        leading=14,
    )

    y -= 33 * mm
    pdf.setFillColor(GREEN)
    pdf.setFont("Wourri-Bold", 15)
    pdf.drawString(MARGIN_X, y, f"Terme {crop_label} déjà retenu")
    y -= 7 * mm
    draw_box(
        pdf,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        height=14 * mm,
        fill=PALE_GREEN,
    )
    paragraph(
        pdf,
        data.get(
            "crop_term_note",
            f"{crop_label} = {crop_term}. Vérifiez son emploi dans chaque phrase.",
        ),
        x=MARGIN_X + 5 * mm,
        y_top=y - 4.5 * mm,
        width=content_width - 10 * mm,
        font_size=10.5,
        leading=14,
    )

    y -= 24 * mm
    pdf.setFillColor(AMBER_INK)
    pdf.setFont("Wourri-Bold", 15)
    pdf.drawString(MARGIN_X, y, "Mots maliens bannis à repérer")
    y -= 7 * mm
    draw_box(
        pdf,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        height=20 * mm,
        fill=PALE_AMBER,
    )
    bans = data.get("audit_basis", {}).get("mots_maliens_bannis", {})
    ban_text = " ; ".join(f"{k} {v}" for k, v in bans.items())
    paragraph(
        pdf,
        ban_text or "karo→kalo ; sugu→lɔgɔ ; waati→tuma ; kosɛbɛ→caman",
        x=MARGIN_X + 5 * mm,
        y_top=y - 4.5 * mm,
        width=content_width - 10 * mm,
        font_size=9.6,
        leading=13,
    )

    y -= 30 * mm
    pdf.setFillColor(GREEN)
    pdf.setFont("Wourri-Bold", 15)
    pdf.drawString(MARGIN_X, y, "Mode d'emploi")
    y -= 8 * mm
    if has_version_b:
        instructions = [
            "1. Pour chaque entrée, choisir UNE décision : A exacte, B exacte ou "
            "Correction nécessaire.",
            "2. Si une correction est nécessaire, écrire la formulation dioula CI "
            "complète dans le champ prévu.",
            "3. Utiliser le commentaire pour justifier (mot malien, sens, grammaire "
            "SOV, orthographe).",
            "4. Les champs sont remplissables dans un lecteur PDF compatible AcroForm.",
        ]
    else:
        instructions = [
            "1. Pour chaque entrée, choisir UNE décision : A exacte ou "
            "Correction nécessaire (aucune ancienne PR pour cette culture).",
            "2. Si une correction est nécessaire, écrire la formulation dioula CI "
            "complète dans le champ prévu.",
            "3. Utiliser le commentaire pour justifier (mot malien, sens, grammaire "
            "SOV, orthographe).",
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

    draw_footer(pdf, page_number, footer_label)


def draw_labeled_block(
    pdf: canvas.Canvas,
    *,
    label: str,
    body: str,
    label_color,
    fill,
    x: float,
    y_top: float,
    width: float,
    body_font_size: float = 9.5,
    body_leading: float = 12.5,
) -> float:
    """Dessine un bloc étiqueté (label en gras + corps) dans une boîte teintée.

    Retourne la hauteur totale consommée.
    """
    inner_pad = 3 * mm
    inner_width = width - 2 * inner_pad
    label_height = 4.4 * mm
    body_height = measure_paragraph(
        body,
        width=inner_width,
        font_size=body_font_size,
        leading=body_leading,
    )
    box_height = label_height + body_height + 3.5 * mm

    draw_box(pdf, x=x, y_top=y_top, width=width, height=box_height, fill=fill)

    pdf.setFillColor(label_color)
    pdf.setFont("Wourri-Bold", 8.4)
    pdf.drawString(x + inner_pad, y_top - 4 * mm, label)

    paragraph(
        pdf,
        body,
        x=x + inner_pad,
        y_top=y_top - label_height - 1 * mm,
        width=inner_width,
        font_size=body_font_size,
        leading=body_leading,
    )
    return box_height


def draw_item_page(
    pdf: canvas.Canvas,
    item: dict,
    *,
    sequence: int,
    total: int,
    page_number: int,
    crop_label: str,
    field_prefix_base: str,
    footer_label: str,
) -> None:
    content_width = PAGE_WIDTH - 2 * MARGIN_X
    has_version_b = bool(item.get("version_b"))

    # En-tête de page
    pdf.setFillColor(GREEN)
    pdf.setFont("Wourri-Bold", 16)
    pdf.drawString(
        MARGIN_X, PAGE_HEIGHT - 18 * mm, f"{crop_label.capitalize()} - {item['id']}"
    )
    pdf.setFillColor(MUTED)
    pdf.setFont("Wourri", 8.8)
    pdf.drawRightString(
        PAGE_WIDTH - MARGIN_X,
        PAGE_HEIGHT - 18 * mm,
        f"{item['intent']}   -   Entrée {sequence} sur {total}",
    )
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.6)
    pdf.line(
        MARGIN_X,
        PAGE_HEIGHT - 20 * mm,
        PAGE_WIDTH - MARGIN_X,
        PAGE_HEIGHT - 20 * mm,
    )

    y = PAGE_HEIGHT - 26 * mm
    gap = 3 * mm

    # Français de référence
    y -= draw_labeled_block(
        pdf,
        label="FRANÇAIS DE RÉFÉRENCE",
        body=item["french"],
        label_color=INK,
        fill=PALE_GREY,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
    )
    y -= gap

    # Version A · brouillon consolidé
    y -= draw_labeled_block(
        pdf,
        label="VERSION A · BROUILLON CONSOLIDÉ (draft v3)",
        body=item["version_a"],
        label_color=GREEN,
        fill=PALE_GREEN,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
    )
    y -= gap

    # Version B · ancienne PR (optionnelle)
    if has_version_b:
        version_b_label = "VERSION B · ANCIENNE PR"
        if item.get("version_b_pr"):
            version_b_label = f"VERSION B · ANCIENNE PR ({item['version_b_pr']})"
        y -= draw_labeled_block(
            pdf,
            label=version_b_label,
            body=item["version_b"],
            label_color=HexColor("#1E5FBF"),
            fill=PALE_BLUE,
            x=MARGIN_X,
            y_top=y,
            width=content_width,
        )
        y -= gap

    # Alerte de l'audit
    y -= draw_labeled_block(
        pdf,
        label="ALERTE DE L'AUDIT",
        body=item["alerte_audit"],
        label_color=AMBER_INK,
        fill=PALE_AMBER,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        body_font_size=8.8,
        body_leading=11.8,
    )
    y -= gap

    # Repère vérifié
    y -= draw_labeled_block(
        pdf,
        label="REPÈRE VÉRIFIÉ",
        body=item["repere_verifie"],
        label_color=MUTED,
        fill=white,
        x=MARGIN_X,
        y_top=y,
        width=content_width,
        body_font_size=8.8,
        body_leading=11.8,
    )
    y -= gap + 1 * mm

    # Décision du validateur : cases A exacte / (B exacte) / Correction
    field_prefix = f"{field_prefix_base}_{sequence:02d}"
    pdf.setFillColor(INK)
    pdf.setFont("Wourri-Bold", 9.6)
    pdf.drawString(MARGIN_X, y, "DÉCISION DU VALIDATEUR :")
    y -= 6 * mm

    radio_size = 3.6 * mm
    radio_y = y
    if has_version_b:
        choices = [
            ("a_exacte", "Version A exacte", MARGIN_X),
            ("b_exacte", "Version B exacte", MARGIN_X + 55 * mm),
            ("correction", "Correction nécessaire", MARGIN_X + 110 * mm),
        ]
    else:
        choices = [
            ("a_exacte", "Version A exacte", MARGIN_X),
            ("correction", "Correction nécessaire", MARGIN_X + 55 * mm),
        ]
    pdf.setFont("Wourri", 9)
    for value, label, cx in choices:
        pdf.acroForm.radio(
            name=f"{field_prefix}_decision",
            value=value,
            selected=False,
            x=cx,
            y=radio_y - 1.2 * mm,
            buttonStyle="check",
            shape="square",
            borderColor=MUTED,
            fillColor=white,
            textColor=GREEN,
            size=radio_size,
        )
        pdf.setFillColor(INK)
        pdf.drawString(cx + radio_size + 1.5 * mm, radio_y, label)
    y -= 9 * mm

    # Champ Correction dioula complète
    pdf.setFillColor(INK)
    pdf.setFont("Wourri-Bold", 8.8)
    pdf.drawString(MARGIN_X, y, "CORRECTION DIOULA COMPLÈTE :")
    y -= 3 * mm
    correction_height = 26 * mm
    pdf.acroForm.textfield(
        name=f"{field_prefix}_correction",
        tooltip=f"Correction dioula complète de {item['id']}",
        x=MARGIN_X,
        y=y - correction_height,
        width=content_width,
        height=correction_height,
        borderStyle="solid",
        borderColor=MUTED,
        borderWidth=0.6,
        fillColor=white,
        textColor=INK,
        forceBorder=True,
        fontName="Helvetica",
        fontSize=10,
        fieldFlags="multiline",
    )
    y -= correction_height + 4 * mm

    # Champ Commentaire
    pdf.setFillColor(INK)
    pdf.setFont("Wourri-Bold", 8.8)
    pdf.drawString(MARGIN_X, y, "COMMENTAIRE :")
    y -= 3 * mm
    comment_height = 20 * mm
    pdf.acroForm.textfield(
        name=f"{field_prefix}_commentaire",
        tooltip=f"Commentaire du validateur pour {item['id']}",
        x=MARGIN_X,
        y=y - comment_height,
        width=content_width,
        height=comment_height,
        borderStyle="solid",
        borderColor=MUTED,
        borderWidth=0.6,
        fillColor=white,
        textColor=INK,
        forceBorder=True,
        fontName="Helvetica",
        fontSize=10,
        fieldFlags="multiline",
    )

    draw_footer(pdf, page_number, footer_label)


def build_pdf(
    input_path: Path,
    output_path: Path,
    *,
    regular_font: Path | None = None,
    bold_font: Path | None = None,
) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if data.get("status") != "pending_native_validation":
        raise ValueError("Le générateur attend un brouillon en validation native.")
    items = data["items"]
    if not items:
        raise ValueError("Le formulaire ne contient aucune entrée.")
    declared = data.get("item_count")
    if declared is not None and declared != len(items):
        raise ValueError(
            f"item_count déclaré ({declared}) != entrées réelles ({len(items)})."
        )
    for item in items:
        for key in ("id", "intent", "french", "version_a", "alerte_audit", "repere_verifie"):
            if not item.get(key):
                raise ValueError(f"Champ '{key}' manquant pour {item.get('id')}.")

    register_fonts(regular_font, bold_font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop_label = data["crop_label"]
    pdf = canvas.Canvas(str(output_path), pagesize=A4, pageCompression=1)
    pdf.setTitle(
        f"Issue {data['issue']} - Pré-validation {crop_label} dioula - "
        "formulaire remplissable"
    )
    pdf.setAuthor("Projet Wourri")
    pdf.setSubject(
        f"Pré-validation native de {len(items)} entrées IVR {crop_label}"
    )
    pdf.setKeywords(
        f"Wourri, Dioula, {crop_label}, validation, corpus, formulaire PDF"
    )

    footer_label = data["footer_label"]
    field_prefix_base = data["field_prefix_base"]

    draw_cover(pdf, data, page_number=1)
    pdf.showPage()

    total = len(items)
    for index, item in enumerate(items):
        draw_item_page(
            pdf,
            item,
            sequence=index + 1,
            total=total,
            page_number=index + 2,
            crop_label=crop_label,
            field_prefix_base=field_prefix_base,
            footer_label=footer_label,
        )
        pdf.showPage()

    pdf.save()
    configure_unicode_form_font(output_path)


def configure_unicode_form_font(output_path: Path) -> None:
    """Réutilise la fonte TrueType embarquée pour les champs de texte."""
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
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
