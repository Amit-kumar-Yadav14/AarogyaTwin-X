"""Generate local Day-5 architecture and presentation decks without dependencies.

Outputs editable PPTX files and simple printable PDFs under docs/. The content is
kept in this script so the export is reproducible and network-free.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import wrap
from xml.sax.saxutils import escape
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EMU_PER_INCH = 914400
SLIDE_W = 13.333 * EMU_PER_INCH
SLIDE_H = 7.5 * EMU_PER_INCH
PDF_W, PDF_H = 960, 540
NAVY = "14253D"
TEAL = "159B9A"
VIOLET = "7667E8"
INK = "26364D"
MUTED = "68758A"
PALE = "F4F7FA"


def esc(text: str) -> str:
    return escape(str(text), {"'": "&apos;", '"': "&quot;"})


def shape_id(start: int, offset: int) -> int:
    return start + offset


def rect_shape(shape_no: int, name: str, x: int, y: int, w: int, h: int, color: str) -> str:
    return f"""<p:sp><p:nvSpPr><p:cNvPr id=\"{shape_no}\" name=\"{esc(name)}\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"{x}\" y=\"{y}\"/><a:ext cx=\"{w}\" cy=\"{h}\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val=\"{color}\"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>"""


def text_shape(
    shape_no: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    paragraphs: list[dict[str, object]],
    default_size: int = 18,
    default_color: str = INK,
) -> str:
    body = []
    for item in paragraphs:
        text = str(item.get("text", ""))
        size = int(item.get("size", default_size))
        color = str(item.get("color", default_color))
        bold = " b=\"1\"" if item.get("bold") else ""
        bullet = "<a:buChar char=\"•\"/>" if item.get("bullet", True) else "<a:buNone/>"
        body.append(
            f"<a:p><a:pPr lvl=\"0\">{bullet}</a:pPr>"
            f"<a:r><a:rPr lang=\"en-US\" sz=\"{size * 100}\"{bold}><a:solidFill><a:srgbClr val=\"{color}\"/></a:solidFill><a:latin typeface=\"Aptos\"/></a:rPr><a:t>{esc(text)}</a:t></a:r>"
            f"<a:endParaRPr lang=\"en-US\" sz=\"{size * 100}\"/></a:p>"
        )
    return f"""<p:sp><p:nvSpPr><p:cNvPr id=\"{shape_no}\" name=\"{esc(name)}\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"{x}\" y=\"{y}\"/><a:ext cx=\"{w}\" cy=\"{h}\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap=\"square\" rtlCol=\"0\"/><a:lstStyle/>{''.join(body)}</p:txBody></p:sp>"""


