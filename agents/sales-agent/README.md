# Sales Agent

Делает квалификацию лидов, ресерч клиентов, подготовку follow-up'ов, разбор возражений.

## Что умеет

- Ресерч клиента по соцсетям и сайту перед звонком
- Анализ чатов и переписок
- Извлечение фактов из транскриптов созвонов
- Подготовка персонализированных follow-up'ов

> **Важно:** скиллы для CRM-флоу (`crm-workflow`, `qualification`, `objection-handling`, `follow-up`) пока в работе — войдут в публичную часть отдельным релизом. Сейчас sales-роль работает на универсальных research-скиллах.

## Скиллы

### Ресерч лида

- [`perplexity-research`](../../skills/perplexity-research/) — глубокий web research по компании и человеку
- [`twitter`](../../skills/twitter/) — чтение X/Twitter профиля клиента
- [`markdown-new`](../../skills/markdown-new/) — выжимка текста с сайта компании
- [`transcript`](../../skills/transcript/) — транскрипция созвона + извлечение ключевых поинтов

### Разбор переписок

- [`chat-archive`](../../skills/chat-archive/) — анализ архивов Telegram-чатов

### Подготовка материалов

- [`present`](../../skills/present/) — персональные HTML-предложения / коммерческие
- [`content-engine`](../../skills/content-engine/) — генерация follow-up writeups с TOV

## Типовой sales-флоу

1. Лид пришёл → `perplexity-research` по компании (отрасль, размер, последние новости)
2. + `twitter` по руководителю → понимаем тон коммуникации
3. + `markdown-new` по их сайту → находим продукт/цены/позиционирование
4. Созвон → `transcript` записи → извлекаем pain points + bant-сигналы
5. Follow-up → `content-engine` пишет персональное письмо
6. Если нужна презентация → `present` собирает HTML по нашему фирстилю

### Воронки и продажи (новое)

- [`funnel-skeleton`](../../skills/funnel-skeleton/) — скелет воронки под кодовое слово
- [`funnel-under-codeword`](../../skills/funnel-under-codeword/) — полная сборка воронки вместе с лид-магнитом
- [`funnel-verify`](../../skills/funnel-verify/) — проверка живой воронки одной командой
- [`funnel-teardown`](../../skills/funnel-teardown/) — разбор чужой воронки с таймингом касаний
- [`chat-selling`](../../skills/chat-selling/) — продажа в переписке после выдачи магнита
- [`product-unpack`](../../skills/product-unpack/) — сборка мини-продукта от ниши до упаковки
- [`polnaya-raspakovka-eksperta`](../../skills/polnaya-raspakovka-eksperta/) — полная распаковка эксперта за семь шагов

## Установка

```bash
cd ~/.claude/skills
git clone https://github.com/izmukovvladimir-cyber/agentos-skills-public.git agentos
for skill in perplexity-research twitter markdown-new transcript chat-archive present content-engine \
  funnel-skeleton funnel-under-codeword funnel-verify funnel-teardown chat-selling product-unpack polnaya-raspakovka-eksperta; do
  cp -r agentos/skills/$skill ./
done
```
