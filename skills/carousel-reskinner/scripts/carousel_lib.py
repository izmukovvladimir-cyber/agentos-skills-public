"""carousel_lib.py — премиум-рендер слайдов: HTML + headless Chrome, 1080x1350.

ЗАЧЕМ. Три брака повторяются у всех, кто рекрейтит карусель, и все три лечатся
здесь, а не внимательностью:
  1. «Хук мелкий, спрятанный» — кегль подбирали на глаз под самый длинный вариант.
     Лечение: fit_css() + JS — заголовок САМ растягивается до максимума, который
     влезает. Короткий хук = огромный, длинный = чуть меньше, но всегда во всю ширину.
  2. «Текст обрезан / профиль подрезан снизу» — контент упирался в край.
     Лечение: SAFE (безопасное поле) + qc() ловит выход за границы ДО отдачи.
  3. «Как в Паинте» — PIL-рендер. Лечение: только Chrome (кернинг, антиалиасинг),
     фон = реальная картинка (codex-image-gen), текст оверлеем.

ПРАВИЛО, которое движок не заменит: если в оригинале ФОТО — генерь фото по смыслу
(codex-image-gen), не отдавай типографику на цветной плашке. Типографика-only вместо
визуальной карусели = брак. Свои пиксели, оригинал автора не патчить.

ИСПОЛЬЗОВАНИЕ:
    import carousel_lib as cl
    html = cl.page(inner, extra_css)
    cl.render(html, "out/01.png")        # рендер + АВТО-QC (упадёт на браке)
    cl.render(html, "out/01.png", qc=False)   # без проверки (не советую)

Заголовок во всю ширину:
    f'<div class="fit" data-fit-max="200" data-fit-min="60">{hook}</div>'
    + cl.fit_css()  в extra_css, и cl.FIT_JS в конце inner.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from html import unescape
from pathlib import Path

W, H = 1080, 1350          # Instagram 4:5, full-bleed, без полей по краям
SAFE = 60                  # безопасное поле: ближе к краю текст не ставим (обрежется в ленте)
MIN_BODY_FS = 30           # мельче — нечитаемо с телефона (оператор: «текст мелкий»)
MIN_HOOK_COVER = 0.55      # хук на обложке: минимум 55% ширины слайда, иначе «спрятан»

FONTS = Path("~.fonts")


def b64(path) -> str:
    p = Path(path)
    ext = p.suffix.lower().lstrip(".")
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return f"data:image/{mime};base64," + base64.b64encode(p.read_bytes()).decode()


# --- brand design system -------------------------------------------------
# Палитру и кегли писали руками в КАЖДОМ build.py, поэтому один бренд выглядел
# по-разному от сборки к сборке, а у клиентских агентов design.md был описанием
# для человека и в рендер не попадал вообще. Здесь он становится входом: токены
# лежат в fenced json внутри design.md, код читает их оттуда.
_BRAND_CACHE: dict[tuple[str, int], dict] = {}
# Тело ограды, а не «первая { … последняя }»: прежний шаблон искал закрывающую скобку
# СКВОЗЬ закрывающую ограду, поэтому незакрытый блок склеивался со следующим и настоящие
# токены исчезали из разбора вместе с ним. «```jsonc» здесь намеренно не подходит: этим
# языком помечают пример для человека.
_TOKENS_RE = re.compile(r"^[ ]{0,3}```json[ \t]*\n(.*?)^[ ]{0,3}```[ \t]*$", re.S | re.M)
_SURFACE_KEYS = ("bg", "text", "accent")   # без них brand_css() собрать нечего


def _find_design_md() -> Path:
    """design.md агента: явный путь из DESIGN_MD, иначе .claude/design.md вверх от cwd.

    Подъём ОСТАНАВЛИВАЕТСЯ на корне воркспейса (каталог, в котором есть .claude).
    Иначе сборка клиента молча подхватывала design.md соседнего или родительского
    каталога и рисовала слайды по чужой дизайн-системе: изоляция клиентов важнее
    удобства, поэтому здесь лучше внятный отказ, чем чужая палитра.
    """
    env = os.environ.get("DESIGN_MD")
    if env:
        return Path(env)
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        cand = d / ".claude" / "design.md"
        if cand.is_file():
            return cand
        if (d / "design.md").is_file():
            return d / "design.md"
        if (d / ".claude").is_dir():
            raise FileNotFoundError(
                f"design.md нет в воркспейсе {d}. Положи его в {d}/.claude/design.md "
                "или укажи путь в переменной DESIGN_MD. Выше корня воркспейса поиск "
                "не идёт: чужая дизайн-система клиенту не подходит."
            )
        if d in (Path("~/.claude/"), Path("~"), Path("/")):
            break
    raise FileNotFoundError(
        "design.md не найден. Положи его в <workspace>/.claude/design.md "
        "или укажи путь в переменной DESIGN_MD."
    )


def _tokens_block(p: Path) -> dict:
    """Блок токенов из design.md. Опознаётся по ключу surfaces, а не по порядку.

    Раньше брался ПЕРВЫЙ ```json в файле, поэтому пример для человека, стоящий выше
    настоящих токенов, молча становился палитрой бренда. Это ровно тот брак, который
    ловит гейт заглушек: слайд выходит почти правильным и уезжает в ленту. Двух
    блоков с surfaces тоже достаточно для отказа: угадывать, который настоящий,
    нельзя.
    """
    text = p.read_text(encoding="utf-8")
    found: list[tuple[int, dict]] = []
    broken: list[str] = []
    for m in _TOKENS_RE.finditer(text):
        body = m.group(1)
        line = text.count("\n", 0, m.start(1)) + 1
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            if "surfaces" in body:
                # Битый блок, похожий на токены, — отказ даже если рядом есть целый.
                # Иначе угадываем, какой из двух настоящий, а цена ошибки это чужая палитра.
                raise ValueError(
                    f"{p}: блок токенов на строке {line} не разбирается ({e.msg}). "
                    "Почините json либо уберите ключ surfaces из примера для человека."
                ) from None
            broken.append(f"строка {line}: {e.msg}")
            continue
        # Кандидат опознаётся по НАЛИЧИЮ ключа surfaces, а не по его содержимому: иначе
        # блок с пустым surfaces выпадал из подсчёта, и стоящий рядом пример становился
        # единственным «кандидатом», то есть палитрой бренда, молча.
        if isinstance(data, dict) and "surfaces" in data:
            found.append((line, data))
    if not found:
        why = "; ".join(broken) if broken else "ни в одном блоке нет ключа surfaces"
        raise ValueError(f"{p}: блок токенов не найден ({why})")
    if len(found) > 1:
        lines = ", ".join(str(line) for line, _ in found)
        raise ValueError(
            f"{p}: блоков с surfaces несколько (строки {lines}). Оставьте один настоящий; "
            "пример для человека помечайте другим языком блока (```jsonc) или уберите "
            "из него ключ surfaces."
        )
    line, data = found[0]
    if not isinstance(data["surfaces"], dict) or not data["surfaces"]:
        raise ValueError(
            f"{p}: блок токенов на строке {line}: surfaces пустой или не объект. "
            "Опишите хотя бы одну поверхность бренда."
        )
    return data


