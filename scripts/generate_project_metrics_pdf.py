#!/usr/bin/env python3
"""Generate MAC_ASD project metrics report as PDF."""

from fpdf import FPDF
from datetime import date

UNICODE_FONT = "Arial"

class MetricsReport(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font(UNICODE_FONT, "", r"C:\Windows\Fonts\arial.ttf", uni=True)
        self.add_font(UNICODE_FONT, "B", r"C:\Windows\Fonts\arialbd.ttf", uni=True)
        self.add_font(UNICODE_FONT, "I", r"C:\Windows\Fonts\ariali.ttf", uni=True)
        self.add_font(UNICODE_FONT, "BI", r"C:\Windows\Fonts\arialbi.ttf", uni=True)

    def header(self):
        self.set_font(UNICODE_FONT, "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, "MAC_ASD - Project Metrics Report", align="L")
        self.cell(0, 5, date.today().strftime("%Y-%m-%d"), align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font(UNICODE_FONT, "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font(UNICODE_FONT, "B", 14)
        self.set_text_color(30, 60, 120)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 60, 120)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def sub_title(self, title):
        self.set_font(UNICODE_FONT, "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def metric_row(self, label, value, w1=110, w2=60):
        self.set_font(UNICODE_FONT, "", 10)
        self.set_text_color(60, 60, 60)
        self.cell(w1, 7, f"  {label}")
        self.set_font(UNICODE_FONT, "B", 10)
        self.set_text_color(30, 60, 120)
        self.cell(w2, 7, str(value), new_x="LMARGIN", new_y="NEXT")

    def table_header(self, cols, widths):
        self.set_fill_color(30, 60, 120)
        self.set_text_color(255, 255, 255)
        self.set_font(UNICODE_FONT, "B", 9)
        for col, w in zip(cols, widths):
            self.cell(w, 7, f" {col}", fill=True)
        self.ln()

    def table_row(self, cells, widths, bold_last=False):
        self.set_text_color(40, 40, 40)
        for i, (cell, w) in enumerate(zip(cells, widths)):
            if bold_last and i == len(cells) - 1:
                self.set_font(UNICODE_FONT, "B", 9)
            else:
                self.set_font(UNICODE_FONT, "", 9)
            self.cell(w, 6, f" {cell}")
        self.ln()


def build_report():
    pdf = MetricsReport()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── Title page ──
    pdf.ln(25)
    pdf.set_font(UNICODE_FONT, "B", 28)
    pdf.set_text_color(30, 60, 120)
    pdf.cell(0, 14, "MAC_ASD", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(UNICODE_FONT, "", 14)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "Project Metrics & Complexity Report", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_draw_color(30, 60, 120)
    mid = pdf.w / 2
    pdf.line(mid - 30, pdf.get_y(), mid + 30, pdf.get_y())
    pdf.ln(12)
    pdf.set_font(UNICODE_FONT, "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 7, f"Generated: {date.today().strftime('%d %B %Y')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Repository: github.com/yamazaki1711/mac_asd", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, 'Branch: main  |  Commit: 7fed40e', align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Page 2: Executive Summary ──
    pdf.add_page()
    pdf.section_title("Executive Summary")

    pdf.set_font(UNICODE_FONT, "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 5.5,
        "MAC_ASD is an AI-powered construction document analysis system. "
        "It automates PTO (Production Technical Department) workflows: "
        "as-built documentation, inspection reports, work acceptance certificates, "
        "normative compliance checks, and evidence graphs for construction disputes. "
        "The system combines LLM/VLM inference pipelines with a modular agent architecture."
    )
    pdf.ln(4)

    pdf.sub_title("Totals at a Glance")
    pdf.metric_row("Total lines of code + config + docs:", "~141,600")
    pdf.metric_row("Python source lines (src + scripts + mcp):", "58,627")
    pdf.metric_row("Estimated tokens (Python):", "~920K")
    pdf.metric_row("Estimated tokens (all files):", "~2.3-2.5M")
    pdf.metric_row("Production source files:", "~160")
    pdf.metric_row("Test files:", "~40")
    pdf.metric_row("Core engine files (src/core/):", "33")
    pdf.ln(4)

    pdf.sub_title("Project Scale Analogy")
    pdf.set_font(UNICODE_FONT, "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 5.5,
        "59K lines of Python is roughly 1/3 of the Linux kernel core, "
        "2 average Django projects, or 6-8 typical microservices. "
        "At ~920K Python tokens, the codebase fits 3-4 times into Gemini 2.5 Pro (1M context) "
        "but cannot fit into Claude (200K) without RAG/chunking."
    )

    # ── Page 3: Line Counts ──
    pdf.add_page()
    pdf.section_title("1. Line Count Breakdown")

    pdf.sub_title("By File Type")
    cols = ["Category", "Lines", "%"]
    widths = [100, 40, 30]
    pdf.table_header(cols, widths)

    rows = [
        ("Python (src, scripts, mcp)", "58,627", "41.4%"),
        ("JSON (knowledge base, templates)", "52,774", "37.3%"),
        ("YAML (configs, knowledge base)", "15,002", "10.6%"),
        ("Markdown (documentation)", "14,816", "10.5%"),
        ("Shell / other", "~370", "0.3%"),
        ("TOTAL", "~141,600", "100%"),
    ]
    for i, row in enumerate(rows):
        pdf.table_row(row, widths, bold_last=(i == len(rows) - 1))

    pdf.ln(6)
    pdf.sub_title("Tests")
    pdf.metric_row("Test code (Python):", "8,431 lines")
    pdf.metric_row("Test-to-source ratio:", "1 : 7")

    pdf.ln(4)
    pdf.sub_title("Knowledge Base (the 'heavy' static data)")
    pdf.set_font(UNICODE_FONT, "", 9)
    pdf.set_text_color(60, 60, 60)
    kb_items = [
        "docx_template_structures.json  —  16,254 lines",
        "idprosto_worktype_docs.json    —  12,808 lines",
        "pto_templates_database.yaml    —  10,070 lines",
        "pto_templates_database.json    —  11,329 lines",
        "normative_docs_qwen.json       —  913 lines",
        "knowledge_invalidation.json    —  666 lines",
    ]
    for item in kb_items:
        pdf.cell(0, 5, f"    {item}", new_x="LMARGIN", new_y="NEXT")
    pdf.metric_row("Total knowledge base:", "~68K lines (48% of project)")

    # ── Page 4: Token Estimate ──
    pdf.add_page()
    pdf.section_title("2. Token Estimate")

    pdf.sub_title("Methodology")
    pdf.set_font(UNICODE_FONT, "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 5.5,
        "Token counts are estimated via character-count division: "
        "Python ~3 chars/token (code-dense), Russian-heavy text ~4 chars/token (Cyrillic = 2-4 bytes/char in UTF-8, "
        "LLM tokenizers compress at ~2-4 chars/token for Russian). Actual token count depends on the specific "
        "tokenizer (Claude vs GPT vs Gemini) and may vary +/-15%."
    )
    pdf.ln(4)

    cols = ["Source", "Characters", "Est. Tokens", "Ratio"]
    widths = [70, 45, 40, 25]
    pdf.table_header(cols, widths)
    rows = [
        ("Python source", "2,760,512", "~920K", "3.0 ch/tok"),
        ("Config, docs, JSON, YAML", "5,068,653", "~1,450K", "3.5 ch/tok"),
        ("TOTAL", "7,829,165", "~2,370K", "3.3 ch/tok"),
    ]
    for i, row in enumerate(rows):
        pdf.table_row(row, widths, bold_last=(i == len(rows) - 1))

    pdf.ln(6)
    pdf.sub_title("Context Window Fit")
    cols = ["Model", "Context Window", "Fits MAC_ASD?"]
    widths = [55, 55, 70]
    pdf.table_header(cols, widths)
    fits = [
        ("Claude Opus 4.7", "200K tokens", "NO  - needs RAG/chunking (12x gap)"),
        ("Gemini 2.5 Pro", "1M tokens", "PARTIAL - Python only (920K fits)"),
        ("Gemini 2.5 Pro", "1M tokens", "NO  - full codebase (2.4M) 2.4x over"),
        ("GPT-4 Turbo", "128K tokens", "NO  - needs RAG/chunking (19x gap)"),
        ("Claude Haiku 4.5", "200K tokens", "NO  - needs RAG/chunking (12x gap)"),
    ]
    for row in fits:
        pdf.table_row(row, widths)

    # ── Page 5: Top Heaviest Files ──
    pdf.add_page()
    pdf.section_title("3. Top Heaviest Files")

    pdf.sub_title("Python Source (Top 15)")
    cols = ["#", "File", "Lines"]
    widths = [8, 140, 30]
    pdf.table_header(cols, widths)
    top_py = [
        (1, "src/agents/skills/pto/work_spec.py", "2,464"),
        (2, "docs/generate_concept_pdf_v4.py", "1,521"),
        (3, "src/core/pm_agent.py", "1,233"),
        (4, "src/agents/nodes.py", "1,207"),
        (5, "mcp_servers/asd_core/tools/lab_tools.py", "1,205"),
        (6, "docs/generate_concept_pdf_v3.py", "1,054"),
        (7, "src/core/ingestion.py", "964"),
        (8, "src/agents/skills/smeta/rate_lookup.py", "929"),
        (9, "src/core/graph_service.py", "914"),
        (10, "src/core/services/pto_agent.py", "866"),
        (11, "src/agents/nodes_v2.py", "856"),
        (12, "src/core/knowledge/invalidation_engine.py", "830"),
        (13, "src/core/auditor.py", "822"),
        (14, "src/core/parser_engine.py", "780"),
        (15, "src/core/services/legal_service.py", "752"),
    ]
    for num, fname, lines in top_py:
        pdf.table_row([str(num), fname, lines], widths)

    pdf.ln(6)
    pdf.sub_title("JSON Data (Top 5)")
    cols = ["#", "File", "Lines"]
    widths = [8, 145, 30]
    pdf.table_header(cols, widths)
    top_json = [
        (1, "data/knowledge/templates/docx_template_structures.json", "16,254"),
        (2, "data/knowledge/idprosto_worktype_docs.json", "12,808"),
        (3, "artifacts/pto_knowledge_base/pto_templates_database.json", "11,329"),
        (4, "artifacts/pto_knowledge_base/id_examples_detail.json", "5,221"),
        (5, "scripts/normative_docs_qwen.json", "913"),
    ]
    for num, fname, lines in top_json:
        pdf.table_row([str(num), fname, lines], widths)

    # ── Page 6: Architecture ──
    pdf.add_page()
    pdf.section_title("4. Architecture Overview")

    pdf.sub_title("Directory Map")
    dirs = [
        ("src/core/",       "33 files", "Core engine: inference, auditor, evidence graph, chain builder, VLM"),
        ("src/core/services/", "12 files", "Domain services: PTO, legal, PPR generator, IS generator, geo context"),
        ("src/agents/",     "16 files", "Agent definitions: PTO, legal, procurement, skills (smeta, pto, legal)"),
        ("mcp_servers/",    "13 files", "MCP tools: lab, jurist, google, vision, artifact, legal"),
        ("scripts/",        "15 files", "Generation scripts, PDF builders, scrapers, telegram scout"),
        ("config/",         "3 files", "id_requirements.yaml, telegram_channels.yaml"),
        ("docs/",           "14 files", "Technical documentation, architecture, concept, specs"),
        ("data/",           "~20 files", "Knowledge bases, templates, test project PDFs, typical rates"),
    ]
    cols = ["Directory", "Size", "Role"]
    widths = [40, 22, 118]
    pdf.table_header(cols, widths)
    for d in dirs:
        pdf.table_row(d, widths)

    pdf.ln(6)
    pdf.sub_title("Key Components (src/core/)")
    pdf.set_font(UNICODE_FONT, "", 9)
    pdf.set_text_color(60, 60, 60)
    components = [
        "auditor.py           — Compliance checking against normative base (822 lines)",
        "chain_builder.py     — LangGraph chain construction (498 lines)",
        "evidence_graph.py    — Legal evidence graph for disputes (734 lines)",
        "graph_service.py     — Shared model queue & graph orchestration (914 lines)",
        "hitl_system.py       — Human-in-the-loop workflows (421 lines)",
        "inference_engine.py  — LLM inference pipeline (529 lines)",
        "ingestion.py         — Document ingestion & parsing (964 lines)",
        "journal_reconstructor.py — Journal reconstruction from fragments (527 lines)",
        "project_loader.py    — Project directory scanning & loading (304 lines)",
        "scan_detector.py     — Defect detection from inspection scans (122 lines)",
        "vlm_classifier.py    — Vision-Language Model classification (312 lines)",
    ]
    for c in components:
        pdf.cell(0, 5, f"    {c}", new_x="LMARGIN", new_y="NEXT")

    # ── Page 7: Complexity Metrics ──
    pdf.add_page()
    pdf.section_title("5. Complexity & Risk Indicators")

    pdf.sub_title("File Size Distribution")
    cols = ["Bucket", "Count", "Examples"]
    widths = [35, 20, 125]
    pdf.table_header(cols, widths)
    buckets = [
        ("1-100 lines", "~55", "Small utilities, __init__.py, thin config wrappers"),
        ("100-300 lines", "~45", "Most service modules, single-responsibility classes"),
        ("300-600 lines", "~35", "Major components: auditor, chain_builder, inference_engine"),
        ("600-1000 lines", "~18", "Heavy components: ingestion, graph_service, evidence_graph"),
        ("1000+ lines", "~8", "Mega-files: work_spec (2.4K), pm_agent (1.2K), nodes (1.2K)"),
    ]
    for b in buckets:
        pdf.table_row(b, widths)

    pdf.ln(6)
    pdf.sub_title("Risk Flags")
    flags = [
        ("work_spec.py at 2,464 lines", "Consider splitting by work type or section"),
        ("pm_agent.py at 1,233 lines", "Monolithic agent; split into sub-agents or skills"),
        ("nodes.py + nodes_v2.py", "Two versions of agent nodes - consolidate"),
        ("Duplicate PDF generators (v3, v4)", "6 PDF scripts in docs/ - extract to shared lib"),
        ("JSON/YAML knowledge base duplication", "Same data in both formats (templates_database)"),
    ]
    for label, note in flags:
        pdf.set_font(UNICODE_FONT, "B", 9)
        pdf.set_text_color(180, 50, 50)
        pdf.cell(0, 5, f"    [!] {label}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(UNICODE_FONT, "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, f"        {note}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.sub_title("Health Indicators")
    pdf.metric_row("Test coverage (lines):", "8,431 lines (1:7 ratio)")
    pdf.metric_row("Type hints:", "Present in most src/core/ files")
    pdf.metric_row("Documentation:", "14,816 lines of MD docs (1:4 doc-to-code ratio)")
    pdf.metric_row("CI/CD:", ".github/workflows/ci.yml present")
    pdf.metric_row("Git activity:", "6+ commits/day average (May 2026)")

    # ── Page 8: Token by Component ──
    pdf.add_page()
    pdf.section_title("6. Token Distribution by Component")

    pdf.sub_title("Core Engine (src/core/)")
    core_components = [
        ("parser_engine.py", "780 lines", "~12K"),
        ("ingestion.py", "964 lines", "~15K"),
        ("auditor.py", "822 lines", "~13K"),
        ("evidence_graph.py", "734 lines", "~11K"),
        ("chain_builder.py", "498 lines", "~8K"),
        ("inference_engine.py", "529 lines", "~8K"),
        ("graph_service.py", "914 lines", "~14K"),
        ("vlm_classifier.py", "312 lines", "~5K"),
        ("hitl_system.py", "421 lines", "~7K"),
        ("journal_reconstructor.py", "527 lines", "~8K"),
        ("project_loader.py", "304 lines", "~5K"),
        ("scan_detector.py", "122 lines", "~2K"),
        ("Subtotal (core)", "~7,200 lines", "~110K"),
    ]
    cols = ["Module", "Lines", "Est. Tokens"]
    widths = [65, 40, 40]
    pdf.table_header(cols, widths)
    for mod, lines, tok in core_components:
        bold = "Subtotal" in mod
        pdf.table_row([mod, lines, tok], widths, bold_last=bold)

    pdf.ln(4)
    pdf.sub_title("Services Layer (src/core/services/)")
    services = [
        ("legal_service.py", "752 lines", "~12K"),
        ("pto_agent.py", "866 lines", "~14K"),
        ("delo_agent.py", "542 lines", "~9K"),
        ("id_requirements.py", "212 lines", "~3K"),
        ("PPR generator (dir)", "~1,900 lines", "~30K"),
        ("IS generator (dir)", "~1,200 lines", "~19K"),
        ("Subtotal (services)", "~5,500 lines", "~87K"),
    ]
    pdf.table_header(cols, widths)
    for mod, lines, tok in services:
        bold = "Subtotal" in mod
        pdf.table_row([mod, lines, tok], widths, bold_last=bold)

    # ── Page 9: Final ──
    pdf.add_page()
    pdf.section_title("7. Recommendations")

    pdf.set_font(UNICODE_FONT, "", 10)
    pdf.set_text_color(60, 60, 60)
    recs = [
        ("1. Split mega-files",
         "work_spec.py (2,464 lines), pm_agent.py (1,233 lines), and nodes.py (1,207 lines) "
         "are candidates for decomposition. Each 2x size reduction cuts context-window cost "
         "for agent tool calls that reference these files."),
        ("2. Deduplicate knowledge base formats",
         "pto_templates_database exists as both YAML (10K lines) and JSON (11K lines). "
         "Pick one canonical format, generate the other at build time."),
        ("3. Consolidate PDF generators",
         "docs/ contains 6+ PDF generation scripts (v3, v4, etc.). Extract shared layout, "
         "font, and table utilities into a common lib."),
        ("4. Merge nodes.py and nodes_v2.py",
         "Two versions of agent nodes exist. If v2 supersedes v1, remove v1; "
         "otherwise, document the difference or unify behind a feature flag."),
        ("5. Bump test coverage",
         "Test-to-source ratio of 1:7 is below typical 1:3 for production systems. "
         "Prioritize tests for inference_engine, auditor, and evidence_graph."),
        ("6. Model context strategy",
         "At ~920K Python tokens, the codebase fits Gemini 2.5 Pro (1M) for full-context "
         "analysis. For Claude (200K), maintain a chunked RAG index of src/core/ files "
         "so agents can retrieve relevant modules on demand."),
    ]
    for title, body in recs:
        pdf.set_font(UNICODE_FONT, "B", 10)
        pdf.set_text_color(30, 60, 120)
        pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(UNICODE_FONT, "", 9)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 5, body)
        pdf.ln(2)

    # ── Save ──
    out = "artifacts/MAC_ASD_Metrics_Report.pdf"
    pdf.output(out)
    print(f"Report saved: {out}")
    return out


if __name__ == "__main__":
    build_report()
