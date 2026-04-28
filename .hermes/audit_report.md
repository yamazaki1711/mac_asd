# ASD v12.0 — Project Audit Report

**Date:** 28 апреля 2026
**Scope:** 120 .py files, 29 959 LOC, 25 commits
**Branch:** main (yamazaki1711/mac_asd)

---

## PASS 1: Syntax

| Check | Result |
|-------|:---:|
| 120 .py files parsed with ast | ✅ All pass |
| Syntax errors | 0 |

## PASS 2: Stale References

| Pattern | Result |
|---------|:---:|
| Yandex refs (non-id_prosto) | 0 ✅ |
| yandex_map_url | 0 ✅ |
| PLACEHOLDER | 0 ✅ |
| TODO/FIXME/HACK | 9 (expected pre-production) |

**TODO items (non-blocking):**
- `event_manager.py:37` — audit log to PostgreSQL
- `integrations/google.py:21-39` — Gmail/Drive/Sheets/Docs API stubs
- `backends/mlx_backend.py:61,115,151` — MLX implementation pending Mac Studio

## PASS 3: Package Structure

| Check | Result |
|-------|:---:|
| Missing __init__.py | 1 — `src/scripts/` → **FIXED** |
| Empty __init__.py | 1 — `src/scripts/__init__.py` (created) |

## PASS 4: AgentState Field Analysis

| Field | Files referencing | Status |
|-------|:---:|--------|
| `revision_history` | 0 (dead) | ⚠️ Defined + populated, never read |
| `rollback_point` | 0 (dead) | ⚠️ Set in fail_step, never triggers rollback |
| `ram_snapshot` | 1 (set only) | ⚠️ Set in pm_planning, never checked in dispatch |
| `ram_status` | 1 (set only) | ⚠️ Same as above |
| `event_type` | 1 | Low usage |
| `compliance_delta` | 2 | OK |
| `completed_task_ids` | 2 | OK |
| All other 28 fields | 3+ | ✅ Active |

**Root cause:** `revision_history` and `rollback_point` were designed in AgentState v2.0 schema but the rollback mechanism was never wired into the PM-driven workflow. The helpers (`start_step`, `complete_step`, `fail_step`, `add_revision`) work, the audit_trail is maintained, but `revision_history` + `rollback_point` are never read by any decision logic.

**Verdict:** Low risk for August — audit_trail covers observability. Rollback is a future feature.

## PASS 5: Workflow Integration

| Check | Result |
|-------|:---:|
| AGENT_NODE_MAP completeness | 6/6 agents mapped ✅ |
| Workflow conditional edges | All agents routed ✅ |
| nodes_v2 ↔ nodes compatibility | 0 function conflicts ✅ |
| PM dispatch → agent execution | Working ✅ |
| RAM Manager integration | Planning + execution checkpoints ✅ |

**Note:** `ram_manager.can_accept_task()` is called in `agent_executor_node` but `ram_status` is not checked in `pm_dispatch_router`. If RAM becomes critical during dispatch, the current agent finishes but the next one gets rejected — this is acceptable (graceful degradation).

## PASS 6: Test Coverage

| Module | Test file | Tests |
|--------|-----------|:---:|
| PM Agent + WorkPlan | test_orchestration.py | 31 |
| RAM Manager | test_orchestration.py | (included) |
| Parser + RAG Pipeline | test_rag_pipeline.py | 27 |
| Legal Documents | test_legal_documents.py | 16 |
| PPR Generator | test_ppr_generator.py | 20 |
| IS Generator | test_is_generator.py | 71 |
| Smoke tests | test_smoke.py | 21 |
| Legal Service | test_legal_service.py | (exists) |
| Google Integration | test_google_integration.py | (exists) |
| **Total** | — | **~200+** |

## PASS 7: Known Gaps (non-blocking for August)

1. **Rollback mechanism** — `revision_history` + `rollback_point` fields exist but no rollback logic
2. **Procurement + Logistics agents** — stub implementations, need full LLM integration
3. **MLX backend** — stubs pending Mac Studio deployment
4. **Google Workspace integration** — stubs (Gmail/Drive/Sheets/Docs API not called)
5. **EventManager** — audit log to PostgreSQL not wired
6. **DB session DI** — sessions created ad-hoc, not injected (deferred from earlier audit)
7. **Shared Gemma 4 31B mutex** — 5 agents share one model, no concurrency guard

## Summary

| Severity | Count | Action |
|----------|:---:|--------|
| 🔴 Critical | 0 | — |
| 🟡 Minor (fixed) | 1 | `src/scripts/__init__.py` created |
| ⚪ Known gaps | 7 | Documented, non-blocking |
| ✅ Verified | 120 files | Syntax, imports, structure OK |

**Project health: GOOD.** 120 files, 29 959 LOC, 25 commits, ~200 tests.
Ready for Packages 5-7 (PTO, Smeta+Delo, Procurement+Logistics) and August deployment.
