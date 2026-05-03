# MAC_ASD v12.0 — AI Subcontractor Documentation Automation

Autonomous multi-agent system for Russian construction subcontractor document management.
Built on LangGraph + pgvector + local LLMs. mac_studio: Llama 3.3 70B + Gemma 4 31B (128K). dev_linux: Gemma 3 12B (32K).

## Architecture

```
User → LangGraph (PM orchestrator) → Workers → MCP Server (60+ tools)
                                         │
                                    Shared Gemma 4 31B
                                         │
                              pgvector (RAG knowledge base)
```

**8 agents**: PM, PTO, Legal, Smeta, Procurement, Logistics, Archive, Auditor (rule-based red-team)

**3 deployment profiles**: `dev_linux` (Ollama), `mac_studio` (MLX, prod), `deepseek` (API, dev bridge)

## Key files

| File | Purpose |
|------|---------|
| `src/main.py` | Entry point — creates project, runs LangGraph pipeline |
| `src/config.py` | Central settings — 3 profiles, models, DB, credentials |
| `src/agents/state.py` | `AgentState` TypedDict — ~40 fields, shared graph state |
| `src/agents/nodes_v2.py` | PM orchestration nodes — planning, dispatch, eval (parallel Send support) |
| `src/core/pm_agent.py` | PM orchestrator — `WorkPlan`, `TaskNode`, weighted scoring, veto rules |
| `src/core/llm_engine.py` | LLM abstraction — backends (MLX, Ollama, DeepSeek) |
| `src/core/model_router.py` | Model selection per agent profile |
| `src/core/ram_manager.py` | RAM pressure monitoring and OOM prevention |

### Agent services

| File | Agent | LLM? | Domain |
|------|-------|------|--------|
| `src/core/services/pto_agent.py` (893L) | PTO Engineer | Yes | Executive docs (344/pr), AOSR trails, cross-checks |
| `src/core/services/legal_service.py` (973L) | Legal Counsel | Yes | Contract analysis, BLS traps, NormativeGuard |
| `src/core/services/legal_documents.py` (1179L) | Legal Docs | Yes | Protocol/disagreement, claim, lawsuit generation |
| `src/core/services/smeta_agent.py` (441L) | Cost Estimator | No | Estimates, FER rates, margin analysis |
| `src/core/services/delo_agent.py` (542L) | Records Manager | No | Document registry, status tracking, deadlines |
| `src/core/services/procurement_logistics.py` (401L) | Procurement & Logistics | No | Tender analysis, supplier search, route planning |

### Knowledge layer

| File | Purpose |
|------|---------|
| `src/core/knowledge/knowledge_base.py` | pgvector RAG over DomainTraps |
| `src/core/knowledge/domain_classifier.py` | 3-tier domain/noise classifier |
| `src/core/knowledge/invalidation_engine.py` | Regulatory change detection, validity tracking |
| `src/core/knowledge/idprosto_loader.py` | id-prosto.ru knowledge base loader (569 doc mappings) |

### Generated document generators

- `src/core/services/is_generator/` — Executive Diagrams (IS): DXF parsing, PDF overlay, GOST stamps
- `src/core/services/ppr_generator/` — Project Execution Plans (PPR): DOCX/PDF export, TTK sections

### Configuration

- `config/id_requirements.yaml` (913L) — 20+ work types with normative requirements per 344/pr
- `config/telegram_channels.yaml` (525L) — 38 monitored Telegram channels for trap ingestion

## Data flow

1. **Ingestion**: TelegramScout → DomainClassifier → DomainTrap (pgvector)
2. **Invalidation**: DomainTrap → InvalidationEngine → affected knowledge entries
3. **Agent pipeline**: User request → PM(create_plan) → dispatch → agent execute → PM(evaluate) → next
4. **Output**: MCP tools → DOCX/PDF generation → Google Workspace export

## Testing

- **19 test files** (8,431 lines) in `tests/`
- Key test files: `test_smoke.py` (1153L), `test_is_generator.py` (1600L), `test_e2e_parallel_graph.py` (764L)
- Run: `pytest tests/`
- Gaps: knowledge layer (invalidation_engine, knowledge_base, domain_classifier) has no tests

## Conventions

- **Language**: Russian domain terminology in code, English in variable names
- **Python**: 3.11+ target, async where LLM is involved
- **Prompts**: Russian-language, inline in agent code
- **Schemas**: Pydantic v2 in `src/schemas/`
- **Database**: PostgreSQL with pgvector extension, port 5433
- **ORM**: SQLAlchemy, models in `src/db/models.py`
- **Logging**: Structured JSON via `src/core/observability.py`

## Key dependencies

- LangGraph (agent orchestration)
- pgvector (semantic search)
- MLX / Ollama (local LLM inference)
- python-docx (document generation)
- PyMuPDF (PDF parsing)
- fastmcp (MCP server)
- cachetools (in-process caching, replaced Redis in v12)
