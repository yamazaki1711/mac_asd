/**
 * MAC_ASD v12.0.0 — Анализ договора генподряда с БЛС (58 ловушек, 10 категорий)
 * Map-Reduce через z-ai-web-dev-sdk
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
  
  // Build BLC summary
  let blcSummary = `БАЗА ЛОВУШЕК СТОРОН (${traps.length} ловушек, 10 категорий):\n\n`;
  for (const t of traps) {
    blcSummary += `[${t.id}] ${t.title}\n`;
    blcSummary += `  Паттерн: ${t.pattern.trim().substring(0, 150)}\n`;
    blcSummary += `  Статья: ${t.law_reference}\n`;
    blcSummary += `  Рекомендация: ${t.recommendation.trim().substring(0, 150)}\n\n`;
  }
  
  // Load contract text
  const contractText = fs.readFileSync('/home/z/my-project/upload/contract_tsod_upper_fields.txt', 'utf-8');
  console.log(`Contract: ${contractText.length} chars`);
  console.log(`BLC: ${traps.length} traps loaded`);
  
  // Analyze first 30K chars (sections 1-4: subject, price, terms, liability)
  // This covers the core legal traps. Remaining is appendices/forms/detail specs.
  const maxChars = 30000;
  const analysisText = contractText.substring(0, maxChars);
  
  // Split into chunks for Map-Reduce
  const chunkSize = 6000;
  const chunkOverlap = 300;
  const chunks = [];
  let start = 0;
  while (start < analysisText.length) {
    let end = Math.min(start + chunkSize, analysisText.length);
    if (end < analysisText.length) {
      const boundary = analysisText.lastIndexOf('\n\n', end);
      if (boundary > start + chunkSize / 2) end = boundary + 2;
    }
    chunks.push(analysisText.substring(start, end));
    start = end < analysisText.length ? end - chunkOverlap : end;
  }
  
  console.log(`Chunks: ${chunks.length} (Map-Reduce mode, first ${Math.round(maxChars/1000)}K of ${Math.round(contractText.length/1000)}K chars)\n`);
  
  // MAP Stage
  console.log("=== MAP Stage ===\n");
  
  const MAP_PROMPT = `Ты — старший юрист-строительник, эксперт по защите подрядчиков и субподрядчиков.
Проанализируй фрагмент договора генподряда на предмет ловушек для ГЕНПОДРЯДЧИКА/СУБПОДРЯДЧИКА.

${blcSummary.substring(0, 4000)}

Для каждой найденной ловушки укажи:
1. ID ловушки из БЛС (если совпадает с известной) или "custom" если это новая ловушка
2. Конкретный пункт договора (цитата)
3. Степень опасности: critical / high / medium / low
4. Рекомендация для протокола разногласий
5. Статья закона

Ищи не только точные совпадения с БЛС, но и скрытые формы ловушек.
Особое внимание категориям: payment, penalty, acceptance, scope, warranty, subcontractor, liability, corporate_policy, termination, insurance.

ФРАГМЕНТ ДОГОВОРА:
{chunk_text}

Ответ ТОЛЬКО в JSON:
{
  "findings": [
    {
      "blc_trap_id": "payment_01",
      "blc_trap_title": "...",
      "contract_clause": "пункт X.X",
      "contract_quote": "цитата",
      "severity": "critical|high|medium|low",
      "analysis": "почему это ловушка",
      "recommendation": "что предложить в протокол",
      "law_reference": "статья ГК РФ"
    }
  ],
  "summary": "резюме рисков фрагмента"
}`;

  const mapResults = [];
  
  for (let i = 0; i < chunks.length; i++) {
    console.log(`  MAP chunk ${i + 1}/${chunks.length} (${chunks[i].length} chars)...`);
    
    const prompt = MAP_PROMPT.replace('{chunk_text}', chunks[i]);
    
    try {
      const completion = await zai.chat.completions.create({
        messages: [
          { role: 'system', content: 'Ты эксперт по строительному праву РФ. Отвечай ТОЛЬКО валидным JSON без markdown.' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.1,
      });
      
      const result = completion.choices[0].message.content;
      mapResults.push({ chunk: i + 1, result: result });
      console.log(`    → Got response (${result.length} chars)`);
    } catch (e) {
      console.log(`    → Error: ${e.message}`);
      mapResults.push({ chunk: i + 1, result: JSON.stringify({ findings: [], summary: `Error: ${e.message}` }) });
    }
    
    await new Promise(r => setTimeout(r, 1000));
  }
  
  // REDUCE Stage
  console.log(`\n=== REDUCE Stage ===\n`);
  
  let formattedMaps = "";
  for (const mr of mapResults) {
    formattedMaps += `\n### Фрагмент ${mr.chunk}\n${mr.result}\n`;
  }
  
  const REDUCE_PROMPT = `Ты — старший юрист-строительник. Агрегируй результаты анализа фрагментов договора генподряда.

РЕЗУЛЬТАТЫ АНАЛИЗА ФРАГМЕНТОВ:
${formattedMaps.substring(0, 15000)}

Сформируй итоговое заключение:
1. Все найденные ловушки (без дубликатов!)
2. Общий вердикт: approved / approved_with_comments / rejected / dangerous
3. Топ-5 самых опасных ловушек с конкретными пунктами
4. Рекомендации для протокола разногласий (приоритезированные)
5. Статьи закона для обоснования

Ответ ТОЛЬКО в JSON:
{
  "findings": [{"blc_trap_id":"...","blc_trap_title":"...","contract_clause":"...","contract_quote":"...","severity":"...","analysis":"...","recommendation":"...","law_reference":"..."}],
  "verdict": "dangerous|rejected|approved_with_comments|approved",
  "top_5_risks": [{"severity":"...","title":"...","clause":"..."}],
  "protocol_recommendations": [{"priority":1,"recommendation":"...","law_reference":"..."}],
  "summary": "..."
}`;

  let finalResult = "";
  try {
    const completion = await zai.chat.completions.create({
      messages: [
        { role: 'system', content: 'Ты эксперт по строительному праву РФ. Отвечай ТОЛЬКО валидным JSON без markdown.' },
        { role: 'user', content: REDUCE_PROMPT }
      ],
      temperature: 0.1,
    });
    finalResult = completion.choices[0].message.content;
  } catch (e) {
    finalResult = JSON.stringify({ error: e.message });
  }
  
  // Parse and display
  console.log("\n" + "=".repeat(70));
  console.log("РЕЗУЛЬТАТ АНАЛИЗА ДОГОВОРА ГЕНПОДРЯДА ЦОД ВЕРХНИЕ ПОЛЯ");
  console.log(`АСД v12.0.0 + БЛС (${traps.length} ловушек, 10 категорий) + Map-Reduce`);
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
    console.log(`\nРЕЗЮМЕ:\n${summary}`);
    
    if (top5 && top5.length > 0) {
      console.log(`\nТОП-5 ОПАСНЫХ РИСКОВ:`);
      top5.forEach((r, i) => {
        if (typeof r === 'object') {
          console.log(`  ${i + 1}. [${r.severity || '?'}] ${r.title || JSON.stringify(r).substring(0, 100)}`);
          if (r.clause) console.log(`     Пункт: ${r.clause}`);
        } else {
          console.log(`  ${i + 1}. ${String(r).substring(0, 120)}`);
        }
      });
    }
    
    console.log(`\nВСЕ НАЙДЕННЫЕ ЛОВУШКИ:`);
    findings.forEach((f, i) => {
      if (typeof f === 'object') {
        console.log(`  ${i + 1}. [${f.severity || '?'}] ${f.blc_trap_title || f.blc_trap_id || '—'}`);
        console.log(`     Пункт: ${f.contract_clause || '—'}`);
        console.log(`     БЛС: ${f.blc_trap_id || '—'}`);
        console.log(`     Цитата: ${(f.contract_quote || '').substring(0, 100)}`);
        console.log(`     Рекомендация: ${(f.recommendation || '').substring(0, 100)}`);
      }
    });
    
    if (recommendations && recommendations.length > 0) {
      console.log(`\nРЕКОМЕНДАЦИИ ДЛЯ ПРОТОКОЛА РАЗНОГЛАСИЙ:`);
      recommendations.forEach((r, i) => {
        if (typeof r === 'object') {
          console.log(`  ${i + 1}. [P${r.priority || '?'}] ${r.recommendation || JSON.stringify(r).substring(0, 120)}`);
          if (r.law_reference) console.log(`     Статья: ${r.law_reference}`);
        } else {
          console.log(`  ${i + 1}. ${String(r).substring(0, 150)}`);
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
      analysis_version: `v12.0.0 + БЛС(${traps.length})`,
      verdict: verdict,
      total_findings: findings.length,
      findings: findings,
      top_5_risks: top5,
      protocol_recommendations: recommendations,
      summary: summary,
    };
    
    fs.writeFileSync(
      '/home/z/my-project/upload/contract_analysis_v1122.json',
      JSON.stringify(output, null, 2),
      'utf-8'
    );
    console.log(`\nРезультат сохранён: /home/z/my-project/upload/contract_analysis_v1122.json`);
    
  } catch (e) {
    console.log(`\nParse error: ${e.message}`);
    console.log(`Raw result:\n${finalResult.substring(0, 3000)}`);
  }
}

main().catch(e => console.error(e));
