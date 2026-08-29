"""Build reports/hw01/report.pdf from repository code, results, and screenshots."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "reports/hw01"
SCREENSHOTS = REPORT_ROOT / "screenshots"
RAW = REPORT_ROOT / "raw"
OUTPUT = REPORT_ROOT / "report.pdf"
REPOSITORY_URL = "https://github.com/Sharanjoo/data260-9619"

EXPECTED_SCREENSHOTS = [
    "01_web_form.png",
    "02_js_console.png",
    "03_docker_localhost.png",
    "04_agents_console.png",
    "05_client_stats_turn3.png",
    "06_client_stats_turn5.png",
    "07_nondeterminism_complete.png",
    "08_aws_ecs_service.png",
    "09_aws_public_ip.png",
]


def read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def git_commit() -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.stdout.strip() if process.returncode == 0 else "PENDING - repository has no commit"


def page_number(canvas, document) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#5E6D66"))
    canvas.drawString(0.62 * inch, 0.38 * inch, "DATA 260 - Homework 1 - SID4 9619")
    canvas.drawRightString(7.88 * inch, 0.38 * inch, f"Page {document.page}")
    canvas.restoreState()


def code_excerpt(text: str, start_marker: str, end_marker: str, fallback_lines: int = 28) -> str:
    start = text.find(start_marker)
    if start < 0:
        return "\n".join(text.splitlines()[:fallback_lines])
    end = text.find(end_marker, start + len(start_marker)) if end_marker else -1
    return text[start:] if end < 0 else text[start:end]


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=29,
            textColor=colors.HexColor("#12472F"),
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#5E6D66"),
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#12472F"),
            spaceBefore=12,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#1D6A47"),
            spaceBefore=9,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=13.3,
            spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#5E6D66"),
            spaceAfter=5,
        ),
        "code": ParagraphStyle(
            "Code",
            fontName="Courier",
            fontSize=6.35,
            leading=8.1,
            textColor=colors.HexColor("#17251F"),
            backColor=colors.HexColor("#F2F5F2"),
            borderColor=colors.HexColor("#CBD6CF"),
            borderWidth=0.5,
            borderPadding=7,
            spaceBefore=4,
            spaceAfter=9,
        ),
        "warning": ParagraphStyle(
            "Warning",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#922B21"),
            alignment=TA_CENTER,
        ),
    }


def config_table(styles: dict[str, ParagraphStyle], model_text: str) -> Table:
    rows = [
        ["SID4", "9619", "Last four digits of SJSU ID"],
        ["PORT_BASE", "8619", "8000 + (9619 mod 900)"],
        ["PREFIX", "s9619", '"s" + SID4'],
        ["SEED", "9619", "SID4"],
        ["VERIFY_SEED", "269619", "260000 + SID4"],
        ["DOMAIN_ID", "3", "9619 mod 8"],
        ["Assigned domain", "Grocery supply and recall notices", "Domain table row 3"],
        ["Hardware", "HP Pavilion; 32 GB RAM; 512 GB storage", "User-provided"],
        ["Local model", model_text, "Ollama"],
        ["Commit reference", git_commit(), "Current report-generation commit"],
    ]
    table = Table([["Value", "Result", "Basis"], *rows], colWidths=[1.35 * inch, 3.35 * inch, 2.45 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D6A47")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10.2),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD6CF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9F7")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def screenshot_flowable(filename: str, caption: str, styles: dict[str, ParagraphStyle]):
    path = SCREENSHOTS / filename
    if not path.is_file():
        box = Table(
            [[Paragraph(f"EVIDENCE NEEDED: {escape(filename)}<br/>{escape(caption)}", styles["warning"])]],
            colWidths=[7.05 * inch],
            rowHeights=[1.0 * inch],
        )
        box.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#C0392B")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDEDEC")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return KeepTogether([box, Spacer(1, 8)])

    image = Image(str(path))
    max_width = 7.05 * inch
    max_height = 4.65 * inch
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    return KeepTogether(
        [
            image,
            Spacer(1, 4),
            Paragraph(f"Figure: {escape(caption)}", styles["small"]),
            Spacer(1, 6),
        ]
    )


def add_code(story: list, text: str, styles: dict[str, ParagraphStyle]) -> None:
    story.append(XPreformatted(escape(text.rstrip()), styles["code"]))


def get_agent_answers() -> tuple[str, str, str, str]:
    data = read_json(RAW / "agent_demo_result.json")
    final = data.get("final", {}) if isinstance(data.get("final"), dict) else {}
    transcript = data.get("transcript", {}) if isinstance(data.get("transcript"), dict) else {}
    reviewer = transcript.get("reviewer", {}) if isinstance(transcript.get("reviewer"), dict) else {}
    tags = final.get("tags", [])
    tags_text = ", ".join(str(tag) for tag in tags) if len(tags) == 3 else "PENDING REAL RUN"
    summary = str(final.get("summary", "PENDING REAL RUN"))
    changed = reviewer.get("changed")
    changed_text = "PENDING REAL RUN" if not isinstance(changed, bool) else ("Yes" if changed else "No")
    explanation = str(reviewer.get("explanation", "PENDING REAL RUN"))
    return tags_text, summary, changed_text, explanation


def model_label() -> str:
    agent = read_json(RAW / "agent_demo_result.json")
    experiment = read_json(RAW / "nondeterminism_results.json")
    model = agent.get("model")
    metadata = experiment.get("metadata", {}) if isinstance(experiment.get("metadata"), dict) else {}
    experiment_model = metadata.get("model")
    if model and experiment_model and model == experiment_model:
        return str(model)
    if model:
        return f"{model} (40-run experiment pending/unchecked)"
    return "qwen3:8b planned - REAL RUN PENDING"


def interpretation_text() -> str:
    experiment = read_json(RAW / "nondeterminism_results.json")
    runs = experiment.get("runs")
    if not isinstance(runs, list) or len(runs) != 40:
        return (
            "PENDING REAL RUN: After collecting all 40 rows, explain whether identical users saw "
            "different tags at temperature 0.7 and 0.0, citing the measured distinct-set counts. "
            "Variation is acceptable for optional discovery tags, but not for a safety-critical "
            "allergen warning that must remain accurate and consistent."
        )
    groups: dict[float, list[dict]] = {0.7: [], 0.0: []}
    for row in runs:
        temperature = float(row.get("temperature", -1))
        if temperature in groups:
            groups[temperature].append(row)
    distinct = {
        temp: len({tuple(sorted(str(tag).casefold() for tag in row.get("tags", []))) for row in rows})
        for temp, rows in groups.items()
    }
    return (
        f"The fixed input produced {distinct[0.7]} distinct tag set(s) at temperature 0.7 and "
        f"{distinct[0.0]} at temperature 0.0. Therefore, two users may receive different but "
        "topically valid labels when sampling is enabled; lower temperature should usually be more "
        "repeatable. Variation is acceptable for optional discovery tags, but not for a "
        "safety-critical allergen warning whose meaning must remain accurate and consistent."
    )


def build_report() -> list[str]:
    styles = build_styles()
    missing = [name for name in EXPECTED_SCREENSHOTS if not (SCREENSHOTS / name).is_file()]
    metrics = read_text("reports/hw01/METRICS.md")
    tags, summary, changed, review_explanation = get_agent_answers()
    html = read_text("code/web_application/index.html")
    javascript = read_text("code/web_application/app.js")
    agent_code = read_text("code/agents_demo.py")
    model_code = read_text("src/model_client.py")
    client_code = read_text("code/hw1_client.py")
    dockerfile = read_text("code/Dockerfile")

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.62 * inch,
        title="DATA 260 Homework 1 - SID4 9619",
        author="Sharan Lourduraj",
    )
    story: list = []
    story.append(Spacer(1, 0.55 * inch))
    story.append(Paragraph("DATA 260 - Homework 1", styles["title"]))
    story.append(Paragraph("Grocery Supply and Recall Notices", styles["subtitle"]))
    story.append(Paragraph("Sharan Lourduraj | SID4 9619", styles["subtitle"]))
    if missing:
        story.append(Spacer(1, 0.18 * inch))
        story.append(
            Paragraph(
                f"DRAFT - DO NOT SUBMIT: {len(missing)} required screenshot(s) are missing.",
                styles["warning"],
            )
        )
    story.append(Spacer(1, 0.35 * inch))
    story.append(config_table(styles, model_label()))
    story.append(Spacer(1, 0.18 * inch))
    story.append(
        Paragraph(
            f'<b>GitHub repository:</b> <link href="{REPOSITORY_URL}">{REPOSITORY_URL}</link>',
            styles["body"],
        )
    )
    story.append(
        Paragraph(
            "This report was generated from repository code and real result files. Any red evidence "
            "box must be replaced by the named screenshot before submission.",
            styles["small"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("Part 1 - HTML and JavaScript", styles["h1"]))
    story.append(Paragraph("Domain schema and form", styles["h2"]))
    story.append(
        Paragraph(
            "The entity is a Grocery Recall Notice. Its primary field is product name; the secondary "
            "field is brand or supplier. The form also collects submitter email, a description longer "
            "than 25 characters, one of four domain categories, and terms acceptance.",
            styles["body"],
        )
    )
    add_code(story, code_excerpt(html, '<form id="noticeForm"', "</form>"), styles)
    story.append(screenshot_flowable("01_web_form.png", "Completed domain form before submission.", styles))

    story.append(Paragraph("JavaScript validation and transformation", styles["h2"]))
    js_excerpt = code_excerpt(javascript, "const submissionCounter", "descriptionInput.addEventListener")
    js_excerpt += "\n\n" + code_excerpt(javascript, 'form.addEventListener("submit"', "});")
    add_code(story, js_excerpt, styles)
    story.append(
        Paragraph(
            "The arrow function first shows the two assignment-specific alerts. A successful submit "
            "is stringified to JSON, parsed, destructured for product name and email, copied with a "
            "submissionDate using spread syntax, and counted by a closure.",
            styles["body"],
        )
    )
    story.append(screenshot_flowable("02_js_console.png", "JSON and JavaScript console output.", styles))

    story.append(PageBreak())
    story.append(Paragraph("Docker - local deployment", styles["h1"]))
    add_code(story, dockerfile, styles)
    add_code(story, "docker compose up --build -d\ncurl -I http://localhost:8619", styles)
    story.append(
        Paragraph(
            "Nginx serves the three static application files on container port 80. Compose maps the "
            "personal port 8619 to port 80 and names the image and container with prefix s9619.",
            styles["body"],
        )
    )
    story.append(screenshot_flowable("03_docker_localhost.png", "Docker-served app at localhost:8619.", styles))

    story.append(PageBreak())
    story.append(Paragraph("Part 2 - Planner, Reviewer, Finalizer", styles["h1"]))
    story.append(
        Paragraph(
            "Planner derives three tags and a short summary only from the supplied title/content. "
            "Reviewer checks specificity, grounding, uniqueness, and the 25-word limit. Finalizer is "
            "a deterministic validation step that normalizes the reviewed output into the exact schema.",
            styles["body"],
        )
    )
    add_code(story, code_excerpt(agent_code, "def run_pipeline(", "def load_input"), styles)
    story.append(Paragraph("Exact command", styles["h2"]))
    add_code(
        story,
        "python scripts/recorded_run.py -- python code/agents_demo.py "
        "--input-file reports/hw01/cases/nondeterminism_input.json "
        "--model qwen3:8b --temperature 0.0 --output-json "
        "reports/hw01/raw/agent_demo_result.json",
        styles,
    )
    story.append(screenshot_flowable("04_agents_console.png", "Planner, Reviewer, Finalized, and Publish output.", styles))
    story.append(Paragraph("Short answers", styles["h2"]))
    for label, value in (
        ("Q1 - Final tags", tags),
        ("Q2 - Final summary", summary),
        ("Q3 - Did Reviewer change anything?", f"{changed}. {review_explanation}"),
    ):
        story.append(Paragraph(f"<b>{escape(label)}:</b> {escape(value)}", styles["body"]))

    story.append(PageBreak())
    story.append(Paragraph("Part 3 - Measuring Non-Determinism", styles["h1"]))
    story.append(
        Paragraph(
            "The exact same saved grocery-recall input is run 20 times at temperature 0.7 and 20 "
            "times at temperature 0.0. Each row stores its final tags, summary, total latency, "
            "Reviewer-change flag, and per-agent token counts. Checkpointing supports safe resume.",
            styles["body"],
        )
    )
    add_code(
        story,
        "python3 scripts/run_nondeterminism.py --model qwen3:8b --resume",
        styles,
    )
    story.append(Paragraph("Measured tables", styles["h2"]))
    add_code(story, metrics, styles)
    story.append(Paragraph("Interpretation", styles["h2"]))
    story.append(Paragraph(escape(interpretation_text()), styles["body"]))
    story.append(screenshot_flowable("07_nondeterminism_complete.png", "Completed 40-run experiment output.", styles))

    story.append(PageBreak())
    story.append(Paragraph("Part 4 - Model Client and Token Accounting", styles["h1"]))
    add_code(story, code_excerpt(model_code, "class OllamaModelClient", "def stats"), styles)
    add_code(story, code_excerpt(client_code, "def send_turn", "def main"), styles)
    story.append(
        Paragraph(
            "Every call uses the same complete(messages, tools=None) adapter. Each response reports "
            "input, output, and total tokens. /stats reads cumulative counters and serialized history "
            "length without appending to the history. The demo records five turns and prints /stats "
            "after turns 3 and 5.",
            styles["body"],
        )
    )
    story.append(screenshot_flowable("05_client_stats_turn3.png", "Token accounting and /stats after turn 3.", styles))
    story.append(screenshot_flowable("06_client_stats_turn5.png", "Token accounting and /stats after turn 5.", styles))

    story.append(Paragraph("Concept questions", styles["h2"]))
    answers = [
        (
            "Why resend prior context?",
            "Model API calls are stateless. Earlier messages must be included again so the next response can use the conversation context.",
        ),
        (
            "System prompt vs. user message",
            "A system prompt sets higher-priority behavior and constraints; a user message supplies the current lower-priority request or content.",
        ),
        (
            "Why do input tokens grow?",
            "Each later request serializes more prior user and assistant messages, so its input contains more tokens than earlier turns.",
        ),
        (
            "What limits growth?",
            "The model context window, application token limits, latency/cost limits, or deliberate history trimming and summarization.",
        ),
    ]
    for question, answer in answers:
        story.append(Paragraph(f"<b>{escape(question)}</b> {escape(answer)}", styles["body"]))

    story.append(PageBreak())
    story.append(Paragraph("AWS ECS Deployment", styles["h1"]))
    story.append(
        Paragraph(
            "The Nginx image is pushed to ECR and deployed as one Linux/X86_64 Fargate task with "
            "0.25 vCPU, 0.5 GB RAM, container port 80, an assigned public IP, and a security-group "
            "inbound rule for TCP/80. Desired task count is exactly one.",
            styles["body"],
        )
    )
    story.append(screenshot_flowable("08_aws_ecs_service.png", "ECS service with one RUNNING task.", styles))
    story.append(screenshot_flowable("09_aws_public_ip.png", "Application opened using the ECS task public IP.", styles))
    story.append(
        Paragraph(
            "After capturing evidence, the service, cluster, ECR repository/images, unused log "
            "group, and dedicated security group must be deleted to stop charges.",
            styles["body"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("Reproducibility and AI Use", styles["h1"]))
    story.append(Paragraph("Reproducible run sequence", styles["h2"]))
    add_code(
        story,
        "docker compose up --build -d\n"
        "ollama pull qwen3:8b\n"
        "make agents\n"
        "make client\n"
        "make experiment\n"
        "make verify\n"
        "make report",
        styles,
    )
    story.append(Paragraph("AI-use disclosure", styles["h2"]))
    ai_use = read_text("reports/hw01/AI_USE.md")
    for paragraph in [item.strip() for item in ai_use.split("\n\n") if item.strip()]:
        if paragraph.startswith("#"):
            continue
        story.append(Paragraph(escape(paragraph.replace("\n", " ")), styles["body"]))
    story.append(Paragraph("Final submission checks", styles["h2"]))
    story.append(
        Paragraph(
            "The report PDF uploaded to the course must be byte-identical to the copy in the tagged "
            "repository. The repository is https://github.com/Sharanjoo/data260-9619 and the final "
            "tag is hw1. Collaborators Sbnikitha and supriyaselvanganesan must retain access. "
            "RUN_LOG.txt, "
            "raw results, METRICS.md, AI_USE.md, report.pdf, run instructions, and verification.json "
            "must all be present at that tag.",
            styles["body"],
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on-missing-evidence",
        action="store_true",
        help="return a failure code if required screenshots are absent",
    )
    args = parser.parse_args()
    missing = build_report()
    print(f"Built {OUTPUT.relative_to(PROJECT_ROOT)}")
    if missing:
        print("Missing screenshots:")
        for name in missing:
            print(f"- {name}")
        if args.fail_on_missing_evidence:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
