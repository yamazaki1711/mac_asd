#!/usr/bin/env python3
"""Generate MAC_ASD v13.0 Comprehensive Technical Analysis as PDF."""

import os, sys
from datetime import date
from pathlib import Path
from fpdf import FPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSansCondensed.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSansCondensed-Bold.ttf")
FONT_MONO = os.path.join(FONT_DIR, "DejaVuSansMono.ttf")

TODAY = date.today().strftime("%d %B %Y")
COMMIT = os.popen("git -C " + str(PROJECT_ROOT) + " rev-parse --short HEAD").read().strip()

DARK = (30, 60, 120)
MID = (60, 60, 60)
LIGHT = (120, 120, 120)
WHITE = (255, 255, 255)


class TechReport(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("R", "", FONT_REGULAR, uni=True)
        self.add_font("R", "B", FONT_BOLD, uni=True)
        self.add_font("M", "", FONT_MONO, uni=True)

    def header(self):
        if self.page_no() > 1:
            self.set_font("R", "B", 7)
            self.set_text_color(*LIGHT)
            self.cell(0, 4, "MAC_ASD v13.0 — Technical Analysis", align="L")
            self.cell(0, 4, TODAY, align="R", new_x="LMARGIN", new_y="NEXT")
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("R", "", 7)
        self.set_text_color(*LIGHT)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def title_page(self):
        self.add_page()
        self.ln(35)
        self.set_font("R", "B", 30)
        self.set_text_color(*DARK)
        self.cell(0, 14, "MAC_ASD", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("R", "", 16)
        self.set_text_color(*MID)
        self.cell(0, 10, "v13.0 — Comprehensive Technical Analysis", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        mid = self.w / 2
        self.set_draw_color(*DARK)
        self.line(mid - 35, self.get_y(), mid + 35, self.get_y())
        self.ln(10)
        self.set_font("R", "", 10)
        self.set_text_color(*LIGHT)
        self.cell(0, 7, f"Generated: {TODAY}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, f"Commit: {COMMIT}  |  Branch: main", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, "Repository: github.com/yamazaki1711/mac_asd", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, "Profile: dev_linux (DeepSeek V4 Pro[1m])", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(12)
        self.set_font("R", "", 8)
        self.set_text_color(*LIGHT)
        self.cell(0, 5, "Confidential — OOO «КСК №1»", align="C", new_x="LMARGIN", new_y="NEXT")

    def section(self, title):
        self.set_font("R", "B", 15)
        self.set_text_color(*DARK)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*DARK)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def sub(self, title):
        self.set_font("R", "B", 11)
        self.set_text_color(*MID)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text):
        self.set_font("R", "", 9)
        self.set_text_color(*MID)
        self.multi_cell(0, 5, text)
        self.ln(2)

    def bullet(self, text, indent=4):
        self.set_font("R", "", 9)
        self.set_text_color(*MID)
        x = self.l_margin + indent
        self.cell(indent, 5, "")
        self.set_font("R", "", 9)
        self.cell(3, 5, chr(8226))
        self.multi_cell(self.w - self.r_margin - x - 3, 5, text)

    def metric_row(self, label, value, w1=115, w2=55):
        self.set_font("R", "", 9)
        self.set_text_color(*MID)
        self.cell(w1, 6, f"  {label}")
        self.set_font("R", "B", 9)
        self.set_text_color(*DARK)
        self.cell(w2, 6, str(value), new_x="LMARGIN", new_y="NEXT")

    def table(self, headers, rows, widths, bold_col=None):
        if bold_col is None:
            bold_col = []
        self.set_fill_color(*DARK)
        self.set_text_color(*WHITE)
        self.set_font("R", "B", 8)
        for h, w in zip(headers, widths):
            self.cell(w, 6, f" {h}", fill=True)
        self.ln()
        self.set_text_color(*MID)
        for i, row in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(245, 247, 250)
            else:
                self.set_fill_color(*WHITE)
            for j, (cell, w) in enumerate(zip(row, widths)):
                self.set_font("R", "B", 8) if j in bold_col else self.set_font("R", "", 8)
                self.cell(w, 5.5, f" {cell}", fill=True)
            self.ln()
        self.ln(3)

    def code_block(self, text):
        self.set_font("M", "", 7)
        self.set_text_color(*MID)
        self.set_fill_color(245, 247, 250)
        for line in text.split("\n")[:30]:
            self.cell(0, 4, f"  {line}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def check_page_break(self, needed=40):
        if self.get_y() > self.h - needed:
            self.add_page()


def build_report():
    pdf = TechReport()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)

    # ═══════════════════════════════════════════════════════════════════
    pdf.title_page()

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("1. Executive Summary")

    pdf.body(
        "MAC_ASD is a multi-agent system for automating executive documentation (ID) "
        "for construction contractors. Built for OOO «KSK №1». Fully local, offline-first. "
        "Two operational modes: (1) сопровождение — real-time document generation during construction; "
        "(2) антикризис (forensic) — reconstruction of work history from scattered evidence "
        "(invoices, certificates, photos, witness statements)."
    )
    pdf.body(
        "Version 13.0 introduces three real PTO skill modules replacing critical stubs: "
        "VorCheck (VOR↔PD fuzzy comparison), PDAnalysis (3-stage PD collision detection), "
        "and ActGenerator (DOCX act generation via docxtpl). Coverage of the 8-stage PSED "
        "expertise pipeline improved from ~35% to ~70%."
    )

    pdf.sub("Key Metrics")
    pdf.metric_row("Python source files:", "231")
    pdf.metric_row("Total lines of code:", "75,562")
    pdf.metric_row("Source lines (src/):", "50,440")
    pdf.metric_row("Test lines (tests/):", "8,976")
    pdf.metric_row("Agent code (src/agents/):", "10,518")
    pdf.metric_row("MCP server code:", "4,100")
    pdf.metric_row("Tests:", "508 passed / 3 failed / 15 skipped (99.4%)")
    pdf.metric_row("MCP tools registered:", "75+")
    pdf.metric_row("Agents:", "8 (7 LLM + Auditor)")
    pdf.metric_row("Database tables:", "27")
    pdf.metric_row("Normative documents:", "284 files, 101 MB")
    pdf.metric_row("Git commits:", "98")
    pdf.metric_row("YAML configs:", "22")
    pdf.metric_row("Markdown docs:", "44")
    pdf.ln(4)

    # ═══════════════════════════════════════════════════════════════════
    pdf.section("2. Architecture Overview")

    pdf.body(
        "The system is built around a LangGraph StateGraph workflow orchestrated by a PM agent. "
        "All LLM calls go through a unified LLMEngine supporting three backends "
        "(DeepSeek API, Ollama, MLX). The central data structure is the Evidence Graph v2 — "
        "a NetworkX DiGraph with 7 node types, 13 edge types, and a confidence framework (0-1) "
        "on every node and edge."
    )

    pdf.sub("Architecture Stack")
    pdf.code_block(
        "MCP Server (FastMCP, 75+ tools)\n"
        "    ↓\n"
        "LangGraph Workflow (PM → fan-out → [agent_worker × N] → pm_evaluate)\n"
        "    ↓\n"
        "LLMEngine (DeepSeekBackend | OllamaBackend | MLXBackend)\n"
        "    ↓\n"
        "Evidence Graph v2 (NetworkX DiGraph, 7 node types, confidence 0-1)\n"
        "    ↓\n"
        "PostgreSQL 16 + pgvector (bge-m3, 1024 dim, 27 tables)"
    )

    pdf.sub("Data Pipeline")
    pdf.code_block(
        "PD/RD → ProjectLoader → WorkUnit (PLANNED)\n"
        "    ↓\n"
        "ParserEngine → OCR → DocumentClassifier (15 types) → HybridClassifier\n"
        "    ↓\n"
        "Evidence Graph (nodes + edges + confidence)\n"
        "    ↓\n"
        "Inference Engine (6 rules) → new WorkUnit (INFERRED)\n"
        "    ↓\n"
        "Chain Builder → DocumentChain (MaterialBatch→Cert→AOSR→KS-2)\n"
        "    ↓\n"
        "Journal Reconstructor → OZHR (5 stages, color coding)\n"
        "    ↓\n"
        "HITL → operator questions → confidence boost\n"
        "    ↓\n"
        "Auditor → 11 rule-based checks → REJECT/APPROVED"
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("3. Agents")

    pdf.body(
        "8 specialized agents, 7 LLM-powered + 1 rule-based Auditor. "
        "On mac_studio: 5 agents share a single Gemma 4 31B instance (128K context). "
        "On dev_linux: all 7 use DeepSeek V4 Pro[1m] via API."
    )

    pdf.table(
        ["Agent", "Model (dev_linux)", "Model (mac_studio)", "Lines", "Key Skills"],
        [
            ["PM", "deepseek-reasoner", "Llama 3.3 70B 4bit", "2,051", "WorkPlan, WeightedScoring, Fan-out"],
            ["PTO", "deepseek-chat", "Gemma 4 31B VLM 4bit", "4,121", "WorkSpec(33), VorCheck, PDAnalysis, ActGen"],
            ["Legal", "deepseek-chat", "Gemma 4 31B 4bit", "2,391", "ContractRisks, BLS(61), Map-Reduce"],
            ["Smeta", "deepseek-chat", "Gemma 4 31B 4bit", "2,194", "Calc, RateLookup, VorCompare"],
            ["Procurement", "deepseek-chat", "Gemma 4 31B 4bit", "401", "TenderSearch, Profitability"],
            ["Logistics", "deepseek-chat", "Gemma 4 31B 4bit", "46", "SourceVendors, CompareQuotes"],
            ["Clerk", "deepseek-chat", "Gemma 4 E4B 4bit", "966", "TemplateLib, Registration, Letters"],
            ["Auditor", "rule-based", "rule-based", "822", "11 checks (no LLM-as-Judge)"],
        ],
        [24, 34, 34, 18, 60],
    )

    pdf.sub("PTO Agent — Core of 8-Stage PSED Expertise")
    pdf.body(
        "The PTO agent is the most complex agent with 4,121 lines of code. "
        "It now provides 11 MCP tools covering full executive documentation lifecycle: "
        "work type specification (PTO_WorkSpec, 33 WorkType enum values), "
        "VOR↔PD comparison (VorCheck with rapidfuzz + trigram fallback), "
        "PD collision analysis (PDAnalysis: spatial + completeness + LLM semantic), "
        "act document generation (ActGenerator: docxtpl + python-docx), "
        "ID completeness checking (IDRequirementsRegistry), "
        "geo-context enrichment (Yandex Geocoder + Open-Meteo weather), "
        "and Vision Cascade for drawing analysis (overview + tile detail)."
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("4. Core Systems (28 modules)")

    pdf.table(
        ["Module", "Lines", "Status", "Function"],
        [
            ["pm_agent.py", "1,290", "DONE", "Orchestrator: WorkPlan, dispatch, weighted scoring"],
            ["work_spec.py", "2,464", "DONE", "33 WorkType, full ID document trail (SkillBase)"],
            ["legal_service.py", "972", "DONE", "Quick Review + Map-Reduce + BLS + NormativeGuard"],
            ["ingestion.py", "975", "DONE", "OCR→classify→extract→graph pipeline"],
            ["graph_service.py", "914", "DONE", "NetworkX knowledge graph (legacy)"],
            ["pto_agent.py", "893", "DONE", "Inventory, AOSR trail, cross-check, completeness"],
            ["auditor.py", "822", "DONE", "11 rule-based checks (no LLM-as-Judge)"],
            ["parser_engine.py", "780", "DONE", "PDF (PyMuPDF→Tesseract→VLM) + XLSX + DOCX"],
            ["evidence_graph.py", "734", "DONE", "Evidence Graph v2: 7 node types, confidence"],
            ["ram_manager.py", "624", "DONE", "128GB Unified Memory management"],
            ["quality_metrics.py", "529", "DONE", "Quality Cascade: 5 stages, loss waterfall"],
            ["inference_engine.py", "529", "DONE", "6 symbolic rules for date/fact inference"],
            ["journal_reconstructor.py", "527", "DONE", "5-stage OZHR reconstruction, color coding"],
            ["chain_builder.py", "498", "DONE", "MaterialBatch→Cert→AOSR→KS-2 chains"],
            ["llm_engine.py", "431", "DONE", "Unified LLM interface: DeepSeek/Ollama/MLX"],
            ["hitl_system.py", "421", "DONE", "Operator questions with priorities"],
            ["pd_analysis.py", "418", "DONE", "3-stage PD analysis (new in v13.0)"],
            ["hybrid_classifier.py", "403", "DONE", "Keyword + VLM hybrid classification"],
            ["knowledge_base.py", "338", "DONE", "pgvector RAG + DomainClassifier"],
            ["vor_check.py", "326", "DONE", "VOR↔PD fuzzy matching (new in v13.0)"],
            ["observability.py", "325", "DONE", "JSON logging, @observe_step, health_check"],
            ["project_loader.py", "304", "PARTIAL", "PD/RD → WorkUnit; load_from_folder() stub"],
            ["act_generator.py", "273", "DONE", "DOCX act generation (new in v13.0)"],
            ["document_repository.py", "226", "DONE", "CRUD + pgvector search, lazy DB imports"],
            ["container_setup.py", "145", "DONE", "DI bootstrap: infra → agents → services"],
            ["container.py", "128", "DONE", "Type-keyed DI container, lazy singletons"],
            ["invalidation_engine.py", "92", "DONE", "Regulatory change tracking"],
        ],
        [38, 14, 16, 102],
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("5. MCP Tools (75+ in 17 groups)")

    pdf.table(
        ["Group", "Count", "Target Agent", "Key Tools"],
        [
            ["Jurist", "7", "Legal", "upload_document, analyze_contract, generate_protocol/claim/lawsuit"],
            ["PTO", "11", "PTO", "vor_check, pd_analysis, generate_act, id_completeness, work_type_info"],
            ["Smeta", "5", "Smeta", "estimate_compare, create_lsr, supplement_estimate, rate_lookup"],
            ["Clerk", "7", "Delo", "register_document, generate_letter, prepare_shipment, track_deadlines"],
            ["Procurement", "2", "Procurement", "tender_search, analyze_lot_profitability"],
            ["Logistics", "3", "Logistics", "source_vendors, add_price_list, compare_quotes"],
            ["Lab Control", "13", "PTO/Proc/Log/Delo", "Full cycle: plan→sample→test→report→file"],
            ["Google Workspace", "16", "All", "Drive(6), Sheets(5), Docs(3), Gmail(1), Status(1)"],
            ["Artifact Store", "3", "All", "Versioned file storage: list, write, read"],
            ["Legal Service", "3", "Legal", "fz_lookup, rag_query, legal_search"],
            ["Vision Cascade", "2", "PTO", "2-stage drawing analysis: overview + tile detail"],
            ["Evidence Graph", "6", "All", "query, get_chain, summary, inference_run, project_load"],
            ["Chain Builder", "3", "PTO, PM", "build, report, validate"],
            ["HITL", "3", "PM, All", "generate, answer, status"],
            ["Journal", "3", "PTO, Clerk", "reconstruct, export, verify"],
            ["Lessons Learned", "4", "All", "search, add, get_stats, export"],
            ["General", "1", "All", "get_system_status"],
        ],
        [28, 14, 46, 82],
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("6. Key Architectural Decisions")

    decisions = [
        ("Shared memory for 5 agents",
         "On mac_studio, Gemma 4 31B (128K) serves PTO/Legal/Smeta/Procurement/Logistics. "
         "Switching is done via system prompt change without model reload. ~23 GB RAM for 5 agents."),
        ("Confidence framework",
         "Every node and edge in Evidence Graph has confidence (0-1). INFERRED nodes (0.4-0.85) "
         "transition to CONFIRMED through HITL or new evidence. Color coding: green ≥0.8, yellow ≥0.6, red ≥0.4, gray <0.4."),
        ("Three LLM backends",
         "Polymorphic interface: DeepSeekBackend (API), OllamaBackend (local), MLXBackend (Mac). "
         "DeepSeek transparently falls back to Ollama for embeddings (bge-m3, 1024 dim). "
         "Retry: 3 attempts, exponential backoff, safe_chat() with fallback_response."),
        ("RAM-aware orchestration",
         "PM dynamically adjusts max_parallel: 5 (normal RAM), 2 (warning), 1 (critical). "
         "Every node checks ram_manager before dispatching. OOM prevention at architecture level."),
        ("Structural chunking",
         "12000/2400 characters with section and table boundary preservation. "
         "Contracts and specifications are never split mid-section. 128K context (Gemma 4 31B) "
         "eliminates Map-Reduce for most documents (<280K chars)."),
        ("Rule-based Auditor",
         "11 checks without LLM-as-Judge: cross-agent consistency (PTO vs Smeta, Legal vs PTO, "
         "Smeta vs Procurement), forensic document checks (batch coverage, certificate reuse, "
         "orphan certificates, material spec validation), and classification quality checks "
         "(type self-consistency, VLM vs keyword mismatch, unsigned critical docs). "
         "No hallucinations in audit findings."),
        ("Quality Cascade",
         "5-stage measurement: OCR → Classification → VLM Fallback → Entity Extraction → "
         "Graph Ingestion. Loss waterfall shows only ~13% of quality loss is on LLM. "
         "Inspired by AFIDA/Gazprom CPS production analysis (2025)."),
        ("NormativeGuard SSOT",
         "All LLM responses from Legal/PTO are validated against normative_index.json "
         "(284 documents from library/normative/). References not found in the index "
         "are marked UNVERIFIED. Prevents LLM from citing non-existent GOST/SP standards."),
        ("IDRequirementsRegistry SSOT",
         "33 construction work types mapped to mandatory document trails per Order 344/pr. "
         "Computes delta between required and present documents. Used by PTO agent, "
         "Auditor, and PM for compliance tracking."),
        ("Lazy imports everywhere",
         "DocumentRepository, container_setup, all agent services use try/except ImportError. "
         "System degrades gracefully when PostgreSQL or optional modules are unavailable. "
         "Works on dev machines without full infrastructure."),
    ]

    for title, desc in decisions:
        pdf.check_page_break(25)
        pdf.set_font("R", "B", 9)
        pdf.set_text_color(*DARK)
        pdf.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("R", "", 8)
        pdf.set_text_color(*MID)
        pdf.multi_cell(0, 4.5, desc)
        pdf.ln(2)

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("7. Evidence Graph v2")

    pdf.body(
        "The Evidence Graph is the central data structure for both operational modes "
        "(construction support and forensic reconstruction). Built on NetworkX DiGraph "
        "with file persistence to data/graphs/."
    )

    pdf.sub("Node Types (7)")
    pdf.table(
        ["Type", "Description", "Key Attributes"],
        [
            ["WorkUnit", "A unit of construction work", "work_type, status, confidence, start_date, end_date, volume"],
            ["MaterialBatch", "A batch of material delivered", "material_name, batch_number, quantity, gost, delivery_date"],
            ["Document", "Any document (AOSR, KS-2, cert, etc.)", "doc_type, doc_number, doc_date, signatures_present, status"],
            ["Person", "A person involved", "name, role, organization, reliability"],
            ["DateEvent", "A dated event", "event_type, timestamp, precision, confidence"],
            ["Volume", "A work volume measurement", "value, unit, source, confidence"],
            ["Location", "A physical location", "name, parent_id, description"],
        ],
        [30, 50, 90],
    )

    pdf.sub("Edge Types (13)")
    pdf.code_block(
        "USED_IN:        MaterialBatch → WorkUnit (quantity)\n"
        "CONFIRMED_BY:   WorkUnit → Document\n"
        "REFERENCES:     Document → Document\n"
        "TEMPORAL_BEFORE/AFTER: WorkUnit → WorkUnit (sequencing)\n"
        "LOCATED_AT:     WorkUnit → Location\n"
        "SUPPLIED_BY:    MaterialBatch → Person\n"
        "SIGNED_BY:      Document → Person\n"
        "DERIVED_FROM:   WorkUnit → WorkUnit (forensic inference)\n"
        "HAS_EVENT:      WorkUnit → DateEvent\n"
        "DEFINES_VOLUME: Volume → WorkUnit\n"
        "MENTIONS:       Document → MaterialBatch\n"
        "CONTAINS:       Location → Location (hierarchy)\n"
        "PART_OF:        WorkUnit → WorkUnit (decomposition)\n"
        "ATTRIBUTED_TO:  DateEvent → Person"
    )

    pdf.sub("Inference Engine — 6 Symbolic Rules")
    rules = [
        "Delivery → Dates: MaterialBatch.delivery_date + typical_rate → WorkUnit.start/end_date",
        "KS-2 → WorkUnit: Signed KS-2 confirms WorkUnit existed on KS-2 date (confidence=0.8)",
        "Photo → DateEvent: EXIF-tagged photo creates DateEvent (confidence=0.85)",
        "Delivery → Location: MaterialBatch location propagates to WorkUnit (confidence=0.7)",
        "Temporal Chain: WorkUnit_A.end_date → WorkUnit_B.start_date (confidence=0.85×source)",
        "Confidence Boost: Confirmed DERIVED_FROM target boosts source confidence (×1.2, cap 0.95)",
    ]
    for r in rules:
        pdf.bullet(r)
    pdf.ln(3)

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("8. Agent Skills (24 modules)")

    pdf.table(
        ["Skill", "Agent", "Lines", "Function"],
        [
            ["PTO_WorkSpec", "PTO", "2,464", "33 WorkType, full ID document trail"],
            ["PTO_Compliance", "PTO", "436", "Merge work_spec + idprosto + templates"],
            ["PTO_PDAnalysis", "PTO", "418", "3-stage PD collision detection (v13.0)"],
            ["PTO_VorCheck", "PTO", "326", "VOR↔PD fuzzy matching (v13.0)"],
            ["PTO_ActGenerator", "PTO", "273", "DOCX act generation (v13.0)"],
            ["Smeta_RateLookup", "Smeta", "929", "FER/GESN/TER rate code search"],
            ["Smeta_Calc", "Smeta", "414", "LSR calculation"],
            ["Smeta_VorCompare", "Smeta", "410", "VOR↔estimate comparison"],
            ["Legal_ContractRisks", "Legal", "674", "BLS 61 traps + contract analysis"],
            ["Legal_IDComposition", "Legal", "565", "ID document composition rules"],
            ["Delo_TemplateLib", "Clerk", "418", "Letter/document templates"],
            ["WorkTypeRegistry", "Common", "279", "Cross-agent work type mappings"],
            ["SkillBase", "Common", "174", "Base class: execute(), validate_input()"],
            ["RegistrySetup", "Common", "58", "Skill registration bootstrap"],
        ],
        [34, 16, 16, 104],
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.section("9. Maturity Assessment by Functional Block")

    pdf.table(
        ["Functional Block", "Maturity", "Key Gaps"],
        [
            ["Document inventory + classification", "80%", "Visual classification (YOLO)"],
            ["VLM/OCR recognition", "60%", "Handwritten notes, nested tables"],
            ["8-stage PSED expertise", "70%", "Stage 7 (Math verification), 8 (XAI + GOST citations)"],
            ["Estimating (Smeta)", "75%", "FSIS CS split-forms"],
            ["Legal analysis", "85%", "61 BLS traps, Map-Reduce, NormativeGuard"],
            ["Business correspondence", "70%", "RFI templates, auto-replies"],
            ["Generative planning (ALICE-like)", "15%", "Entirely new module"],
            ["M-29 material write-off", "25%", "Entirely new module"],
            ["CV site control (GOST 71718)", "10%", "Site photos, defect detection"],
            ["PM orchestration", "80%", "RAM-aware fan-out, fallback chains"],
            ["Auditor", "75%", "GOST citations in findings"],
            ["Evidence Graph", "80%", "ProjectLoader.load_from_folder()"],
            ["Journal Reconstructor", "75%", "GOST R 70108-2022 EOZHR format"],
            ["HITL", "70%", "Telegram integration"],
            ["Observability", "75%", "Grafana dashboard"],
            ["Knowledge Base", "70%", "Dynamic supplier price updates"],
        ],
        [50, 30, 90],
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("10. Technology Stack & Profiles")

    pdf.sub("Infrastructure")
    pdf.table(
        ["Component", "Technology", "Details"],
        [
            ["Language", "Python 3.11+", "Type hints (strict), Pydantic schemas"],
            ["Framework", "LangGraph + FastMCP", "StateGraph workflow, 75+ MCP tools via stdio"],
            ["Database", "PostgreSQL 16 + pgvector", "27 tables, bge-m3 embeddings (1024 dim), port 5433"],
            ["Migrations", "Alembic", "Autogenerate from SQLAlchemy models"],
            ["Graph", "NetworkX DiGraph", "In-memory + pickle/GML serialization to data/graphs/"],
            ["Container", "Docker Compose", "PostgreSQL + pgvector, port 5433"],
            ["DI", "Custom ServiceContainer", "Type-keyed, lazy singletons, test overrides"],
            ["Observability", "JSON structured logging", "Grafana/Prometheus target, @observe_step decorator"],
        ],
        [28, 46, 96],
    )

    pdf.sub("LLM Profiles")
    pdf.table(
        ["Agent", "dev_linux (DeepSeek)", "mac_studio (MLX)"],
        [
            ["PM", "deepseek-reasoner", "Llama 3.3 70B 4bit (~40 GB)"],
            ["PTO", "deepseek-chat", "Gemma 4 31B VLM 4bit"],
            ["Legal", "deepseek-chat", "Gemma 4 31B 4bit (shared ~23 GB)"],
            ["Smeta", "deepseek-chat", "Gemma 4 31B 4bit (shared)"],
            ["Procurement", "deepseek-chat", "Gemma 4 31B 4bit (shared)"],
            ["Logistics", "deepseek-chat", "Gemma 4 31B 4bit (shared)"],
            ["Clerk", "deepseek-chat", "Gemma 4 E4B 4bit (~3 GB)"],
            ["Embeddings", "bge-m3 (Ollama)", "bge-m3-mlx-4bit (~0.3 GB)"],
            ["Vision", "gemma4:31b-cloud (Ollama)", "Gemma 4 31B VLM (shared)"],
        ],
        [34, 56, 80],
    )
    pdf.ln(2)
    pdf.body(
        "Total VRAM on mac_studio: ~66.3 GB for 3 unique models. "
        "DeepSeek V4 Pro[1m] provides 1M context on dev_linux with reasoning mode. "
        "Context: dev_linux cached system prompt + project context (~1/4 of input cost on DeepSeek cache)."
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.section("11. Database Schema (27 tables)")

    pdf.table(
        ["Table", "Rows (typ.)", "Size", "Description"],
        [
            ["projects", "~3", "1 MB", "Construction projects"],
            ["documents", "~200", "50 MB", "All uploaded documents"],
            ["chunks", "~8,000", "500 MB", "Document chunks + embeddings (bge-m3, 1024d)"],
            ["contracts", "~10", "1 MB", "Contract details + ProtocolPartyInfo"],
            ["traps", "61", "1 MB", "BLS trap library (61 traps, 10 categories)"],
            ["trap_matches", "~200", "5 MB", "Detected trap matches in documents"],
            ["claims", "~5", "1 MB", "Legal claims"],
            ["lawsuits", "~2", "1 MB", "Court lawsuits"],
            ["vor / vor_items", "~30 / 15,000", "15 MB", "Volume of Work statements + items"],
            ["estimates / estimate_items", "~20 / 3,000", "15 MB", "Cost estimates + line items"],
            ["acts", "~100", "5 MB", "AOSR, incoming control, hidden works acts"],
            ["letters", "~50", "5 MB", "Business correspondence"],
            ["registrations", "~100", "5 MB", "Incoming document registration"],
            ["shipments", "~20", "5 MB", "Document packages sent to customer"],
            ["supplements", "~10", "1 MB", "Contract supplements"],
            ["vendors", "~100", "2 MB", "Vendor/supplier registry"],
            ["materials_catalog", "~5,000", "10 MB", "Unified materials nomenclature"],
            ["price_lists / items", "~50 / 2,000", "10 MB", "Price lists + line items"],
            ["wiki_articles", "~500", "10 MB", "Knowledge base articles (Markdown)"],
            ["audit_log", "~2,000", "10 MB", "All system actions"],
            ["construction_zones", "~20", "1 MB", "Construction zones (захватки, участки)"],
            ["construction_elements", "~500", "5 MB", "Construction elements (ростверк, свая, etc.)"],
            ["work_entries", "~2,000", "5 MB", "Work journal entries (→ AOSR trigger)"],
            ["element_documents", "~1,000", "3 MB", "Documents linked to construction elements"],
        ],
        [34, 28, 18, 90],
    )
    pdf.ln(2)
    pdf.body("Total estimated DB size for a typical 2-year construction project: ~650 MB.")

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("12. Testing & Quality")

    pdf.body(
        "508 tests passing (99.4%), 3 pre-existing failures (hypothesis scoring invariant, "
        "ram_manager context size, delo_agent import). 15 skipped tests. "
        "Test framework: pytest with asyncio auto mode. All tests are synchronous "
        "def test_* methods. No fixtures — objects constructed inline. Plain assert only."
    )

    pdf.sub("Test Breakdown")
    pdf.table(
        ["Test File", "Tests", "Area"],
        [
            ["test_vor_check.py", "14", "VOR↔PD fuzzy comparison (new v13.0)"],
            ["test_pd_analysis.py", "10", "PD collision detection (new v13.0)"],
            ["test_act_generator.py", "9", "DOCX act generation (new v13.0)"],
            ["test_legal_service.py", "~30", "Contract analysis + chunking"],
            ["test_workplan.py", "~35", "PM WorkPlan + weighted scoring"],
            ["test_hypothesis_scoring.py", "~25", "Property-based scoring tests"],
            ["test_smoke.py", "~60", "Integration smoke tests"],
            ["test_e2e_forensic.py", "~20", "End-to-end forensic pipeline"],
            ["test_rag_pipeline.py", "~25", "RAG pipeline"],
            ["test_orchestration.py", "~30", "Orchestration + RAM management"],
            ["Others (10 files)", "~300", "Remaining unit tests"],
        ],
        [48, 18, 104],
    )

    pdf.sub("Quality Cascade Metrics")
    pdf.code_block(
        "OCR → Classification → VLM Fallback → Entity Extraction → Graph Ingestion\n"
        " 91%  →     83%      →    100%     →       100%      →      100%\n\n"
        "Domain Benchmark (LOS, 12 PDF):\n"
        "  Classification accuracy without VLM: 36%\n"
        "  Classification accuracy with VLM (Gemma 4 31B): 92%\n"
        "  UNKNOWN documents: 0 (0%) with VLM\n"
        "  Micro-errors: 2/12 (KS-3 confused with KS-2; KS-6a → journal)"
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.section("13. Regulatory Framework")

    pdf.body(
        "The system operates within the Russian construction regulatory framework. "
        "NormativeGuard validates all LLM outputs against 284 normative documents (101 MB) "
        "in library/normative/. The IDRequirementsRegistry provides SSOT for 33 construction "
        "work types per Order 344/pr."
    )

    pdf.sub("Key Regulatory Documents")
    regs = [
        "Order 344/pr (Ministry of Construction) — executive documentation composition",
        "Order 1026/pr — construction work journals",
        "GOST R 70108-2025 — electronic executive documentation",
        "GOST R 71718-2024 — AI and mixed reality for visual control of OKS geometric parameters",
        "GOST R 71750-2024 — intelligent systems terminology in construction-road machinery",
        "GOST R 21.1101-2013 — design documentation system, core requirements",
        "SP 543.1325800.2024 — construction control, Appendix A (ID per work type)",
        "SP 70.13330.2012 — load-bearing structures",
        "SP 48.13330.2019 — construction organization",
        "VSN 012-88 — welding (oil & gas)",
        "PP RF №468 — acceptance of completed construction works",
        "PP RF №249 — construction control procedures",
        "FZ-44 — public procurement",
        "FZ-223 — procurement by certain legal entities",
        "BLS — 61 subcontractor traps in 10 categories (YAML + pgvector RAG)",
    ]
    for r in regs:
        pdf.bullet(r)
    pdf.ln(3)

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("14. v13.0 Changes Summary")

    pdf.body(
        "Version 13.0 (May 4, 2026) introduces critical PTO skill modules replacing stubs "
        "that returned empty results. This directly addresses the 8-stage PSED expertise "
        "pipeline gaps identified in the strategic analysis document "
        "'AI for PTO Engineer: Implementation and Application' (31 sources)."
    )

    pdf.sub("New Files (6)")
    pdf.code_block(
        "src/agents/skills/pto/vor_check.py         326 lines   VOR↔PD fuzzy matching\n"
        "src/agents/skills/pto/pd_analysis.py        418 lines   3-stage PD collision detection\n"
        "src/agents/skills/pto/act_generator.py      273 lines   DOCX act document generation\n"
        "tests/test_vor_check.py                     209 lines   14 tests\n"
        "tests/test_pd_analysis.py                   191 lines   10 tests\n"
        "tests/test_act_generator.py                 145 lines    9 tests"
    )

    pdf.sub("Modified Files (1)")
    pdf.code_block(
        "mcp_servers/asd_core/tools/pto_tools.py   +202/-18 lines   3 stubs → real implementations"
    )

    pdf.sub("Impact")
    pdf.bullet("Test count: 475 → 508 (+33 new tests, 0 regressions)")
    pdf.bullet("PTO agent code: 893 → 4,121 lines (skills + service)")
    pdf.bullet("8-stage PSED expertise coverage: ~35% → ~70%")
    pdf.bullet("Three previously stub MCP tools now return real structured results")
    pdf.bullet("New SkillBase pattern followed: validate_input() + _execute() + SkillResult")
    pdf.ln(4)

    # ═══════════════════════════════════════════════════════════════════
    pdf.section("15. Team & Project")

    pdf.table(
        ["Metric", "Value"],
        [
            ["Primary author", "Oleg Shcherbakov (66 commits)"],
            ["Contributors", "Z User (25), Antigravity Agent (7)"],
            ["Total commits", "98"],
            ["License", "Proprietary (OOO «KSK №1»)"],
            ["Target platform (prod)", "Mac Studio M4 Max 128GB Unified Memory"],
            ["Target platform (dev)", "Linux, RTX 5060 8GB, DeepSeek API"],
            ["Current session profile", "dev_linux via DeepSeek V4 Pro[1m]"],
            ["Architecture", "Multi-agent (8), LangGraph + FastMCP + SQLAlchemy + Alembic"],
            ["Database", "PostgreSQL 16 + pgvector (localhost:5433)"],
            ["Document format", "DOCX (docxtpl + python-docx) + PDF (fpdf2)"],
        ],
        [48, 122],
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("16. Domain Benchmark Results")

    pdf.body(
        "Domain benchmark on real construction documents (LOS project, 12 PDF files). "
        "Inspired by AFIDA approach (Gazprom CPS, 2025): quality cascade + custom benchmark on domain data."
    )

    pdf.table(
        ["Metric", "Without VLM", "With VLM (Gemma 4 31B)"],
        [
            ["Classification accuracy", "36%", "92%"],
            ["VLM fallback rate", "0%", "92%"],
            ["UNKNOWN documents", "3 (25%)", "0 (0%)"],
            ["AOSR found", "1 of 2", "2 of 2"],
            ["Embedded references detected", "0", "4"],
            ["Processing time", "47 sec", "~6 min"],
            ["Key error", "—", "KS-3 → KS-2 (visually similar), KS-6a → journal"],
        ],
        [46, 56, 68],
    )

    pdf.sub("Quality Cascade (Loss Waterfall)")
    pdf.code_block(
        "100%  ───────────────────────────────────────────\n"
        "      │ OCR loss: -9%\n"
        " 91%  ├──────────────────────────────────────────\n"
        "      │ Classification loss: -8%\n"
        " 83%  ├──────────────────────────────────────────\n"
        "      │ VLM Fallback: +17% (!!! recovery)\n"
        " 100% ├──────────────────────────────────────────\n"
        "      │ Entity Extraction: 0% loss\n"
        " 100% ├──────────────────────────────────────────\n"
        "      │ Graph Ingestion: 0% loss\n"
        " 100% ───────────────────────────────────────────\n\n"
        "VLM fallback recovers quality: classification jumps from 36% to 92%.\n"
        "Only ~13% of total quality loss is attributable to LLM."
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section("17. Roadmap & Next Steps")

    pdf.body("Priority-ordered implementation backlog based on gap analysis:")

    pdf.table(
        ["Priority", "Item", "Complexity", "Impact"],
        [
            ["P0", "Auditor enhancement: GOST citations in findings", "S", "High"],
            ["P0", "Add GOST R 71718-2024 + 71750-2024 to normative_index", "S", "High"],
            ["P1", "XRef cross-section checking (extend pd_analysis)", "S", "Medium"],
            ["P1", "Calculation verification module (Math stage)", "S", "Medium"],
            ["P1", "ProjectLoader.load_from_folder() implementation", "M", "High"],
            ["P2", "M-29 material write-off automation module", "M", "High"],
            ["P2", "Site photo analysis for construction progress (GOST 71718)", "L", "High"],
            ["P2", "Visual classification via YOLO for scanned documents", "M", "Medium"],
            ["P3", "Generative planning module (ALICE-like simulations)", "L", "High"],
            ["P3", "FSIS CS split-forms in Smeta agent", "M", "Medium"],
            ["P3", "RFI-specific templates in Clerk agent", "S", "Low"],
            ["P4", "Dynamic supplier price updates in Knowledge Base", "M", "Medium"],
            ["P4", "GOST R 70108-2022 EOZHR format in Journal Reconstructor", "M", "Medium"],
            ["P4", "Grafana dashboard for observability metrics", "M", "Low"],
        ],
        [14, 84, 20, 52],
    )

    # ═══════════════════════════════════════════════════════════════════
    pdf.section("18. Conclusion")

    pdf.body(
        "MAC_ASD v13.0 represents a mature multi-agent system for construction documentation "
        "automation. The architecture successfully bridges two operational modes "
        "(real-time construction support and forensic reconstruction) through a unified "
        "Evidence Graph with confidence scoring. The system's 8 agents cover the full "
        "construction lifecycle: from tender search through material procurement, "
        "work execution documentation, legal compliance, to final project closeout."
    )
    pdf.body(
        "The key architectural decisions — shared LLM memory for 5 agents, RAM-aware "
        "orchestration, structural chunking, rule-based Auditor, NormativeGuard SSOT "
        "validation — provide a solid foundation. Version 13.0 addresses the most "
        "critical gap: PTO skills for VOR comparison, PD analysis, and act generation "
        "are now real, tested modules rather than stubs."
    )
    pdf.body(
        "The remaining gaps — generative planning, M-29 automation, computer vision "
        "for site control per GOST R 71718-2024 — represent the next frontier. "
        "These modules would transform MAC_ASD from a document automation system "
        "into a comprehensive construction management platform."
    )

    pdf.ln(6)
    pdf.set_font("R", "", 8)
    pdf.set_text_color(*LIGHT)
    pdf.cell(0, 5, f"Generated: {TODAY}  |  Commit: {COMMIT}  |  Profile: dev_linux (DeepSeek V4 Pro[1m])", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "MAC_ASD v13.0 — OOO «KSK №1» — Confidential", align="C", new_x="LMARGIN", new_y="NEXT")

    # ═══════════════════════════════════════════════════════════════════
    output = PROJECT_ROOT / "docs" / "MAC_ASD_Technical_Analysis.pdf"
    pdf.output(str(output))
    return output


if __name__ == "__main__":
    path = build_report()
    print(f"PDF generated: {path}")
    print(f"Size: {path.stat().st_size:,} bytes")
    print(f"Pages: check file")
