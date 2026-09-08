#!/usr/bin/env python3
"""v3: дизайн ПОД ОРИГИНАЛ каждого + ПОЛНЫЙ текст 1:1 (владелец голос 8963).
c01 theivansergeev = премиум-тетрадь/планер (кремовая бумага, пружина), 4 промпта ЦЕЛИКОМ.
c02 dashi_agent = тёмный продуктовый дек (Claude badge, оранж 'Результат:'), задачи ЦЕЛИКОМ.
gpt-image-2, текст запекает модель (проверено: 70 слов рендерит чисто). Лицо на обложках.

ДИЗАЙН-КАНОН РЕКРЕЙТА (HARD, владелец голос  — дефолты для любого рекрейта,
см. carousel-reskinner/SKILL.md «ДИЗАЙН РЕКРЕЙТА — ПРИНЦИП»):
  1. Исходник = основа, ЛЁГКОЕ улучшение — НЕ перебарщивать (уточнено владелец). Переносишь текст, держишься раскладки оригинала; палитру/фоны можно ЧУТЬ
     усилить до премиума, но результат остаётся узнаваемо на базе оригинала (не рестайл, не клон).
  2. НЕ вся серия в одном дизайне. Каждая карусель — свой премиум-стиль от своего
     оригинала; чередовать светлые/тёмные фоны + разные акценты (как c01 тетрадь vs c02 дек).
  3. Текст исходника НЕ сокращать — держать объём (усиливать смысл можно, резать ядро нельзя).
  4. Заголовки РОВНЫМИ строками 2-4 слова, ЛЕВОЕ выравнивание (HEADLINE_RULE ниже) —
     не по одному слову в строку, не всё по центру.
  5. Айдентика: чужие ники→@your_account, имена→владелец, лицо АВТОРА→лицо
     владелец (FACE_REFS ×3). Лицо знаменитости/героя новости (Дуров, Маск) ОСТАВЛЯТЬ как
     есть (цепляет взгляд) — на владельца НЕ менять.
  6. Только gpt-image, НИКОГДА PIL. Full-bleed 4:5 через edge-replicate (без полос),
     тире 0 + табу-маск в IG-капшене."""
import subprocess
from pathlib import Path

BIN = "~/bin/codex-image-gen.py"
BASE = Path("~/.claude/assets/daily_posts")
REFS = Path("~/.claude/assets/owner_face_refs")
FACE_REFS = ["32_fresh_selfie_open_white_smile_20260531.jpg", "00_studio_athletic_arms_crossed.jpg", "02_front.jpg"]

NOTE = ("Premium Instagram carousel slide, portrait 4:5. Design mirrors a beautiful premium bullet-journal "
        "notebook page: warm cream paper with faint ruled lines and a spiral binding along the top, a small "
        "tasteful hand-drawn doodle icon in a corner. Heading in elegant handwritten-style Cyrillic in warm "
        "orange ink; body text in a clean HIGHLY-LEGIBLE dark-charcoal font (not messy handwriting for the body), "
        "key phrases underlined in orange. Refined, premium, generous margins. All Cyrillic spelled EXACTLY as "
        "given, perfectly legible, no gibberish, no extra text, no logos, no watermark. ")
DARK = ("Premium Instagram carousel slide, portrait 4:5. Design mirrors a sleek modern AI product deck: "
        "deep charcoal near-black background, soft subtle glow, a small elegant rounded 'Claude' badge near the top, "
        "bold clean modern white Cyrillic, the label 'Результат:' in warm orange. Premium, minimal, clickable. "
        "All Cyrillic spelled EXACTLY as given, perfectly legible, no gibberish, no extra text, no logos, no watermark. ")
FACE = ("Use the EXACT face of the man from the reference images, identity 1:1, recognizable. Athletic build, "
        "trimmed beard, RESTRAINED natural closed-lip smile, not a wide grin. Photorealistic, premium cinematic portrait. ")
# Rule 4 : headings on EVEN lines of 2-4 words, left-aligned.
HEADLINE_RULE = ("Headline wrapped on EVEN lines of 2-4 words each, LEFT-aligned, "
                 "not one word per line, not all centered. ")


def gen(out_path: Path, prompt: str, refs=False):
    cmd = ["python3", BIN, "--quality", "high", "--aspect", "portrait", "--out", str(out_path), "--prompt", prompt]
    if refs:
        for r in FACE_REFS:
            cmd += ["--ref-image", str(REFS / r)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"{out_path.parent.parent.name}/{out_path.name}: {'OK' if out_path.exists() else 'FAIL '+r.stderr[-150:]}", flush=True)


def note_slide(heading, body):
    return (NOTE + f'Layout: heading at top "{heading}". {HEADLINE_RULE}Below a small orange label "Промпт:". '
            f'Then this exact paragraph as clean legible body text: «{body}» Every Cyrillic word spelled exactly.')


def dark_task(title, body):
    return (DARK + f'Layout: small orange "Claude" badge at top. Big bold white headline "{title}". {HEADLINE_RULE}'
            f'Below this exact text, white with the word "Результат:" in orange: «{body}» Every Cyrillic word spelled exactly.')


