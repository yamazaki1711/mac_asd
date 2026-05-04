#!/bin/bash
# 5-кратный цикл расширенной проверки MAC_ASD
set -e

cd /home/oleg/MAC_ASD
LOGFILE="/tmp/asd_loop_5cycles.log"
echo "=== 5-CYCLE LOOP STARTED $(date) ===" | tee "$LOGFILE"

export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="sk-a2e155f831b94b58be01528af20afb30"
export ANTHROPIC_MODEL="deepseek-v4-pro[1m]"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro[1m]"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro[1m]"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_SUBAGENT_MODEL="deepseek-v4-flash"
export CLAUDE_CODE_EFFORT_LEVEL="max"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"

for i in $(seq 1 5); do
    echo "" | tee -a "$LOGFILE"
    echo "========================================" | tee -a "$LOGFILE"
    echo "=== CYCLE $i/5 STARTED $(date) ===" | tee -a "$LOGFILE"
    echo "========================================" | tee -a "$LOGFILE"

    claude --dangerously-skip-permissions --permission-mode bypassPermissions -p \
"ЦИКЛ $i/5 — РАСШИРЕННАЯ КОМПЛЕКСНАЯ ПРОВЕРКА MAC_ASD:

1. ПРОВЕРКА ВСЕХ ФАЙЛОВ ПРОЕКТА:
   - Все .py файлы в src/, tests/, mcp_servers/ — баги, дубликаты, мёртвый код
   - Старые/невостребованные файлы, не входящие в план (P0/P1/P2)
   - Дублирующиеся функции, классы, модули
   - Неиспользуемые импорты, закомментированный код
   - Фрагменты, оставшиеся от старых версий

2. ЦЕЛЕСООБРАЗНОСТЬ:
   - Каждый модуль: нужен ли? работает ли? документирован ли?
   - Что можно удалить без ущерба?
   - Что требует доработки?

3. НОРМАТИВНАЯ БАЗА:
   - Актуализировать data/regulations/ — новые ГОСТ, СП, ПП РФ
   - Проверить ссылки в IDRequirementsRegistry на актуальность
   - Обновить устаревшие нормативы

4. БАЗА ЗНАНИЙ ИЗ ТГ-КАНАЛОВ:
   - Запустить scripts/telegram_scout.py для сбора свежих постов
   - Извлечь строительную информацию из каналов config/telegram_channels.yaml
   - Обновить data/knowledge/ новыми данными

5. ИСПРАВЛЕНИЯ:
   - Все найденные баги — исправить
   - Дубликаты — удалить
   - Мёртвый код — вычистить
   - Тесты — дополнить при необходимости

6. ФИНАЛЬНАЯ ПРОВЕРКА:
   - Прогнать ВСЕ тесты: python -m pytest tests/ -v --tb=short
   - Убедиться: 0 failures, все тесты зелёные
   - Никаких регрессий

7. ДОКУМЕНТАЦИЯ:
   - Обновить STATUS.md с результатами цикла $i
   - Обновить README.md при необходимости

8. ПУШ НА GITHUB:
   - git add -A
   - git commit -m \"cycle-$i: расширенная проверка, вычистка, актуализация нормативки и ТГ-базы знаний\"
   - git push origin main

Результат каждого шага — в лог. Никаких сокращений, полный sweep." \
    < /dev/null 2>&1 | tee -a "$LOGFILE"

    echo "=== CYCLE $i/5 COMPLETED $(date) ===" | tee -a "$LOGFILE"
    sleep 2
done

echo "" | tee -a "$LOGFILE"
echo "=== ALL 5 CYCLES COMPLETED $(date) ===" | tee -a "$LOGFILE"
echo "=== Final git log: ===" | tee -a "$LOGFILE"
git log --oneline -10 | tee -a "$LOGFILE"
