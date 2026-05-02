#!/usr/bin/env python3
"""PTO Agent analysis of 61.17 documents using Gemma 4 31B via Ollama."""
import asyncio, json, sys, time
from pathlib import Path

async def main():
    from src.core.services.pto_agent import pto_agent
    from src.core.llm_engine import llm_engine

    # Load inventory data
    inv_path = Path("data/inventory_61.17.json")
    with open(inv_path) as f:
        inv = json.load(f)

    # Build document batch for PTO analysis
    # We use the actual OCR text from ingestion pipeline (stored in graph)
    from src.core.graph_service import graph_service

    # Collect documents with their text samples
    docs_for_pto = []
    for node, data in graph_service.graph.nodes(data=True):
        if data.get('type') == 'Document':
            text_sample = data.get('raw_text_sample', '')[:1500]
            fname = data.get('file_name', node)
            doc_type = data.get('doc_type', 'unknown')
            confidence = data.get('confidence', 0.0)
            docs_for_pto.append({
                "filename": fname,
                "content_preview": text_sample,
                "keyword_type": doc_type,
                "keyword_confidence": confidence,
            })

    print(f"Документов для PTO-анализа: {len(docs_for_pto)}")
    print()

    # ═══ 1. LLM-classify через Gemma 4 31B (первые 10 доков) ═══
    print("═══ PTO Agent: LLM-классификация 10 документов ═══")

    sample = docs_for_pto[:10]
    t0 = time.time()
    result = await pto_agent.analyze_document_batch(
        documents=sample,
        project_context="Аэропортовый комплекс «Левашово», I Этап, Сектор ГА, Служебное здание АС, шифр 61.17",
    )
    elapsed = time.time() - t0

    classified = result.get("classified", {})
    issues = result.get("issues", [])
    recommendations = result.get("recommendations", [])

    print(f"Время: {elapsed:.1f} сек")
    print(f"Классифицировано: {len(classified)}")
    print(f"Найдено проблем: {len(issues)}")
    print(f"Рекомендаций: {len(recommendations)}")
    print()

    # Show classification
    print("Результаты классификации (LLM vs Keyword):")
    for doc in sample:
        fname = doc["filename"]
        kw_type = doc.get("keyword_type", "?")
        llm_info = classified.get(fname, {})
        llm_type = llm_info.get("category_344", llm_info.get("doc_type", "?"))
        match = "✓" if kw_type in str(llm_type) or str(llm_type) in kw_type else "✗"
        print(f"  {match} {fname[:55]:<55s} keyword={kw_type:<15s} llm={str(llm_type)[:20]}")

    if issues:
        print(f"\nНайденные проблемы:")
        for iss in issues[:10]:
            sev = iss.get("severity", "?")
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(sev, "⚪")
            print(f"  {icon} [{sev}] {iss.get('doc', '')}: {iss.get('issue', '')[:100]}")

    if recommendations:
        print(f"\nРекомендации PTO:")
        for r in recommendations[:5]:
            print(f"  → {r[:120]}")

    # ═══ 2. Completeness report ═══
    print(f"\n\n═══ PTO Agent: отчёт о комплектности ═══")
    report = await pto_agent.generate_completeness_report(
        project_id=61,
        work_types=["architectural_solutions", "reinforced_concrete", "metal_structures"],
        available_docs=docs_for_pto,
    )
    print(f"Общая комплектность: {report.completeness_pct:.0f}%")
    print(f"Требуется позиций: {report.total_positions}")
    print(f"Закрыто позиций: {report.covered_positions}")
    print(f"Разрывов: {len(report.gaps)}")

    critical_gaps = report.critical_gaps
    high_gaps = [g for g in report.gaps if g.severity == "high"]
    print(f"  Критических: {len(critical_gaps)}")
    print(f"  Высоких: {len(high_gaps)}")

    if critical_gaps:
        print("\nКритические разрывы (отсутствуют полностью):")
        for g in critical_gaps[:10]:
            print(f"  🔴 {g.description}")

    if high_gaps:
        print("\nВысокие разрывы:")
        for g in high_gaps[:10]:
            print(f"  🟠 {g.description}")

    # ═══ 3. Сохраняем ═══
    output = {
        "llm_classification": {k: v for k, v in classified.items()},
        "issues": issues,
        "recommendations": recommendations,
        "completeness": {
            "coverage_pct": report.completeness_pct,
            "total_positions": report.total_positions,
            "covered_positions": report.covered_positions,
            "gaps": [{"category": g.category.value, "desc": g.description, "severity": g.severity} for g in report.gaps],
        },
    }
    out_path = Path("data/pto_analysis_61.17.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nПолный отчёт: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