def slide_xml(title: str, bullets: list[str], number: int, accent: str = TEAL) -> str:
    title_paragraph = [{"text": title, "bullet": False, "bold": True, "size": 28, "color": NAVY}]
    body_paragraphs = [{"text": line, "bullet": True, "size": 17, "color": INK} for line in bullets]
    footer_paragraph = [{"text": f"AarogyaTwin-X  |  synthetic research prototype  |  {number}", "bullet": False, "size": 9, "color": MUTED}]
    tree = (
        f"<p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
        f"<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
        f"{rect_shape(2, 'background', 0, 0, int(SLIDE_W), int(SLIDE_H), 'FFFFFF')}"
        f"{rect_shape(3, 'accent', 0, 0, int(SLIDE_W), int(0.18 * EMU_PER_INCH), accent)}"
        f"{text_shape(4, 'title', int(0.65 * EMU_PER_INCH), int(0.48 * EMU_PER_INCH), int(12 * EMU_PER_INCH), int(0.7 * EMU_PER_INCH), title_paragraph, 28, NAVY)}"
        f"{text_shape(5, 'body', int(0.82 * EMU_PER_INCH), int(1.38 * EMU_PER_INCH), int(11.7 * EMU_PER_INCH), int(5.25 * EMU_PER_INCH), body_paragraphs, 17, INK)}"
        f"{text_shape(6, 'footer', int(0.65 * EMU_PER_INCH), int(7.12 * EMU_PER_INCH), int(12 * EMU_PER_INCH), int(0.2 * EMU_PER_INCH), footer_paragraph, 9, MUTED)}"
    )
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree>{tree}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"""


def pptx_parts(slides: list[tuple[str, list[str]]]) -> dict[str, bytes]:
    ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts: dict[str, bytes] = {}
    overrides = [
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>',
        '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>',
        '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>',
    ]
    pres_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>']
    sld_ids = []
    for index, _ in enumerate(slides, 1):
        overrides.append(f'<Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
        pres_rels.append(f'<Relationship Id="rId{index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>')
        sld_ids.append(f'<p:sldId id="{255 + index}" r:id="rId{index + 1}"/>')
        parts[f'ppt/slides/slide{index}.xml'] = slide_xml(slides[index - 1][0], slides[index - 1][1], index).encode()
    parts['[Content_Types].xml'] = (f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>{''.join(overrides)}</Types>''').encode()
    parts['_rels/.rels'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>'''
    parts['ppt/presentation.xml'] = (f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{rel}" xmlns:p="{ns}"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{''.join(sld_ids)}</p:sldIdLst><p:sldSz cx="12192000" cy="6858000" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle/></p:presentation>''').encode()
    parts['ppt/_rels/presentation.xml.rels'] = (f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(pres_rels)}</Relationships>''').encode()
    parts['ppt/slideMasters/slideMaster1.xml'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles><p:clrMap accent1="159B9A" accent2="7667E8" accent3="14253D" accent4="68758A" accent5="F4F7FA" accent6="FFFFFF" bg1="FFFFFF" bg2="F4F7FA" tx1="14253D" tx2="68758A"/></p:sldMaster>'''
    parts['ppt/slideMasters/_rels/slideMaster1.xml.rels'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>'''
    parts['ppt/slideLayouts/slideLayout1.xml'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'''
    parts['ppt/slideLayouts/_rels/slideLayout1.xml.rels'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>'''
    parts['ppt/theme/theme1.xml'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="AarogyaTwin"><a:themeElements><a:clrScheme name="Aarogya"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="14253D"/></a:dk2><a:lt2><a:srgbClr val="F4F7FA"/></a:lt2><a:accent1><a:srgbClr val="159B9A"/></a:accent1><a:accent2><a:srgbClr val="7667E8"/></a:accent2><a:accent3><a:srgbClr val="D58A36"/></a:accent3><a:accent4><a:srgbClr val="68758A"/></a:accent4><a:accent5><a:srgbClr val="FFFFFF"/></a:accent5><a:accent6><a:srgbClr val="F4F7FA"/></a:accent6><a:hlink><a:srgbClr val="159B9A"/></a:hlink><a:folHlink><a:srgbClr val="7667E8"/></a:folHlink></a:clrScheme><a:fontScheme name="Aarogya"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme><a:fmtScheme name="Aarogya"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>'''
    parts['ppt/presProps.xml'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'''
    parts['ppt/viewProps.xml'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:normalViewPr/></p:viewPr>'''
    parts['ppt/tableStyles.xml'] = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" defaultTableStyle="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'''
    return parts


def write_pptx(path: Path, slides: list[tuple[str, list[str]]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in pptx_parts(slides).items():
            archive.writestr(name, data)


def pdf_text(text: str) -> str:
    clean = text.replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
    return clean.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, slides: list[tuple[str, list[str]]]) -> None:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = list(range(3, 3 + len(slides)))
    content_start = 3 + len(slides)
    objects.append(("<< /Type /Pages /Kids [" + " ".join(f"{x} 0 R" for x in page_ids) + f"] /Count {len(slides)} >>").encode())
    contents: list[bytes] = []
    for index, (title, bullets) in enumerate(slides, 1):
        commands = ["q", "0.08 0.15 0.24 rg", "0 508 960 32 re", "f", "Q", "BT", "/F1 24 Tf", "0.08 0.15 0.24 rg", "48 470 Td", f"({pdf_text(title)}) Tj", "/F1 12 Tf", "0.15 0.21 0.30 rg", "0 -42 Td"]
        y_lines = []
        for bullet in bullets:
            for line in wrap(bullet.replace("—", "-"),  ninety := 96):
                y_lines.append("- " + line)
        for line in y_lines:
            commands.append(f"({pdf_text(line)}) Tj")
            commands.append("0 -17 Td")
        commands += ["/F1 8 Tf", "0.40 0.46 0.54 rg", "0 -18 Td", f"(AarogyaTwin-X | synthetic research prototype | {index}) Tj", "ET"]
        stream = "\n".join(commands).encode("latin-1", "replace")
        contents.append(stream)
    for index, stream in enumerate(contents):
        page_no = page_ids[index]
        content_no = content_start + index
        while len(objects) < page_no - 2:
            objects.append(b"")
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_W} {PDF_H}] /Resources << /Font << /F1 {content_start + len(slides)} 0 R >> >> /Contents {content_no} 0 R >>").encode())
    for stream in contents:
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(output)


ARCHITECTURE_SLIDES = [
    ("AarogyaTwin-X architecture", ["Local synthetic research prototype", "Forecast heads at 30, 60, and 120 minutes", "Evidence, uncertainty, provenance, and abstention are first-class outputs"]),
    ("End-to-end data flow", ["Seed 2026 -> synthetic simulator -> patient-disjoint split", "Past-only feature builder -> CPU temporal model", "Calibration and bounded residual -> joblib/JSON artifacts", "FastAPI local API -> React/Vite dashboard"]),
    ("Synthetic data boundary", ["60 patients, 5 days, 5-minute grid", "CGM, heart rate, HRV, sleep, activity, meals, and static fields", "Hidden simulator parameters never become model features", "No real patient records or public benchmark data"]),
    ("Leakage-aware evaluation", ["36 train patients; 6 calibration-tuning; 6 calibration-interval; 12 test", "No test patient tunes models, calibration, thresholds, or intervals", "Every feature vector is bounded by its replay anchor", "Correlated replay windows are not independent subjects"]),
    ("Model layers", ["Temporal lag gradient-boosting heads for glucose", "Fusion logistic classifier for the sustained-event endpoint", "Train-only imputation, standardization, and missing indicators", "Platt probability calibration and split-conformal intervals"]),
    ("Causal-in-time residual", ["A prior forecast error is used only after its target timestamp is observable", "Per-patient, short, bounded error history", "Strength selected on calibration-tuning patients", "Adaptive residual only - not a clinical insulin-sensitivity model"]),
    ("Serving boundary", ["TwinEngine loads artifacts and never trains during API requests", "Local endpoints: health, patients, twin snapshot, scenario, metrics", "Missing/stale CGM produces warnings and abstention", "No fallback medical numbers are inserted"]),
    ("Dashboard boundary", ["Replay held-out patient history", "Three named forecast heads and intervals", "Event state and risk when eligible", "Dropout, provenance, limitations, and assumption-based scenario view"]),
    ("Non-claims", ["No clinical accuracy or real-patient generalization", "No causal treatment effect or dosing recommendation", "No arbitrary distribution-shift robustness", "Full saved evidence is in docs/EVIDENCE_SUMMARY.md"]),
]

PRESENTATION_SLIDES = [
    ("AarogyaTwin-X", ["Forecasts with evidence, not unsupported certainty", "Local synthetic patient replay and glucose forecasting", "Not a diagnostic device. Not medical advice."]),
    ("The question", ["Can a forecast be useful without hiding its limitations?", "Users need data freshness, uncertainty, and provenance", "Missing data should trigger abstention, not invented certainty"]),
    ("The experience", ["Select a held-out synthetic patient", "Replay the timeline in five-minute steps", "Inspect context, forecast heads, intervals, event risk, and evidence"]),
    ("Synthetic data only", ["60 artificial patients x 5 days x 5-minute observations", "Static records plus CGM, heart rate, HRV, sleep, activity, and meals", "Seeded variability, rhythms, noise, and missingness", "No real patient data"]),
    ("Leakage-aware evaluation", ["36 training patients", "6 calibration-tuning patients", "6 calibration-interval patients", "12 held-out test patients", "Past-only features at every replay anchor"]),
    ("Model architecture", ["Small CPU temporal lag gradient-boosting heads", "Calibrated fusion logistic event classifier", "Train-only preprocessing and missingness indicators", "Conformal intervals and explicit ablations"]),
    ("Personalization", ["Make a forecast at time T", "Wait for the target timestamp", "Use a bounded history of matured errors for later forecasts", "Never use the current forecast's future target", "Adaptive residual, not clinical physiology"]),
    ("Held-out forecast results", ["30 min: MAE 7.21 | RMSE 9.76 | coverage 89.95%", "60 min: MAE 7.85 | RMSE 10.42 | coverage 89.36%", "120 min: MAE 8.38 | RMSE 11.00 | coverage 90.00%", "Intervals are calibrated named heads, not extra points"]),
    ("Probability calibration", ["Fusion Brier: 0.05035 -> 0.02437", "Fusion log loss: 0.18466 -> 0.13559", "Expected calibration error: 0.05814 -> 0.02387", "AUROC 0.94330 and AUPRC 0.27652 remained ranking measures"]),
    ("Missing data", ["Natural missingness: about 0.3% abstention", "Recent stream gaps degrade measured forecasts", "Recent 30-minute CGM dropout: 100% abstention", "Unavailable estimates remain null"]),
    ("Distribution shift", ["Nominal 120-minute coverage: 89.46%", "Glucose level +25 mg/dL: coverage 62.09%", "Meal inputs doubled: coverage 89.35%", "HbA1c +1.0: coverage 80.26%", "Stress tests show known failure modes"]),
    ("Alert behavior", ["22 synthetic episodes across 12 test patients", "At threshold 0.10: episode sensitivity 22.7%, median lead 70 min", "At threshold 0.20: episode sensitivity 18.2%, 0.133 false alerts/patient-day", "Synthetic alert metrics are not clinical performance"]),
    ("Live demo", ["Show synthetic/non-clinical warning", "Select held-out record and replay +5 minutes", "Inspect heads and intervals", "Enable dropout and show abstention", "Review scenario disclaimer and measured evidence"]),
    ("Safety and transparency", ["No diagnosis, dosing, medication change, or treatment advice", "Drivers are observed context, not causal attribution", "Scenario controls are assumptions, not treatment effects", "Not-ready, loading, error, and unavailable states are explicit"]),
    ("Reproducibility", ["Seed 2026 and local synthetic generation", "Joblib bundle plus strict JSON metrics/provenance", "Engine loads artifacts and never trains automatically", "API and dashboard run on localhost"]),
    ("Limitations", ["One simulator and one seeded cohort", "Correlated replay windows", "Small event count for alert conclusions", "Coverage can fail under distribution shift", "No clinical validation"]),
    ("Closing", ["A reproducible foundation for honest forecasting research", "Past-only temporal features", "Measured uncertainty and probability calibration", "Data-quality abstention and explicit limitations"]),
]


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    outputs = [
        ("AarogyaTwinX_Architecture", ARCHITECTURE_SLIDES),
        ("AarogyaTwinX_Presentation", PRESENTATION_SLIDES),
    ]
    for stem, slides in outputs:
        write_pptx(DOCS / f"{stem}.pptx", slides)
        write_pdf(DOCS / f"{stem}.pdf", slides)
        print(f"generated {stem}.pptx and {stem}.pdf ({len(slides)} slides)")


if __name__ == "__main__":
    main()
