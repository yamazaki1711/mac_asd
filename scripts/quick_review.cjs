/**
 * MAC_ASD v12.0.0 — Quick Review анализа договора ЦОД
 * Один LLM-вызов с кратким содержанием + полная БЛС (58 ловушек)
 */

const ZAI = require('z-ai-web-dev-sdk').default;
const fs = require('fs');
const yaml = require('js-yaml');

async function main() {
  const zai = await ZAI.create();
  
  // Load BLC traps
  const trapsYaml = fs.readFileSync('/home/z/my-project/mac_asd/traps/default_traps.yaml', 'utf-8');
  const blcData = yaml.load(trapsYaml);
  const traps = blcData.traps;
  
  // Build BLC summary (compact — IDs + titles + law refs)
  let blcSummary = `БИБЛИОТЕКА ЛОВУШЕК СТОРОН (${traps.length} ловушек, 10 категорий):\n\n`;
  for (const t of traps) {
    blcSummary += `[${t.id}|${t.severity}] ${t.title}\n`;
    blcSummary += `  Закон: ${t.law_reference}\n`;
    blcSummary += `  Паттерн: ${t.pattern.trim().substring(0, 120)}\n`;
    blcSummary += `  Защита: ${t.recommendation.trim().substring(0, 120)}\n\n`;
  }
  
  // Load contract text — first 15K for Quick Review
  const contractText = fs.readFileSync('/home/z/my-project/upload/contract_tsod_upper_fields.txt', 'utf-8');
  const reviewText = contractText.substring(0, 15000);
  
  console.log(`Contract: ${contractText.length} chars (reviewing first 15K)`);
  console.log(`BLC: ${traps.length} traps loaded`);
  console.log(`Running Quick Review...\n`);
  
  const PROMPT = `Ты — старший юрист-строительник, эксперт по защите подрядчиков и субподрядчиков.
Проанализируй договор генподряда на предмет ловушек для ГЕНПОДРЯДЧИКА/СУБПОДРЯДЧИКА.

${blcSummary.substring(0, 5000)}

Для каждой найденной ловушки укажи:
1. ID ловушки из БЛС (если совпадает) или "custom" для новой
2. Конкретный пункт договора (цитата)
3. Степень опасности: critical / high / medium / low
4. Рекомендация для протокола разногласий
5. Статья закона

Ищи совпадения с БЛС и скрытые формы ловушек.
Особое внимание: payment, penalty, acceptance, scope, warranty, subcontractor, liability, corporate_policy, termination, insurance.

ДОГОВОР ГЕНПОДРЯДА:
${reviewText}

Ответ ТОЛЬКО в JSON (без markdown):
{
  "findings": [
    {
      "blc_trap_id": "payment_01",
      "blc_trap_title": "...",
      "contract_clause": "пункт X.X",
      "contract_quote": "цитата из договора",
      "severity": "critical|high|medium|low",
      "analysis": "почему это ловушка",
      "recommendation": "что предложить в протокол разногласий",
      "law_reference": "статья ГК РФ"
    }
  ],
  "verdict": "dangerous|rejected|approved_with_comments|approved",
  "top_5_risks": [{"severity":"...","title":"...","clause":"..."}],
  "protocol_recommendations": [{"priority":1,"recommendation":"...","law_reference":"..."}],
  "summary": "развёрнутое резюме анализа"
}`;

  let finalResult = "";
  try {
    const completion = await zai.chat.completions.create({
      messages: [
        { role: 'system', content: 'Ты эксперт по строительному праву РФ с 20-летним опытом. Отвечай ТОЛЬКО валидным JSON без markdown-обёрток.' },
        { role: 'user', content: PROMPT }
      ],
      temperature: 0.15,
    });
    finalResult = completion.choices[0].message.content;
  } catch (e) {
    console.error(`LLM Error: ${e.message}`);
    process.exit(1);
  }
  
  // Parse and display
  console.log("=".repeat(70));
  console.log("РЕЗУЛЬТАТ АНАЛИЗА ДОГОВОРА ГЕНПОДРЯДА ЦОД «ВЕРХНИЕ ПОЛЯ»");
  console.log(`АСД v12.0.0 + БЛС (${traps.length} ловушек, 10 категорий) + Quick Review`);
  console.log("=".repeat(70));
  
  try {
    let text = finalResult;
    if (text.includes("```json")) text = text.split("```json")[1].split("```")[0];
    else if (text.includes("```")) text = text.split("```")[1].split("```")[0];
    
    const parsed = JSON.parse(text.trim());
    
    const findings = parsed.findings || [];
    const verdict = parsed.verdict || "unknown";
    const top5 = parsed.top_5_risks || [];
    const recommendations = parsed.protocol_recommendations || [];
    const summary = parsed.summary || "";
    
    console.log(`\nВЕРДИКТ: ${verdict.toUpperCase()}`);
    console.log(`Найдено ловушек: ${findings.length}`);
    
    // Severity breakdown
    const bySev = { critical: 0, high: 0, medium: 0, low: 0 };
    findings.forEach(f => { if (typeof f === 'object' && f.severity) bySev[f.severity] = (bySev[f.severity]||0)+1; });
    console.log(`  Critical: ${bySev.critical}, High: ${bySev.high}, Medium: ${bySev.medium}, Low: ${bySev.low}`);
    
    console.log(`\nРЕЗЮМЕ:\n${summary}`);
    
    if (top5 && top5.length > 0) {
      console.log(`\nТОП-5 ОПАСНЫХ РИСКОВ:`);
      top5.forEach((r, i) => {
        if (typeof r === 'object') {
          console.log(`  ${i + 1}. [${r.severity || '?'}] ${r.title || JSON.stringify(r).substring(0, 100)}`);
          if (r.clause) console.log(`     Пункт: ${r.clause}`);
        }
      });
    }
    
    console.log(`\nВСЕ НАЙДЕННЫЕ ЛОВУШКИ:`);
    findings.forEach((f, i) => {
      if (typeof f === 'object') {
        console.log(`  ${i + 1}. [${f.severity || '?'}] ${f.blc_trap_title || f.blc_trap_id || '—'}`);
        console.log(`     Пункт: ${f.contract_clause || '—'}`);
        console.log(`     БЛС: ${f.blc_trap_id || '—'}`);
        console.log(`     Цитата: ${(f.contract_quote || '').substring(0, 120)}`);
        console.log(`     Анализ: ${(f.analysis || '').substring(0, 120)}`);
        console.log(`     Рекомендация: ${(f.recommendation || '').substring(0, 120)}`);
        console.log(`     Закон: ${f.law_reference || '—'}`);
      }
    });
    
    if (recommendations && recommendations.length > 0) {
      console.log(`\nРЕКОМЕНДАЦИИ ДЛЯ ПРОТОКОЛА РАЗНОГЛАСИЙ:`);
      recommendations.forEach((r, i) => {
        if (typeof r === 'object') {
          console.log(`  ${i + 1}. [P${r.priority || '?'}] ${r.recommendation || ''}`);
          if (r.law_reference) console.log(`     Статья: ${r.law_reference}`);
        }
      });
    }
    
    // Count by BLC category
    const cats = {};
    findings.forEach(f => {
      if (typeof f === 'object' && f.blc_trap_id) {
        const cat = f.blc_trap_id.replace(/_\d+$/, '');
        cats[cat] = (cats[cat] || 0) + 1;
      }
    });
    if (Object.keys(cats).length > 0) {
      console.log(`\nРАСПРЕДЕЛЕНИЕ ПО КАТЕГОРИЯМ БЛС:`);
      Object.entries(cats).sort((a, b) => b[1] - a[1]).forEach(([cat, count]) => {
        console.log(`  ${cat}: ${count}`);
      });
    }
    
    // Save structured output
    const output = {
      contract: "Договор генподряда ЦОД Верхние поля (без РС/ЗОС/РВ)",
      analysis_version: `v12.0.0 + БЛС(${traps.length}) Quick Review`,
      verdict: verdict,
      total_findings: findings.length,
      severity_breakdown: bySev,
      findings: findings,
      top_5_risks: top5,
      protocol_recommendations: recommendations,
      summary: summary,
    };
    
    const outPath = '/home/z/my-project/upload/contract_analysis_v1122_bls58.json';
    fs.writeFileSync(outPath, JSON.stringify(output, null, 2), 'utf-8');
    console.log(`\nРезультат сохранён: ${outPath}`);
    
  } catch (e) {
    console.log(`\nParse error: ${e.message}`);
    console.log(`Raw result (first 3000 chars):\n${finalResult.substring(0, 3000)}`);
    
    // Save raw result anyway
    fs.writeFileSync('/home/z/my-project/upload/contract_analysis_v1122_bls58_raw.txt', finalResult, 'utf-8');
  }
}

main().catch(e => console.error(e));
