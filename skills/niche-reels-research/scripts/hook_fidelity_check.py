#!/usr/bin/env python3
"""hook_fidelity_check.py — проверяет, что телесуфлёр рилса СОХРАНИЛ хук оригинала.

Правило: телесуфлёр = адаптация чужого вирального текста,
а не новый текст. Хук (первые ~3 сек) и ядро остаются почти дословно, рерайт ~25%
(меняем только табу-слова/чужие ники/CTA/мат/кодворд). Хук, переписанный «по-своему»,
убивает виральную механику.

Метрика: доля КОНТЕНТНЫХ слов оригинального хука, которые сохранились в начале
телесуфлёра (retention). Высокая = хук сберегли, низкая = переписали заново.
Иностранный оригинал (не кириллица) дословно сравнить нельзя → помечаем «skip», не флагуем.
Слишком короткий хук (<3 контентных слов) тоже skip: смена кодворда уронила бы счёт ложно.

Выход: stdout-отчёт. exit 0 = все хуки сохранены / нечего проверять.
exit 10 = есть рилс(ы) с потерянным хуком (нужен повторный рерайт).
exit 2 = ошибка ввода (битый pack JSON / нет packs-dir / битый порог).

Usage: python3 hook_fidelity_check.py [--packs-dir DIR] [--reels-dir DIR] [--min FLOAT]
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_paths

# Per-client isolation via env NRR_CLIENT_DIR (lib_paths.py); unset = legacy paths.
# Matches digest_format_check.py / send_morning_digest.py so a bare (flag-less)
# run inspects THIS client's packs, not the shared legacy /tmp pool.
DEFAULT_PACKS = lib_paths.packs_dir()      # board #56: owner packs live in SKILL_DIR/packs, not pool/packs
DEFAULT_REELS = lib_paths.pool_dir()       # transcripts + work/ stay in the pool
CONFIG = lib_paths.config_file()

# минимальная доля сохранённых контентных слов хука; ниже = хук переписан
DEFAULT_MIN = 0.5
ORIG_HOOK_WORDS = 14      # «первые ~3 сек» оригинала
TELE_HEAD_WORDS = 32      # где ищем хук в телесуфлёре (начало, с запасом на лид-ин)
# КОНТРАКТ С send_morning_digest.py: строка пропуска по донору формата начинается ровно
# этим токеном. Отправитель ищет его подстрокой, чтобы напечатать причину в сводке клиента,
# поэтому менять токен можно только в обоих файлах сразу.
DONOR_SKIP_TOKEN = "[skip:format_donor]"
FORMAT_DONOR_MARK = "ДОНОР ФОРМАТА"

MIN_HOOK_WORDS = 3        # меньше контентных слов в хуке = не судим (skip), иначе ложные флаги

STOP = {
    "и", "в", "во", "не", "на", "я", "с", "со", "что", "как", "это", "к", "но",
    "они", "мы", "за", "из", "у", "то", "же", "бы", "ты", "вы", "он", "она",
    "оно", "для", "так", "вот", "уже", "или", "если", "когда", "чтобы", "только",
    "там", "тут", "его", "ее", "её", "их", "был", "была", "было", "быть", "есть",
    "the", "a", "an", "to", "of", "and", "is", "in", "it", "you", "your", "this",
}
WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
# Конец предложения: следующее слово с заглавной буквы именем собственным НЕ считается.
# Двоеточия и точки с запятой здесь НЕТ намеренно (Codex): «Обращение: Павлу Гетельману» —
# после двоеточия предложение не начинается, и Павлу обязан опознаться как имя.
# Хвост допускает открывающие кавычки, скобки и тире: «Павел сказал…» иначе читалось бы
# как начало предложения и имя утекало бы в знаменатель.
SENT_END_RE = re.compile(r"[.!?…\n]\s*[«\"'(\[\-–—]*\s*$")
MAX_PROPER_NOUNS = 2    # имя + фамилия; больше — эвристике не верим, судим полным набором
STEM_MIN = 5            # общий префикс короче — считаем слова разными
STEM_LEN_DELTA = 2      # род/число меняют хвост на 1-2 буквы, не больше
# Хвосты, которыми РАЗРЕШЕНО различаться формам одного слова. Свободное сравнение префиксов
# склеивало разные слова («сторонник» и «сторонний» — общие 8 букв, разница длины ноль),
# то есть открывало дорогу переписанному хуку. Список закрытый: чего тут нет, то разные слова.
#
# ХВОСТЫ РАЗБИТЫ НА ГРУППЫ, И ЭТО НЕ КОСМЕТИКА (<agent> , доска #1083). Плоский
# список, в который просто досыпали окончания лица, приравнял бы «заработала» и «заработает»:
# «ла» и «ет» лежали бы в одном множестве. Граница проходит по ТИПУ согласования, а не по
# длине хвоста, поэтому различаться слова имеют право только внутри ОДНОЙ группы:
#   NOMINAL_TAILS — род, число, падеж, возвратность (сюда же прошедшее время: «ла», «ли»);
#   PERSON_TAILS  — лицо и число глагола настоящего времени («экономим» и «экономлю»).
# Время утверждения остаётся различимым: «заработал» и «заработает» лежат в разных группах и
# по-прежнему разные слова. Канон требует согласовать форму под клиента, а не переписать
# обещание из прошлого в будущее.
NOMINAL_TAILS = {
    "", "а", "я", "о", "и", "ы", "у", "ю", "е", "й", "ь",
    "ая", "ое", "ые", "ый", "ой", "ей", "ом", "ым", "их", "ых", "ах", "ях",
    "ла", "ло", "ли", "лся", "лась", "лись", "ся", "сь", "ась", "ись",
    "ам", "ям", "ами", "ями", "ов", "ев", "ию", "ии", "ия", "ье", "ья",
}
# Лицо и число настоящего времени. Бесконечных «л»-форм здесь нет намеренно: прошедшее живёт
# в NOMINAL_TAILS, и общего хвоста у двух групп быть не должно там, где это стирает время.
# «лю» отдельным хвостом здесь НЕ стоит намеренно (Codex ): снимая его целиком, код
# делал бы чередование бл→б МОЛЧА, в обход слотов, и любое слово вида основа+л+ю читалось бы
# личной формой. Теперь «люблю» разбирается как «любл» + «ю» и сводится к «люб» ПОМЕЧЕННЫМ
# чередованием, то есть проходит те же проверки, что и все остальные.
PERSON_TAILS = {
    "у", "ю", "ешь", "ёшь", "ет", "ёт", "ем", "ём", "ете", "ёте", "ут", "ют",
    "ишь", "ит", "им", "ите", "ат", "ят",
}
STEM_TAIL_GROUPS = (NOMINAL_TAILS, PERSON_TAILS)
# Хвосты, которые бывают ТОЛЬКО прошедшим временем. Групп мало, потому что «ю» и «у» честно
# живут в обеих (энергию — экономлю), и одна эта неоднозначность стирала границу времени:
# «считала» и «считаю» различались хвостами «ла» и «ю», оба лежат в именной группе, и пара
# сходилась (находка Codex ; дыра жила в гейте и ДО правки, замер на доправочной
# копии это подтвердил). Правило простое: однозначно прошедший хвост с непрошедшим не сходится
# никогда, даже внутри одной группы.
PAST_ONLY_TAILS = {"л", "ла", "ло", "ли", "лся", "лась", "лись"}
# Русское спряжение меняет не только хвост: в 1-м лице единственного числа основа чередуется
# («платим» → «плачу», «видим» → «вижу», «любим» → «люблю»). Сравнение по общему префиксу такие
# пары не берёт вовсе, то есть «разрешено согласование по лицу» было бы правдой лишь для
# регулярной части спряжения (находка Codex ). Список ЗАКРЫТЫЙ: это школьные
# чередования перед личным окончанием, а не общее правило похожести.
# Каждая замена нужна КОНКРЕТНОМУ классу глаголов, где две ЛИЧНЫЕ формы несут разную основу:
#   ч→т, ж→д|з, ш→с, щ→ст|т, бл→б, пл→п, вл→в, мл→м, фл→ф — тип «платить» (плачу/платим,
#     вижу/видим, вожу/возим, ношу/носим, прощу/простим, люблю/любим);
#   ч→к, ж→г — тип «мочь» (пеку/печём, могу/можем, берегу/бережём).
# Замены ш→х здесь НЕТ намеренно (находка Codex ): ни один глагол её не требует, у
# «пахать» и «махать» все личные формы несут «ш», зато через неё «пашет» сходилось с «паху».
# Замена, не нужная ни одной паре личных форм, работает только на склейку.
STEM_ALTERNATIONS = {
    "ч": ("т", "к"), "ж": ("д", "з", "г"), "ш": ("с",), "щ": ("ст", "т"),
    "бл": ("б",), "пл": ("п",), "вл": ("в",), "мл": ("м",), "фл": ("ф",),
}
# ГРАНИЦА, КОТОРУЮ КОД НЕ ПЕРЕЙДЁТ БЕЗ СЛОВАРЯ. Личная форма опознаётся по написанию, а в
# русском форма существительного бывает неотличима от формы глагола: «соплю» (от «сопля») и
# «люблю» это одна и та же строковая фигура основа+л+ю, «лечу» это и «лететь», и «лечить».
# Запретить одно значит запретить другое, а другое канон требует. Направление ошибки здесь
# безопаснее обратного: засчитано слово, которое переписчику надо подобрать нарочно.
# Тип «мочь» опознаётся ещё и по основе: незачередованная сторона там кончается заднеязычным
# (могу, пеку, берегу). Без этого условия ветка принимала пары «глагол + существительное на -у»
# («лечит» и «лету»). Полностью класс не закрыт: «кричит» и «крику» сойдутся, потому что «крик»
# тоже кончается на «к». Цена принята — переписчику такое слово надо подобрать нарочно.
VELAR_END = ("г", "к", "х")
# Основа короче трёх букв не судится: цена названа, «пьём» и «пью» остаются разными
# словами. Практического веса у этого мало — форма короче четырёх букв и так не
# попадает в контентные слова, а расширение открыло бы склейки на голом корне.
PERSON_BASE_MIN = 3
# СЛОТЫ, в которых чередование законно. Русское чередование стоит не «где-нибудь», а в
# определённых лицах, и без этого условия правило склеивало разные глаголы: «лечим» и «летите»
# сходились через ч→т просто потому, что хвосты разные (находка Codex ).
#   тип «платить»: чередуется РОВНО 1 лицо ед. числа (плачу — платим, люблю — любим);
#   тип «мочь»:    чередуются ВСЕ формы, КРОМЕ 1 лица ед. и 3 лица мн. (можем — могу, но
#                  «могут» и «могу» несут ту же основу).
PERSON_1SG = {"у", "ю"}
PERSON_3PL = {"ут", "ют", "ат", "ят"}
# Прошедшее время короткой основы: «сняли» и «сняла» имеют общий префикс 3 буквы, то есть до
# STEM_MIN не дотягивают вовсе, а канон требует именно такой замены («мы сняли» → «я сняла»).
# Основа не короче трёх букв намеренно: с двумя склеились бы РАЗНЫЕ слова («село» и «сели»,
# «пила» и «пили»). Цена названа: «ушла» и «ушли» с двухбуквенной основой судятся как разные,
# это ложная потеря в счёте, а не пропущенный рерайт.
PAST_RE = re.compile(r"^(.{3,}?)л(?:а|о|и)?(?:ся|сь)?$")
PAREN_RE = re.compile(r"\([^)]*\)")        # вырезаем ремарки «(пауза 0.3 сек)»
CYR_RE = re.compile(r"[а-яё]", re.IGNORECASE)


def _s(v):
    """Безопасно привести значение поля к строке (поля могут прийти числом/списком/None)."""
    return v if isinstance(v, str) else ""


def _clip(text, limit=160):
    """Обрезать причину донора ПО ГРАНИЦЕ СЛОВА (наблюдение <agent> 17.08: жёсткая
    резка давала «…поэто» посреди слова).

    Обещаний ровно два, и второе сильнее первого: итог не длиннее limit ВСЕГДА (символ под
    многоточие зарезервирован), слово не рвётся, ЕСЛИ до лимита есть пробел. Одно слово
    длиннее лимита режется жёстко — размен осознанный: вернуть на него одно «…» значит
    выкинуть всю причину, а причина тут и есть смысл строки (находка ревью, отклонена).
    limit подразумевается >= 1; вызов один, значение константное."""
    s = _s(text).strip()
    if len(s) <= limit:
        return s
    head = s[:limit - 1]      # символ под многоточие, иначе итог был бы limit+1 (находка ревью)
    cut = head.rstrip()
    sp = cut.rfind(" ")
    if sp > 0:
        cut = cut[:sp]
    return cut.rstrip(" ,.;:—-–") + "…"


def content_words(text, limit=None):
    """Контентные слова: lowercase, длина>=4, не стоп-слово. limit — взять первые N токенов."""
    clean = PAREN_RE.sub(" ", _s(text))
    toks = WORD_RE.findall(clean.lower())
    if limit is not None:
        toks = toks[:limit]
    return [t for t in toks if len(t) >= 4 and t not in STOP]


def hook_window(text, n=ORIG_HOOK_WORDS):
    """Первые n токенов исходного текста как строка (для классификации языка хука)."""
    return " ".join(WORD_RE.findall(PAREN_RE.sub(" ", _s(text)))[:n])


def is_cyrillic(text):
    return len(CYR_RE.findall(_s(text))) >= 5  # несколько кириллических букв → русский


def shortcode_from_url(url):
    m = re.search(r"/reel/([A-Za-z0-9_-]+)", _s(url))
    return m.group(1) if m else None


def load_transcripts(reels_dir):
    """Собирает shortcode -> текст оригинала из _*transcript(s)*.json + work/<code>/transcript.txt."""
    by_code = {}
    files = sorted(set(reels_dir.glob("_*transcript*.json")))   # один паттерн покрывает оба
    for jf in files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = list(data.values())
        else:
            items = []
        for it in items:
            if not isinstance(it, dict):
                continue
            code = it.get("code") or shortcode_from_url(it.get("url", ""))
            text = _s(it.get("text") or it.get("transcript") or "")
            if code and text and len(text) > len(by_code.get(code, "")):
                by_code[code] = text
    work = reels_dir / "work"
    if work.is_dir():
        for tx in work.glob("*/transcript.txt"):
            code = tx.parent.name
            try:
                text = tx.read_text(encoding="utf-8")
            except OSError:
                continue
            if code and text and len(text) > len(by_code.get(code, "")):
                by_code[code] = text
    return by_code


def proper_nouns(text, limit=ORIG_HOOK_WORDS):
    """Имена собственные окна хука: слово с заглавной буквы НЕ в начале предложения.

    Замена чужого имени на имя клиента канон РАЗРЕШАЕТ, поэтому судить по ней нельзя
    (<agent> 31.07: «обращение к Павлу Гетельману» → «к Ирине Терещенко» отнимало
    два слова из семи ещё до всякого рерайта). Начало предложения исключаем: там заглавная
    стоит по правилам письма, а не потому что это имя.
    """
    clean = PAREN_RE.sub(" ", _s(text))
    out, seen = set(), 0
    for m in WORD_RE.finditer(clean):
        if seen >= limit:
            break
        seen += 1
        w = m.group(0)
        if not w[:1].isupper():
            continue
        if w.isupper():
            continue                      # ИИ, GPT, СССР — аббревиатура, а не имя (Codex)
        before = clean[:m.start()]
        if not before.strip() or SENT_END_RE.search(before):
            continue                      # первое слово предложения
        out.add(w.lower())
    return out


def _same_past_base(a, b):
    """Обе формы прошедшего времени от одной основы: «сняли» и «сняла», «снял» и «сняло».

    Отдельным правилом, потому что общего префикса у них меньше STEM_MIN, а требование канона
    ровно такое: ролик, снятый дуэтом, клиент в кадре один переносит от первого лица
    единственного числа. Границу времени это не трогает: «л» есть у обеих форм.
    """
    ma, mb = PAST_RE.match(a), PAST_RE.match(b)
    return bool(ma and mb) and ma.group(1) == mb.group(1)


def _person_forms(word):
    """Разборы слова как личной формы: список (хвост, основа, основа_разчередована).

    Пусто = слово на личную форму не похоже. Разчередованные основы отдаются отдельной
    пометкой, потому что верить им можно не всегда: см. _same_person_form.
    """
    out = []
    for tail in PERSON_TAILS:
        if not tail or not word.endswith(tail):
            continue
        base = word[: len(word) - len(tail)]
        if len(base) < PERSON_BASE_MIN:
            continue
        out.append((tail, base, False))
        for alt, plains in STEM_ALTERNATIONS.items():
            if not base.endswith(alt):
                continue
            for plain in plains:
                cand = base[: len(base) - len(alt)] + plain
                if len(cand) >= PERSON_BASE_MIN:
                    out.append((tail, cand, True))
    return out


def _same_person_form(a, b):
    """Обе формы личные и сводятся к одной основе: «плачу» и «платим», «пишем» и «пишу».

    РАЗЧЕРЕДОВАНИЕ ЗАСЧИТЫВАЕТСЯ ТОЛЬКО В СВОЁМ СЛОТЕ (PERSON_1SG / PERSON_3PL), и это не
    осторожность, а морфология: чередование создаётся сменой лица и стоит в определённых
    формах. Одного лишь «хвосты разные» мало — так «лечим» и «летите» сходились через ч→т,
    хотя это разные глаголы. Прошедшего времени здесь нет вовсе: его хвосты не личные, поэтому
    «заработал» и «заработаю» этой дорогой не сходятся и время остаётся различимым.
    """
    fb = _person_forms(b)
    for ta, ba, alt_a in _person_forms(a):
        for tb, bb, alt_b in fb:
            if ba != bb:
                continue
            if not alt_a and not alt_b:
                return True
            if alt_a and alt_b:
                continue          # разчередовать обе стороны значит гадать дважды
            alt_tail, plain_tail = (ta, tb) if alt_a else (tb, ta)
            if alt_tail in PERSON_1SG and plain_tail not in PERSON_1SG:
                return True       # тип «платить»: чередуется 1 лицо ед. числа
            if (alt_tail not in PERSON_1SG | PERSON_3PL
                    and plain_tail in PERSON_1SG | PERSON_3PL
                    and ba.endswith(VELAR_END)):
                return True       # тип «мочь»: чередуются все, кроме 1 ед. и 3 мн.
    return False


def _same_stem(a, b):
    """Одно слово в разных формах: род, число, падеж меняют хвост, а не основу.

    Клиент-женщина, переснимающая мужской ролик, обязана написать «ошибалась» вместо
    «ошибался» — это требование канона, а не рерайт. Точное сравнение засчитывало такую
    замену как потерю слова. Ограничение на разницу длин не даёт склеить разные слова
    с общим началом («энергия» и «энергетика» остаются разными).
    """
    if a == b:
        return True
    if abs(len(a) - len(b)) > STEM_LEN_DELTA:
        return False
    # Проверка длины стоит ВЫШЕ прошедшего времени намеренно: без неё «читал» и «читалась»
    # дали бы одну основу «чита», а это уже не согласование, а другое слово.
    if _same_past_base(a, b):
        return True
    if _same_person_form(a, b):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    if n < STEM_MIN or n < min(len(a), len(b)) - STEM_LEN_DELTA:
        return False
    # Мало иметь общее начало: РАЗЛИЧАТЬСЯ слова обязаны только допустимым окончанием, и
    # притом окончанием ОДНОГО типа согласования — иначе род приравнивается к времени.
    ta, tb = a[n:], b[n:]
    if (ta in PAST_ONLY_TAILS) != (tb in PAST_ONLY_TAILS):
        return False              # прошедшее против настоящего: время обязано быть различимым
    return any(ta in g and tb in g for g in STEM_TAIL_GROUPS)


def retention(orig_text, tele_text):
    """(score, orig_set, kept). score=None если хук оригинала пуст/короток.

    Из знаменателя выведены имена собственные: их замена разрешена каноном, и держать их
    в счёте значило бы требовать от телесуфлёра сохранить чужое имя. Сравнение форм идёт
    по основе, иначе смена рода читается как переписанный хук.
    """
    orig = content_words(orig_text, limit=ORIG_HOOK_WORDS)
    names = proper_nouns(orig_text, limit=ORIG_HOOK_WORDS)
    full = set(orig)
    if len(full) < MIN_HOOK_WORDS:
        return None, full, set()
    tele = content_words(tele_text, limit=TELE_HEAD_WORDS)
    # Сопоставление ОДИН К ОДНОМУ: один токен телесуфлёра закрывает одно слово оригинала
    # (Codex, ). Иначе окно с «энергия, энергии, энергию» целиком засчитывалось
    # одним словом в телесуфлёре, а остальной хук мог быть переписан — числитель завышался.
    # Порядок обхода отсортирован ради воспроизводимости счёта.
    used, kept_full = set(), set()
    for w in sorted(full):
        for i, t in enumerate(tele):
            if i in used or not _same_stem(w, t):
                continue
            used.add(i)
            kept_full.add(w)
            break

    # Вычет имён РАЗРЕШЁН ровно тогда, когда потери ТОЛЬКО на именах (Codex, ).
    # Прежний безусловный вычет открывал дыру: телесуфлёр переписывал заглавные слова вместе
    # с половиной хука, заглавные исчезали из знаменателя, и переписанное давало высокий счёт.
    # Теперь замена ника прощается только тому, кто остальной хук сохранил, — а именно это
    # канон и требует. Потерял что-то ещё — судим по ПОЛНОМУ набору, счёт строже.
    # MAX_PROPER_NOUNS отсекает заголовочное написание и названия методик: замер по 568 живым
    # транскриптам дал 487 без имён в окне, 73 с одним-двумя и лишь 8 с бо́льшим числом.
    lost = full - kept_full
    lost_names = lost & names
    lost_others = lost - names
    if lost_names and not lost_others and len(lost_names) <= MAX_PROPER_NOUNS:
        orig_set = full - lost_names
    else:
        orig_set = full
    # Вычет не имеет права опустошить окно: отказ судить это дыра, а не безопасное поведение.
    if len(orig_set) < MIN_HOOK_WORDS:
        orig_set = full
    kept = kept_full & orig_set
    return len(kept) / len(orig_set), orig_set, kept


def resolve_threshold(cli_min):
    """Порог из --min или config; nan/негатив/>1 = ошибка ввода (None)."""
    thr = cli_min
    if thr is None:
        try:
            thr = float(json.loads(CONFIG.read_text()).get("limits", {}).get("hook_retention_min", DEFAULT_MIN))
        except (OSError, ValueError, TypeError):
            thr = DEFAULT_MIN
    if not isinstance(thr, (int, float)) or not math.isfinite(thr) or not (0.0 <= thr <= 1.0):
        return None
    return float(thr)


DONOR_SEPARATORS = ":—-–"


def _donor_line(raw: str) -> tuple[bool, str]:
    """Разбор ОДНОЙ строки ТЗ монтажу: (это заявка донора, названная причина).

    ОДИН предикат на обе функции ниже: двумя копиями условия они разъезжаются молча, а цена
    расхождения тут — снятый блокирующий гейт. Форма строгая (находки ревью):
      * строка НАЧИНАЕТСЯ с пометки, иначе «НЕ ДОНОР ФОРМАТА» снимало бы гейт;
      * сразу после пометки идёт разделитель (: — -) или конец строки, иначе «ДОНОР
        ФОРМАТАМИ» и «ДОНОР ФОРМАТА НЕ СТАВИТЬ» проходили бы за объявление с причиной;
      * причина это текст ПОСЛЕ разделителя.
    """
    line = raw.strip().lstrip("-*•").strip()
    up = line.upper()
    if not up.startswith(FORMAT_DONOR_MARK):
        return False, ""
    rest = line[len(FORMAT_DONOR_MARK):]
    if not rest.strip():
        return True, ""                      # заявка есть, причина не названа
    # Двоеточие принимается вплотную («ДОНОР ФОРМАТА: причина»), тире и прочие разделители
    # только после пробела: иначе «ДОНОР ФОРМАТА-НЕТ» читалось бы как объявление с причиной
    # «НЕТ», а «ДОНОР ФОРМАТАМИ» — как объявление вовсе.
    if rest[0] != ":" and not rest[0].isspace():
        return False, ""
    rest = rest.strip()
    if rest[0] not in DONOR_SEPARATORS:
        return False, ""                     # «ДОНОР ФОРМАТА НЕ СТАВИТЬ» — не объявление
    return True, rest.lstrip(DONOR_SEPARATORS).strip()


def format_donor_reason(pack: dict, brief: str) -> str:
    """Донор ФОРМАТА: у оригинала берётся конструкция, а не речь. Возвращает ПРИЧИНУ,
    названную автором, либо "" — тогда пак донором не считается.

    Правило куратора (случай донора из бьюти-ниши): если речь
    оригинала это прайс-лист конкурента — чужие товарные марки, диагнозы, названия услуг —
    хук по нему НЕ переносится, потому что перенести его дословно значит произнести чужой
    бренд. Порог retention в таком случае недостижим арифметически (@pediatr_nauruzova
    DcHBjmsMRm-: максимум 0.42 при пороге 0.50, все семь потерянных слов — чужие марки и
    диагноз), и гейт блокировал бы карточку, которую правило разрешает.

    Признак ОБЪЯВЛЯЕТСЯ ЯВНО и требует причины, потому что это снятие блокирующего гейта:
      * ключ `"hook_source": "format_donor"` плюс непустой `hook_source_reason`;
      * либо строка editor_brief вида «ДОНОР ФОРМАТА: <причина>».
    """
    if str(pack.get("hook_source", "")).strip().lower() == "format_donor":
        reason = _s(pack.get("hook_source_reason"))
        if reason.strip():
            return reason.strip()
    for raw in str(brief or "").splitlines():
        declared, reason = _donor_line(raw)
        if declared and reason:
            return reason
    return ""


def declares_format_donor(pack: dict, brief: str) -> bool:
    """Пометка донора ЗАЯВЛЕНА (причина могла быть не названа).

    Отдельно от `format_donor_reason`, чтобы заявку без причины не пропускать молча: она
    означает намерение снять гейт, и ответ на неё должен объяснять, чего не хватает.
    """
    if str(pack.get("hook_source", "")).strip().lower() == "format_donor":
        return True
    return any(_donor_line(raw)[0] for raw in str(brief or "").splitlines())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs-dir", type=Path, default=DEFAULT_PACKS)
    ap.add_argument("--reels-dir", type=Path, default=DEFAULT_REELS)
    ap.add_argument("--min", type=float, default=None)
    args = ap.parse_args()

    thr = resolve_threshold(args.min)
    if thr is None:
        print(f"ERR: некорректный порог hook_retention_min (нужно 0..1)", file=sys.stderr)
        return 2

    if not args.packs_dir.is_dir():
        print(f"ERR: packs-dir не найден: {args.packs_dir}", file=sys.stderr)
        return 2
    transcripts = load_transcripts(args.reels_dir)

    flags, checked, skipped, bad_packs = [], 0, [], []
    donor_skipped: list = []          # печатаются своим токеном, их читает отправитель
    for pf in sorted(args.packs_dir.glob("pack_*.json")):
        try:
            p = json.loads(pf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad_packs.append(pf.name)
            continue
        if not isinstance(p, dict) or str(p.get("type", "")).lower() == "carousel":
            continue
        # Канон <agent>: REFERENCE-ONLY рилс (off-niche виралка для полноты картины) идёт БЕЗ
        # телесуфлёра — хук не переписан, его просто нет. digest_format_check.py уже знает это
        # исключение (check_reel через «РЕФЕРЕНС-ONLY» in brief.upper()); здесь оно тоже нужно,
        # иначе пустой телесуфлёр (ниже) даёт ложный [FLAG] «хук переписан», который попадает
        # прямо в текст сводки клиента (баг <agent> : 3 из 5 паков ложно сработали).
        brief = _s(p.get("editor_brief"))
        if "РЕФЕРЕНС-ONLY" in brief.upper() or "REFERENCE-ONLY" in brief.upper():
            author = _s(p.get("author_username")) or "?"
            skipped.append(f"{pf.name} (@{author}): REFERENCE-ONLY пак, телесуфлёр не требуется")
            continue
        # То же самое для ролика БЕЗ РЕЧИ. digest_format_check.py уже знает этот флаг как
        # канонное исключение ('no_speech': true либо «БЕЗ РЕЧИ» в brief), а здесь его не было.
        # У немого ролика транскрипт это галлюцинация ASR на музыке (замер 31.07: два прогона
        # одного файла дали два разных мусорных текста, второй просто строка песни), и сравнение
        # телесуфлёра с этим мусором давало ложный [FLAG] «переписан ХУК» с блокировкой выдачи.
        if p.get("no_speech") is True or "БЕЗ РЕЧИ" in brief.upper():
            author = _s(p.get("author_username")) or "?"
            skipped.append(f"{pf.name} (@{author}): ролик без речи, хук живёт в тексте на экране")
            continue
        # Донор ФОРМАТА (правило куратора 27.07): хук не переносится, телесуфлёр пишется с
        # нуля на позициях клиента. Сравнивать его с речью оригинала бессмысленно, а порог
        # там недостижим арифметически. Но ОДНО из проверок остаётся: телесуфлёр обязан
        # существовать — пометка означает «написан с нуля», а не «его нет».
        if declares_format_donor(p, brief):
            author = _s(p.get("author_username")) or "?"
            reason = format_donor_reason(p, brief)
            tele = _s(p.get("teleprompter"))
            if not reason:
                # Снятие блокирующего гейта без названной причины не принимается: пометка
                # обязана объяснять, ЧТО именно в речи оригинала не переносится.
                checked += 1
                line = (f"[FLAG] {pf.name} @{author} retention=0.00 (порог {thr:.2f}) | "
                        f"{FORMAT_DONOR_MARK} заявлен без причины — назови её в "
                        f"hook_source_reason или в строке ТЗ монтажу после пометки")
                flags.append(line)
                print(line)
                continue
            if not tele.strip():
                # Пометка означает «речь пишется своя», а не «телесуфлёра нет».
                checked += 1
                line = (f"[FLAG] {pf.name} @{author} retention=0.00 (порог {thr:.2f}) | "
                        f"{FORMAT_DONOR_MARK}, но телесуфлёра нет — пометка снимает перенос "
                        f"хука, а не сам телесуфлёр")
                flags.append(line)
                print(line)
                continue
            # Формулировка НЕЙТРАЛЬНАЯ: код проверил наличие телесуфлёра и причины, а не то,
            # что текст написан с нуля (находка ревью — не утверждать непроверенное).
            donor_skipped.append(
                f"{pf.name} (@{author}): {FORMAT_DONOR_MARK} — перенос хука не проверялся, "
                f"причина: {_clip(reason)}")
            continue
        code = shortcode_from_url(p.get("url") or p.get("link", "")) or _s(p.get("code"))
        author = _s(p.get("author_username")) or "?"
        orig = transcripts.get(code or "")
        if not orig:
            skipped.append(f"{pf.name} (@{author}, code={code or '?'}): нет оригинального транскрипта")
            continue
        if not is_cyrillic(hook_window(orig)):
            skipped.append(f"{pf.name} (@{author}): оригинал не на русском, дословно не проверяю")
            continue
        tele = _s(p.get("teleprompter"))
        if not tele.strip():
            # русский оригинал есть, телесуфлёра нет = хук не сохранён
            checked += 1
            line = f"[FLAG] {pf.name} @{author} retention=0.00 (порог {thr:.2f}) | телесуфлёр пуст"
            flags.append(line)
            print(line)
            continue
        score, orig_set, kept = retention(orig, tele)
        if score is None:
            skipped.append(f"{pf.name} (@{author}): хук оригинала слишком короткий, не сужу")
            continue
        checked += 1
        status = "OK" if score >= thr else "FLAG"
        line = f"[{status}] {pf.name} @{author} retention={score:.2f} (порог {thr:.2f})"
        if status == "FLAG":
            lost = sorted(orig_set - kept)
            line += f" | потеряны слова хука: {', '.join(lost[:8])}"
            flags.append(line)
        print(line)

    for s in donor_skipped:
        print(f"{DONOR_SKIP_TOKEN} {s}")
    for s in skipped:
        print(f"[skip] {s}")
    for b in bad_packs:
        print(f"[ERR] битый pack JSON: {b}", file=sys.stderr)
    print(f"\n=== проверено: {checked}, флагов: {len(flags)}, пропущено: {len(skipped)}, "
          f"доноров формата: {len(donor_skipped)}, битых паков: {len(bad_packs)} ===")

    if bad_packs:
        return 2  # вход сломан, доверять прогону нельзя
    if flags:
        print("\nХУК ПЕРЕПИСАН — верни хук оригинала почти дословно (рерайт ≤25%, меняй только табу/ники/кодворд):")
        for f in flags:
            print("  " + f)
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
