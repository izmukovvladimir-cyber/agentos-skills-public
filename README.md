# AgentOS Skills — Каталог скиллов для Claude Code

Production-tested скиллы от команды EdgeLab: кодинг, ресерч, контент, воронки и продажи, соцсети, AI-генерация. 73 штуки.

Этот репозиторий — публичная часть скиллов, которые мы используем каждый день в работе агентов Orgrimmar. Опубликовано как материал для учеников интенсива AgentOS.

---

## Что такое скилл

Скилл — это компактная инструкция для Claude Code, которая активируется по триггеру. Внутри: описание задачи, пошаговый процесс, шаблоны, иногда вспомогательные скрипты. Когда ты пишешь Claude «сделай мне рилс» — он находит скилл `reels` и работает по проверенной методике.

---

## Скиллы по ролям агентов

Если хочешь увидеть готовые наборы скиллов под конкретные роли (marketing, sales, coding, coordinator, monitoring, reviewer) — смотри папку [`agents/`](./agents/). Там для каждой роли README с описанием, списком скиллов и одной командой для установки.

## Категории

| Категория | Скиллов | Что внутри |
|-----------|---------|------------|
| **Ресерч** | 15 | perplexity, twitter, transcript, markdown-new, groq-voice, reel-radar, chat-archive, topic-monitor, yt-research, telegram-chip, hikerapi, niche-reels-research, reels-analyzer, youtube-analyzer, youtube-transcript |
| **Кодинг** | 11 | loop-coding, fast-loop-coding, mcp-builder, mcp-api-build, cross-review, dev-pipeline, server-doctor, agent-browser, senior-brainstorm, ui-ux-pro-max, gws |
| **Воронки и продажи** | 7 | funnel-skeleton, funnel-under-codeword, funnel-verify, funnel-teardown, chat-selling, product-unpack, polnaya-raspakovka-eksperta |
| **Тексты и контент** | 6 | content-engine, present, seo-tune, seo-blog, selling-article, selling-longread |
| **Соцсети** | 11 | instagram-superpower, carousel-instagram, reels, reels-analytics-for-brokers, youtube-producer, youtube-thumbnail, threads-content, twitter (создание), carousel-reskinner, reel-reskin, reels-montage |
| **AI-генерация** | 8 | codex-image, codex-image-gen, visual-gen-howto, synthetic-avatar, higgsfield-generate, higgsfield-soul-id, higgsfield-product-photoshoot, higgsfield-marketplace-cards |
| **Сайты и приложения** | 4 | workshop, agentos-content, client-knowledge-base-site, client-design-system |
| **Визуализация** | 3 | excalidraw, miro-board, datawrapper |
| **Системные и память** | 9 | learnings, memory-audit, agent-introspection, skill-creator, skill-finder, self-compiler, onboarding, gbrain-doctor, quick-reminders |

Рядом со скиллами лежит `_text-rules` — общий свод правил живого русского текста, на него ссылаются скиллы контента и воронок.

Продажный контур теперь открыт: воронка под кодовое слово со сборкой и проверкой, разбор чужой воронки, живая продажа в переписке, распаковка эксперта и сборка мини-продукта. Не опубликованы пока `landing-page-copywriter` и CRM-блок (`crm-workflow`, `qualification`, `objection-handling`, `follow-up`), см. раздел [«Готовятся к публикации»](./CATALOG.md#готовятся-к-публикации). Прогревы по Product Launch Formula лежат отдельным репозиторием: [izmukovvladimir-cyber/plf-walker](https://github.com/izmukovvladimir-cyber/plf-walker).

---

## Установка

Скиллы хранятся в `~/.claude/skills/`. Чтобы установить весь каталог:

```bash
cd ~/.claude/skills
git clone https://github.com/izmukovvladimir-cyber/agentos-skills-public.git agentos
```

Чтобы установить отдельный скилл — скопируй нужную папку из `agentos/skills/<name>/` в `~/.claude/skills/`.

```bash
cp -r ~/.claude/skills/agentos/skills/loop-coding ~/.claude/skills/
```

После установки запусти Claude Code и попробуй триггер на тестовой задаче.

---

## Структура репозитория

```
agentos-skills-public/
├── README.md            # этот файл
├── LICENSE              # MIT
├── CATALOG.md           # полное описание всех скиллов с триггерами
└── skills/
    ├── <skill-name>/
    │   ├── SKILL.md         # главная инструкция (с frontmatter)
    │   ├── references/      # доп. справочники (по необходимости)
    │   ├── scripts/         # вспомогательные скрипты (по необходимости)
    │   └── templates/       # шаблоны выходных файлов (по необходимости)
    └── ...
```

Каждый скилл — самодостаточная папка. Можно ставить по одному, можно весь набор.

---

## Дополнительные источники скиллов

| Источник | Описание | Установка |
|----------|----------|-----------|
| [izmukovvladimir-cyber/superpowers](https://github.com/izmukovvladimir-cyber/superpowers) | Универсальные мета-скиллы: TDD, debugging, plan-driven development | `git clone https://github.com/izmukovvladimir-cyber/superpowers.git ~/.claude/skills/superpowers` |
| [anthropics/skills](https://github.com/anthropics/skills) | Официальные скиллы Anthropic (skill-creator, cua-driver) | `git clone https://github.com/anthropics/skills.git ~/.claude/skills/anthropics` |
| [supabase/agent-skills](https://github.com/supabase/agent-skills) | Best practices для Supabase + Postgres | `git clone https://github.com/supabase/agent-skills.git ~/.claude/skills/supabase` |

---

## Создание своего скилла

Поставь официальный `skill-creator` от Anthropic — это скилл для создания скиллов. Он проведёт через интервью, поможет написать SKILL.md, протестировать и улучшить.

```bash
cd ~/.claude/skills
git clone https://github.com/anthropics/skills.git anthropics
```

После установки в Claude Code: «Создай скилл для <твоя задача>» — активируется skill-creator.

---

## Лицензия

MIT — используй, модифицируй, публикуй. Атрибуция к EdgeLab / AgentOS приветствуется.

---

## Контекст

Этот репозиторий — часть материалов интенсива «AgentOS» от EdgeLab.