def _require_filled(node, p: Path, where: str) -> None:
    """Отказ, если в токенах остались заглушки шаблона. Область — только `node`."""
    left = _unfilled(node)
    if not left:
        return
    raise ValueError(
        f"{p}: в {where} остались заглушки шаблона: {', '.join(left[:6])}"
        f"{' и ещё ' + str(len(left) - 6) if len(left) > 6 else ''}. "
        "Снимите значения с материалов клиента (его сайт, принятые посты, "
        "утверждённая колода) и подставьте сюда."
    )


def brand(path=None) -> dict:
    """Токены дизайн-системы из design.md. Кидает, если файла или блока json нет.

    Молчаливый фолбэк на дефолтную палитру здесь запрещён специально: он и был
    причиной разнобоя, потому что сборка «как-то» проходила и брак ехал дальше.

    Гейт заглушек разделён по области: общие блоки (кегли, холст, подвал) судятся
    здесь, а поверхность — в surface(). Прежде он судил ВЕСЬ файл, и заглушка в
    поверхности, которую сборка не использует, валила сборку целиком; такой отказ
    учит снимать гейт вместо того, чтобы заполнять токены.
    """
    p = Path(path) if path else _find_design_md()
    try:
        rp = p.resolve(strict=True)            # относительный путь двух клиентов совпал бы
        st = rp.stat()
    except OSError as e:
        raise FileNotFoundError(f"{p}: не читается ({e.strerror})") from None
    # Ключ несёт устройство, инод, время и размер: имя файла у клиентов одинаковое
    # («design.md»), и кеш по одному имени отдал бы палитру соседа.
    key = (str(rp), st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size)
    if key not in _BRAND_CACHE:
        data = _tokens_block(rp)
        _require_filled({k: v for k, v in data.items() if k != "surfaces"},
                        rp, "общих токенах")
        _BRAND_CACHE[key] = data
    # Отдаём КОПИЮ: иначе сборка, поправившая у себя один цвет, меняет общий кеш,
    # и следующий вызов получает подменённую палитру молча — без единой заглушки.
    return copy.deepcopy(_BRAND_CACHE[key])