# ===== CAROUSEL 1: theivansergeev — премиум-тетрадь, полные промпты =====
C1 = BASE / "carousel_c01_system_20260618" / "gpt_v3"; C1.mkdir(parents=True, exist_ok=True)
gen(C1 / "00_cover.png", FACE +
    "Premium warm editorial portrait of the man at a stylish desk with a cream notebook and coffee, soft warm light, "
    "upscale cozy interior. Overlaid clean bold headline (cream/charcoal palette): top kicker \"AI ДЛЯ БЛОГА\", "
    "big headline \"СИСТЕМА КОНТЕНТА\", subline in orange \"за один запрос к нейросети\", small line \"4 промпта по шагам\". "
    "All Cyrillic spelled exactly, premium, magazine-quality.", refs=True)
gen(C1 / "01_slide.png", note_slide("1. Ниша и позиционирование",
    "Найди 5 ниш с высоким спросом, где можно быстро вырасти и начать зарабатывать на коротких видео. "
    "Бери ниши с высокой кликабельностью, хорошей досматриваемостью, контентом, который хочется смотреть запоем, "
    "и понятной монетизацией: реклама, партнёрки, спонсоры или цифровые продукты. Потом собери уникальную концепцию "
    "канала: стиль контента, подход к обложкам, формат видео, целевую аудиторию и темы, которые залетают."))
gen(C1 / "02_slide.png", note_slide("2. Архитектура контента (короткие ролики)",
    "Придумай 10 идей коротких видео с высоким удержанием для этого канала. В каждой идее: сильный хук в первые "
    "2 секунды, история, которая держит на интересе, и быстрая развязка. Затачивай под досматриваемость, репосты, "
    "комментарии и повторные просмотры. Каждый сценарий держи в пределах 20-30 секунд и под форматы коротких видео, "
    "которые залетают."))
gen(C1 / "03_slide.png", note_slide("3. Движок хуков и виральности",
    "Разбери самые залетевшие короткие видео в этой нише и вытащи самые рабочие приёмы хука в первые 3 секунды. "
    "Потом придумай 10 новых хуков: ещё сильнее цепляют любопытство, бьют по эмоциям и заточены остановить "
    "пролистывание. Опирайся на триггеры: деньги, статус, спор, страх, удивление и преображение."))
gen(C1 / "04_slide.png", note_slide("4. AI-система контента (+ автоматизация)",
    "Собери пошаговый план, как наладить стабильное AI-производство контента: генерация гиперреалистичных картинок, "
    "единый образ героя во всех роликах, превращение картинок в короткие видео, озвучка, субтитры и монтаж. "
    "Потом выстрой систему ежедневных публикаций, заточенную под рост и монетизацию."))
gen(C1 / "05_final.png", NOTE +
    'Layout: centered handwritten-style orange heading "Один запрос. Целая система." then clean charcoal line '
    '"Четыре промпта собирают контент под твою нишу." Below a call-to-action "Забери все промпты, напиши «статья» '
    'в комментариях" with «статья» underlined in orange. All Cyrillic spelled exactly.')

# ===== CAROUSEL 2: dashi_agent — тёмный дек, задачи целиком =====
C2 = BASE / "carousel_c02_claude_20260618" / "gpt_v3"; C2.mkdir(parents=True, exist_ok=True)
gen(C2 / "00_cover.png", FACE + DARK.replace("All Cyrillic", "Man positioned on the left, face clean at top. "
    "Big white headline on the dark right \"ЛАЙФХАКИ НЕДЕЛИ\", orange subline \"с нейросетью Claude\". A small Claude badge top. "
    "All Cyrillic"), refs=True)
gen(C2 / "01_slide.png", dark_task("ВИДЕОМОНТАЖ",
    "Смонтируй видео от и до строго в рамках моего фирменного стиля. Возьми отснятые исходники из папки, автоматически "
    "добавь субтитры, наложи графику и привычный монтаж. Результат: процесс, который раньше занимал часы, теперь длится считаные минуты."))
gen(C2 / "02_slide.png", dark_task("РОЛИКИ В СТИЛЕ UGC",
    "Сгенерируй 3 новых UGC-видео на основе аватаров наших клиентов. Результат: тестируешь разные гипотезы, заходы и боли "
    "аудитории за пару минут, без вложений в реальных инфлюенсеров."))
gen(C2 / "03_slide.png", dark_task("ДИЗАЙН ИНТЕРЬЕРА",
    "Сделай дизайн интерьера, исходя из предметов, которые лежат в этой папке. Результат: то, что требовало платной "
    "консультации дизайнера и часов поиска идей на Pinterest, автоматизировано с помощью Claude."))
gen(C2 / "04_slide.png", dark_task("ОРГАНИЗАТОР СЪЁМОК",
    "Распредели концепты роликов по локациям, составь чёткий список шотов и тайминг для съёмочного дня. Результат: "
    "планирование съёмок, которое отнимало целый день подготовки, готово за минуты."))
gen(C2 / "05_final.png", DARK +
    'Layout: centered bold white headline "Хочешь так же?" then orange line "Внедри нейросеть в процессы своего дела." '
    'Below a white call-to-action "Напиши «статья» в комментариях" with «статья» in orange. All Cyrillic spelled exactly.')

print("DONE_ALL")