def _unfilled(node, trail: str = "") -> list[str]:
    """Пути до незаполненных заглушек шаблона (значения с маркером TODO_).

    Гейт стоит здесь, а не в ревью глазами, потому что заглушка это невалидный
    цвет: браузер её молча игнорирует, слайд выходит почти правильным, и уезжает
    в прод. Пусть лучше падает сборка.
    """
    out: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += _unfilled(v, f"{trail}.{k}" if trail else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _unfilled(v, f"{trail}[{i}]")
    elif isinstance(node, str) and "TODO_" in node:
        out.append(trail or node)
    return out


def surface(name: str, path=None) -> dict:
    """Одна поверхность бренда (например lime или editorial_dark).

    Здесь же гейт заглушек по ЭТОЙ поверхности: судим то, чем сборка рисует.
    """
    p = Path(path) if path else _find_design_md()
    b = brand(p)
    try:
        s = b["surfaces"][name]
    except KeyError:
        have = ", ".join(sorted(b.get("surfaces", {})))
        raise KeyError(f"поверхности «{name}» нет в design.md; есть: {have}") from None
    if not isinstance(s, dict):
        raise ValueError(
            f"{p}: поверхность «{name}» должна быть объектом, а не {type(s).__name__}."
        )
    _require_filled(s, p, f"поверхности «{name}»")
    # Судим не наличие ключа, а ЗНАЧЕНИЕ: пустая строка, null и число проходили насквозь
    # и доезжали до css видом `background:;color:None`, то есть заглушка без слова TODO_.
    miss = [k for k in _SURFACE_KEYS if not (isinstance(s.get(k), str) and s[k].strip())]
    if miss:
        raise ValueError(
            f"{p}: у поверхности «{name}» не заполнены обязательные ключи: {', '.join(miss)}. "
            f"Нужны непустые строки: {', '.join(_SURFACE_KEYS)}."
        )
    return s


def _hex_to_rgb(v: str) -> tuple:
    """#rgb / #rrggbb / #rrggbbaa -> кортеж, который понимает PIL."""
    s = v.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"«{v}» не похоже на цвет; нужен #rgb, #rrggbb или #rrggbbaa")
    return tuple(int(s[i:i + 2], 16) for i in range(0, len(s), 2))


def palette(name: str, path=None) -> dict:
    """Цвета поверхности в форме, пригодной для PIL: {'bg': {'hex':..., 'rgb':(...)}}.

    Зачем отдельно от brand_css(): тот отдаёт CSS, а тринадцать живых сборщиков рисуют
    через PIL и CSS применить не могут. Без этой функции они хардкодят цвет, то есть
    механизм остаётся без вызывающих ровно там, где сборок больше всего (замер 02.08:
    через carousel_lib идёт 1 сборщик из 21).

    Гейты не дублируются: разбор, кеш и проверка заглушек живут в brand()/surface(),
    здесь только перевод формы. Значит палитра для PIL не может разойтись с палитрой
    для HTML, они читают один объект.
    """
    s = surface(name, path)
    out = {}
    for k, v in s.items():
        if isinstance(v, str) and v.startswith("#"):
            out[k] = {"hex": v, "rgb": _hex_to_rgb(v)}
    if not out:
        raise ValueError(f"у поверхности «{name}» нет ни одного цвета вида #rrggbb")
    return out


def brand_css(name: str, path=None) -> str:
    """CSS-переменные и базовые классы поверхности. Ставить первым в extra_css."""
    p = Path(path) if path else _find_design_md()
    b = brand(p)
    s = surface(name, p)
    t = b.get("type_scale", {})
    # Цвета верхнего уровня токенов (например accent_ink, «текст поверх акцента») тоже
    # уезжают в :root. Без этого их нельзя было взять из design.md штатным путём:
    # surface() отдаёт только ключи ВНУТРИ поверхности, а роль лежит уровнем выше,
    # поэтому сборка вынужденно хардкодила близкий цвет и палитра тихо расходилась
    # с источником (живой случай 26.08: #14180f вместо accent_ink #1a1a1a).
    # Ключи поверхности идут ПОСЛЕ и перекрывают одноимённые общие: поверхность конкретнее.
    top = {k: v for k, v in b.items() if isinstance(v, str) and v.startswith("#")}
    var = "".join(f"--{k.replace('_', '-')}:{v};"
                  for k, v in {**top, **{k: v for k, v in s.items()
                                         if isinstance(v, str) and v.startswith("#")}}.items())
    return f"""
:root{{{var}}}
.slide{{background:{s['bg']};color:{s['text']};font-family:'{s.get('body_font', 'OnestV')}',sans-serif;}}
.h2{{font-family:'{s.get('headline_font', 'Onest')}',serif;font-weight:900;
  font-size:{t.get('h2', 62)}px;line-height:1.06;letter-spacing:-0.005em;}}
.lab{{font-family:'{s.get('label_font', 'InterB')}',sans-serif;font-size:{t.get('label', 31)}px;
  letter-spacing:{t.get('label_ls', '0.14em')};text-transform:uppercase;color:{s['accent']};}}
.body{{font-size:{t.get('body', 37)}px;line-height:{t.get('body_lh', 1.34)};
  color:{s.get('text_body', s['text'])};}}
.body b{{color:{s['text']};font-weight:800;}}
.rule{{height:2px;background:{s['accent']};opacity:.55;}}
.foot{{position:absolute;left:{SAFE}px;right:{SAFE}px;bottom:{b.get('canvas', {}).get('footer_bottom', 64)}px;
  display:flex;justify-content:space-between;font-size:{t.get('footer', 30)}px;
  color:{s.get('text_footer', s.get('text_muted', '#888'))};}}
"""


def fit_css() -> str:
    """Стили для авто-подгоняемого заголовка. Ставить в extra_css."""
    return (".fit{font-family:'Onest',sans-serif;font-weight:900;line-height:0.95;"
            "text-wrap:balance;word-break:normal;}")


# Автоподгон + замеры. Кладётся ОДИН раз в конец inner (перед </body>).
FIT_JS = """
<script>
(function(){
  // 1. Каждый .fit растягиваем до максимального кегля, который влезает по ширине И высоте.
  document.querySelectorAll('.fit').forEach(function(e){
    var max=parseFloat(e.dataset.fitMax||'200'), min=parseFloat(e.dataset.fitMin||'40');
    var box=e.parentElement;
    // Мерить ТОЛЬКО по box.clientWidth недостаточно: если box сам fit-content
    // (резиновый, растёт вместе с e), сравнение всегда проходит на максимальном
    // кегле, и текст может вылезти за холст, а QC ниже это не всегда ловит
    // (нашли на карусели <client-agent> 2026-07-29, обложка обрезалась при чистом QC).
    // Поэтому дополнительно жёстко ограничиваем реальными границами холста.
    for(var fs=max; fs>=min; fs-=2){
      e.style.fontSize=fs+'px';
      var r=e.getBoundingClientRect();
      var fitsBox = e.scrollWidth<=box.clientWidth && e.scrollHeight<=box.clientHeight;
      var fitsCanvas = r.left>=%SAFE% && r.right<=%W%-%SAFE% && r.top>=%SAFE% && r.bottom<=%H%-%SAFE%;
      if(fitsBox && fitsCanvas) break;
    }
  });
  // 2. Замеры для QC: overflow, мелкий текст, выход за safe-zone.
  var SAFE=%SAFE%, MINFS=%MINFS%, res={overflow:[],tiny:[],outside:[],hook:null};
  var SKIP={STYLE:1,SCRIPT:1,TITLE:1,META:1,HEAD:1,HTML:1,BODY:1,LINK:1};
  document.querySelectorAll('*').forEach(function(e){
    if(SKIP[e.tagName]) return;
    if(!e.textContent.trim()||e.children.length) return;   // только листья с текстом
    var st=getComputedStyle(e);
    if(st.display==='none'||st.visibility==='hidden'||parseFloat(st.opacity)===0) return;
    var fs=parseFloat(st.fontSize);
    var r=e.getBoundingClientRect();
    var tag=(e.className||e.tagName).toString().slice(0,30);
    // Обрезка: только там, где контент реально режется (overflow скрыт) либо
    // текст шире своего контейнера. Голый scrollWidth у flex-детей врёт.
    var clipped=(st.overflow==='hidden'||st.overflow==='clip');
    var par=e.parentElement;
    if(clipped && (e.scrollWidth>e.clientWidth+1||e.scrollHeight>e.clientHeight+1))
      res.overflow.push(tag);
    else if(par && r.width>par.clientWidth+1) res.overflow.push(tag+'>parent');
    if(fs<MINFS) res.tiny.push(tag+':'+Math.round(fs)+'px');
    if(r.left<SAFE-1||r.top<SAFE-1||r.right>%W%-SAFE+1||r.bottom>%H%-SAFE+1)
      res.outside.push(tag+':'+[r.left,r.top,r.right,r.bottom].map(Math.round).join(','));
  });
  var h=document.querySelector('.fit');
  if(h) res.hook=Math.round(h.getBoundingClientRect().width/%W%*100)/100;
  document.body.dataset.qc=JSON.stringify(res);
})();
</script>
"""


def _js() -> str:
    return (FIT_JS.replace("%SAFE%", str(SAFE)).replace("%MINFS%", str(MIN_BODY_FS))
            .replace("%W%", str(W)).replace("%H%", str(H)))


def page(inner: str, extra_css: str = "") -> str:
    """Каркас слайда. FIT_JS подмешивается сам — вручную не вставлять."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
@font-face{{font-family:'Onest';src:url('file://{FONTS}/Onest-Black.ttf');font-weight:900;}}
@font-face{{font-family:'OnestV';src:url('file://{FONTS}/Onest.ttf');font-weight:100 800;}}
@font-face{{font-family:'Play';src:url('file://{FONTS}/PlayfairDisplay.ttf');font-weight:400 900;}}
@font-face{{font-family:'Inter';src:url('file://{FONTS}/Inter-Regular.ttf');font-weight:400;}}
@font-face{{font-family:'Inter';src:url('file://{FONTS}/Inter-Bold.ttf');font-weight:700;}}
@font-face{{font-family:'InterB';src:url('file://{FONTS}/Inter-Black.ttf');font-weight:900;}}
@font-face{{font-family:'Mont';src:url('file://{FONTS}/Montserrat-Black.ttf');font-weight:900;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;}}
.slide{{position:relative;width:{W}px;height:{H}px;overflow:hidden;}}
{extra_css}
</style></head><body>{inner}{_js()}</body></html>"""


def _measure(htmlpath: str) -> dict:
    r = subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
                        f"--window-size={W},{H}", "--dump-dom", f"file://{htmlpath}"],
                       capture_output=True, text=True, timeout=90)
    m = re.search(r'data-qc="([^"]*)"', r.stdout)
    return json.loads(unescape(m.group(1))) if m else {}


def render(html: str, out_png: str, qc: bool = True, cover: bool = False) -> dict:
    """Рендер слайда. qc=True → падает на браке (мелкий текст / обрезка / выход за поле).

    cover=True — слайд обложки: дополнительно требует, чтобы хук занимал
    >= MIN_HOOK_COVER ширины (иначе он «спрятан», оператор бракует).
    """
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir="/tmp") as f:
        f.write(html)
        htmlpath = f.name
    try:
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
                            "--hide-scrollbars", "--force-device-scale-factor=1",
                            f"--screenshot={out_png}", f"--window-size={W},{H}",
                            "--default-background-color=00000000", f"file://{htmlpath}"],
                           capture_output=True, text=True, timeout=90)
        if not Path(out_png).exists():
            sys.stderr.write(r.stderr[-1500:] + "\n")
            raise SystemExit(f"render failed: {out_png}")
        info = _measure(htmlpath) if qc else {}
    finally:
        os.unlink(htmlpath)

    if qc and info:
        bad = []
        if info.get("overflow"):
            bad.append(f"ОБРЕЗАН текст: {', '.join(info['overflow'][:4])}")
        if info.get("tiny"):
            bad.append(f"МЕЛКИЙ текст (<{MIN_BODY_FS}px): {', '.join(info['tiny'][:4])}")
        if info.get("outside"):
            bad.append(f"ВЫХОД за safe-zone {SAFE}px (обрежется/подрежется): "
                       f"{', '.join(info['outside'][:4])}")
        if cover and (info.get("hook") or 0) < MIN_HOOK_COVER:
            bad.append(f"ХУК МЕЛКИЙ: {int((info.get('hook') or 0)*100)}% ширины, "
                       f"нужно >={int(MIN_HOOK_COVER*100)}% — подними data-fit-max "
                       f"или укороти текст хука")
        if bad:
            raise SystemExit(f"QC FAILED {out_png}:\n  " + "\n  ".join(bad))
    print(f"rendered {out_png}" + (f"  hook={info['hook']}" if info.get("hook") else ""))
    return info
