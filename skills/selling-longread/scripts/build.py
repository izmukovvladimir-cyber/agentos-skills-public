#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a selling longread into a single static page.

    python3 src/build.py            # -> out/index.html

Design: premium editorial dark, black + gold, serif display, generous air.
Assets live in out/img/ (prepared separately from client materials).
"""
from __future__ import annotations

import pathlib
import re
import sys

from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import content as C  # noqa: E402

OUT = HERE.parent / "out"

GRAIN = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E"
    "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E"
    "%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.35'/%3E%3C/svg%3E"
)

CSS = """
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  margin:0;background:#070708;color:#ece5da;
  font-family:'Manrope',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:19px;font-weight:300;line-height:1.75;letter-spacing:.005em;
  overflow-x:hidden;
}
body::before{
  content:'';position:fixed;inset:0;z-index:2;pointer-events:none;
  background-image:url("%GRAIN%");opacity:.045;mix-blend-mode:overlay;
}
/* Во встроенном браузере Telegram фиксированный слой с блендом пересчитывается на каждом
   кадре прокрутки, и страница начинает дёргаться. На сенсорных экранах зерно кладём
   обычным слоем поверх страницы: выглядит так же, а прокрутка остаётся гладкой */
@media (hover:none){
  body::before{position:absolute;top:0;left:0;width:100%;height:100%;
    mix-blend-mode:normal;opacity:.03}
  /* размытие ореола под портретом телефон пересчитывает на каждом кадре: градиент
     сам по себе мягкий, разницы в картинке нет, а прокрутка перестаёт спотыкаться */
  .hero-figure::after{filter:none}
}
/* height:auto обязателен рядом с атрибутами width/height в разметке, иначе картинка
   тянется до своей настоящей высоты и ломает пропорции */
img{max-width:100%;display:block;height:auto}
a{color:inherit}
/* заголовки разбиваются на ровные строки, в абзацах последняя строка не остаётся
   из одного слова. Браузеры без поддержки просто переносят как раньше */
h1,h2,.pull,.price-hero,.story-sum,.qmark{text-wrap:balance}
h3{text-wrap:pretty}
p,li,.result,.story-niche{text-wrap:pretty}

:root{
  --gold:#c9a24a; --gold-lt:#f2dca6; --cream:#ece5da; --mute:#8b8377;
  --ink:#0c0c0e; --line:rgba(201,162,74,.22);
  --wrap:1180px; --read:720px;
  /* Заголовки набраны шрифтом с сайта Кати: в её теме он спрятан под именем Showshrift,
     весом 700 там стоит Anticva. Файл лежит у нас, чтобы страница не зависела от Тильды. */
  --serif:'Anticva','Playfair Display',Georgia,serif;
}
@font-face{
  font-family:'Anticva';
  src:url('fonts/anticva-regular.woff') format('woff');
  font-weight:400;font-style:normal;font-display:swap;
}

.wrap{width:min(100% - 44px,var(--wrap));margin-inline:auto}
.read{width:min(100% - 44px,var(--read));margin-inline:auto}

h1,h2,h3,.disp{
  font-family:var(--serif);font-weight:400;
  letter-spacing:-.015em;line-height:1.08;margin:0;
}
h2{font-size:clamp(30px,4.4vw,52px);line-height:1.17}
h3{font-size:clamp(21px,2.2vw,26px);line-height:1.25}
p{margin:0 0 1.35em}
strong,b{font-weight:600}

.kicker{
  font-size:12px;font-weight:600;letter-spacing:.28em;text-transform:uppercase;
  color:var(--gold);margin:0 0 22px
}
.eyebrow{
  font-size:11.5px;font-weight:600;letter-spacing:.3em;text-transform:uppercase;
  color:var(--mute);margin:0 0 18px
}
.lead{font-size:clamp(20px,2vw,23px);line-height:1.65;color:#f4efe7}
.mute{color:var(--mute)}

/* ---------- sections ---------- */
section{position:relative;padding:clamp(76px,10vw,140px) 0}
.sec-line{height:1px;border:0;margin:0;
  background:linear-gradient(90deg,transparent,rgba(201,162,74,.34),transparent)}
.panel{background:linear-gradient(180deg,#0b0b0d,#0e0e11)}

/* ---------- hero ---------- */
.hero{
  min-height:100svh;display:flex;align-items:center;padding:96px 0 72px;
  background:
    radial-gradient(120% 90% at 78% 26%,rgba(201,162,74,.20),transparent 58%),
    radial-gradient(90% 70% at 8% 88%,rgba(201,162,74,.07),transparent 60%),
    #070708;
  overflow:hidden;
}
.hero-grid{display:grid;grid-template-columns:1.08fr .92fr;gap:clamp(24px,5vw,80px);align-items:center}
/* кегль подобран под ДОСЛОВНУЮ шапку клиента (она длиннее слогана), чтобы первый экран
   вмещал заголовок, лид и кнопку целиком */
.hero h1{font-size:clamp(30px,3.9vw,52px);line-height:1.12;margin:0 0 22px}
/* у ёлочек в Anticva широкие боковые поля, из-за них слово в кавычках
   разъезжается и точка после кавычки отлетает. Поджимаем сами кавычки */
.q{margin:0 -.16em;letter-spacing:0}
.q2{margin-right:-.3em}
.hero .lead{max-width:34ch}
.hero-note{font-size:14px;color:var(--mute);letter-spacing:.02em;margin-top:18px}
.hero-figure{position:relative}
.hero-figure::after{
  content:'';position:absolute;inset:-14% -10% -6% -10%;z-index:-1;
  background:radial-gradient(60% 55% at 50% 42%,rgba(201,162,74,.28),transparent 70%);
  filter:blur(18px);
}
.hero-figure img{width:100%;border-radius:2px;position:relative;z-index:1}
.hero-figure::before{
  content:'';position:absolute;inset:22px -22px -22px 22px;border:1px solid rgba(201,162,74,.42);
  border-radius:2px;z-index:0
}
.hero-figure figcaption{
  position:absolute;left:0;right:0;bottom:-1px;height:34%;z-index:2;pointer-events:none;
  background:linear-gradient(180deg,transparent,rgba(7,7,8,.85))
}
.scroll-hint{
  margin-top:56px;font-size:11.5px;letter-spacing:.28em;text-transform:uppercase;color:var(--mute);
  display:flex;align-items:center;gap:12px
}
.scroll-hint span{display:block;width:56px;height:1px;background:linear-gradient(90deg,var(--gold),transparent)}

/* ---------- buttons ---------- */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:12px;
  padding:19px 44px;border-radius:999px;text-decoration:none;
  font-family:'Manrope',sans-serif;font-size:14.5px;font-weight:600;
  letter-spacing:.16em;text-transform:uppercase;color:#141008;
  background:linear-gradient(100deg,#b8903c,#f2dca6 46%,#c9a24a);
  box-shadow:0 18px 44px -20px rgba(201,162,74,.85);
  position:relative;overflow:hidden;transition:transform .35s cubic-bezier(.2,.7,.3,1),box-shadow .35s
}
.btn::after{
  content:'';position:absolute;top:0;bottom:0;left:-70%;width:45%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.55),transparent);
  transform:skewX(-18deg);transition:left .6s ease
}
.btn:hover{transform:translateY(-2px);box-shadow:0 24px 56px -20px rgba(201,162,74,.95)}
.btn:hover::after{left:130%}
.btn-ghost{
  background:none;color:var(--gold-lt);border:1px solid var(--line);box-shadow:none
}
.btn-ghost:hover{border-color:rgba(242,220,166,.6);box-shadow:none}
.cta-row{display:flex;flex-wrap:wrap;gap:18px;align-items:center;margin-top:34px}

/* ---------- longread ---------- */
.read p{color:#ded7cb}
.read .first::first-letter{
  font-family:var(--serif);float:left;font-size:76px;line-height:.82;
  padding:6px 14px 0 0;color:var(--gold)
}
.qmark{
  font-family:var(--serif);font-size:clamp(34px,5vw,58px);color:var(--gold-lt);
  text-align:center;margin:14px 0 0
}
.pull{
  margin:clamp(44px,6vw,72px) auto;text-align:center;max-width:24ch;
  font-family:var(--serif);font-size:clamp(28px,3.6vw,44px);line-height:1.2;color:#f7f1e6
}
.pull::before,.pull::after{
  content:'';display:block;width:64px;height:1px;margin:26px auto;
  background:linear-gradient(90deg,transparent,var(--gold),transparent)
}
.loops{list-style:none;margin:0 0 2em;padding:0;counter-reset:l}
.loops li{
  position:relative;padding:20px 0 20px 62px;border-bottom:1px solid rgba(255,255,255,.06);
  color:#ded7cb
}
.loops li::before{
  counter-increment:l;content:counter(l,decimal-leading-zero);
  position:absolute;left:0;top:22px;font-family:var(--serif);font-size:20px;color:var(--gold)
}

/* ---------- author ---------- */
.author-grid{display:grid;grid-template-columns:.85fr 1.15fr;gap:clamp(28px,5vw,72px);align-items:center}
.author-figure{position:relative}
.author-figure img{width:100%;border-radius:3px;filter:saturate(.96)}
.author-figure::before{
  content:'';position:absolute;inset:16px -16px -16px 16px;border:1px solid var(--line);z-index:-1
}

/* ---------- levels / steps ---------- */
.levels{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin:44px 0 0}
.card{
  padding:34px 30px;background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.012));
  border:1px solid rgba(255,255,255,.07);border-radius:3px;position:relative;overflow:hidden
}
.card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(201,162,74,.55),transparent)
}
.card h3{margin-bottom:12px}
.card p{margin:0;font-size:17px;color:#cdc6bb}

.steps{margin:54px 0 0;border-top:1px solid rgba(255,255,255,.08)}
.step{
  display:grid;grid-template-columns:96px 1fr;gap:clamp(16px,3vw,40px);
  padding:34px 0;border-bottom:1px solid rgba(255,255,255,.08);align-items:start
}
.step-n{font-family:var(--serif);font-size:44px;color:var(--gold);line-height:1}
.step h3{margin-bottom:10px}
.step p{margin:0;color:#cdc6bb;font-size:17.5px}

/* ---------- results / cases ---------- */
.results{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin:0 0 20px}
.result{
  padding:30px 26px;border-left:1px solid var(--line);font-size:17.5px;color:#ded7cb;line-height:1.65
}
.cases{
  display:grid;grid-template-columns:repeat(5,1fr);gap:clamp(18px,3vw,38px) 18px;margin:56px 0 0
}
.case{text-align:center}
.case img{
  width:clamp(76px,9vw,124px);aspect-ratio:1;border-radius:50%;object-fit:cover;margin:0 auto 14px;
  border:1px solid rgba(201,162,74,.35);
  box-shadow:0 0 0 6px rgba(201,162,74,.05);transition:transform .4s,box-shadow .4s
}
.case:hover img{transform:translateY(-4px);box-shadow:0 0 0 8px rgba(201,162,74,.12)}
.case b{display:block;font-size:13px;font-weight:500;color:var(--mute);letter-spacing:.02em}
.case span{display:block;margin-top:5px;font-size:15.5px;font-weight:600;color:var(--gold-lt)}

/* ---------- slider ---------- */
.rail{
  display:flex;gap:20px;overflow-x:auto;scroll-snap-type:x mandatory;
  padding:8px 0 26px;margin-top:44px;scrollbar-width:thin;scrollbar-color:rgba(201,162,74,.4) transparent
}
.rail::-webkit-scrollbar{height:3px}
.rail::-webkit-scrollbar-thumb{background:rgba(201,162,74,.4)}
.rail img{
  flex:0 0 min(78vw,470px);scroll-snap-align:center;border-radius:3px;
  border:1px solid rgba(255,255,255,.07)
}
.rail.reviews img{flex:0 0 min(64vw,318px);border-radius:14px}

/* ---------- story cards ---------- */
.story{
  flex:0 0 min(84vw,430px);scroll-snap-align:center;display:flex;flex-direction:column;
  padding:32px 30px 34px;border:1px solid rgba(255,255,255,.08);border-radius:4px;
  background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.012));
  position:relative;overflow:hidden
}
.story::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(201,162,74,.5),transparent)
}
.story-top{display:flex;gap:16px;align-items:center;margin-bottom:22px}
.story-top img{
  width:66px;height:66px;border-radius:50%;object-fit:cover;flex:0 0 auto;
  border:1px solid rgba(201,162,74,.4)
}
.story-top h3{font-size:21px;margin-bottom:4px}
.story-niche{margin:0;font-size:13px;color:var(--mute);line-height:1.4}
.story-handle{margin:3px 0 0;font-size:12.5px;color:rgba(242,220,166,.75);letter-spacing:.04em}
.story-sum{
  font-family:var(--serif);font-size:30px;color:var(--gold-lt);margin:0 0 24px;
  letter-spacing:.01em
}
.story-lbl{
  margin:0 0 10px;font-size:11px;font-weight:600;letter-spacing:.26em;text-transform:uppercase;
  color:var(--mute)
}
.story-lbl.gold{color:var(--gold)}
.story-col+.story-col{margin-top:22px;padding-top:22px;border-top:1px solid rgba(255,255,255,.07)}
.story ul{list-style:none;margin:0;padding:0}
.story li{
  position:relative;padding:0 0 9px 24px;font-size:15.5px;line-height:1.55;color:#cdc6bb
}
.story li::before{position:absolute;left:0;top:0;font-size:13px}
.story-a li::before{content:'✕';color:#8a4a44}
.story-b li::before{content:'✓';color:#7fa06a}
.rail-hint{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--mute);margin-top:6px}
/* кнопка раскрытия историй живёт только на телефоне */
.more-btn{
  display:none;width:100%;margin-top:20px;padding:16px 22px;font:inherit;font-size:13px;
  font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--gold-lt);
  background:rgba(201,162,74,.06);border:1px solid rgba(201,162,74,.32);border-radius:3px;
  cursor:pointer;transition:background .3s ease,border-color .3s ease
}
.more-btn:hover{background:rgba(201,162,74,.12);border-color:rgba(201,162,74,.55)}

/* ---------- fears ---------- */
.fears{display:grid;gap:18px;margin-top:46px}
.fear{
  padding:32px 34px;border:1px solid rgba(255,255,255,.08);border-radius:3px;
  background:linear-gradient(180deg,rgba(255,255,255,.03),transparent)
}
.fear h3{color:#f7f1e6;margin-bottom:12px;font-size:clamp(19px,2vw,23px)}
.fear p{margin:0;color:#cdc6bb;font-size:17.5px}

/* ---------- price ---------- */
.price-hero{
  font-family:var(--serif);font-size:clamp(26px,3.4vw,40px);line-height:1.25;
  color:#f7f1e6;margin:0 0 34px
}
.price-hero em{font-style:normal;color:var(--gold-lt)}

/* ---------- final ---------- */
.final{
  text-align:center;
  background:
    radial-gradient(90% 70% at 50% 0%,rgba(201,162,74,.18),transparent 62%),
    linear-gradient(180deg,#0a0a0c,#070708);
}
.final h2{margin-bottom:30px}
.final .read p{color:#ded7cb}
.sign{
  font-family:var(--serif);font-size:clamp(22px,2.6vw,30px);color:#f7f1e6;
  margin-top:40px;line-height:1.4
}

/* ---------- sticky cta ---------- */
.dock{
  position:fixed;left:50%;bottom:22px;transform:translate(-50%,140%);z-index:5;
  transition:transform .5s cubic-bezier(.2,.7,.3,1);
}
.dock.on{transform:translate(-50%,0)}
.dock .btn{padding:16px 34px;font-size:13px}

/* ---------- footer ---------- */
footer{padding:66px 0 52px;border-top:1px solid rgba(255,255,255,.07);color:var(--mute);font-size:14px}
.foot-grid{display:flex;flex-wrap:wrap;gap:18px 40px;justify-content:space-between;align-items:baseline}
.foot-name{font-family:var(--serif);font-size:20px;color:var(--cream)}

/* ---------- reveal ---------- */
.rv{opacity:0;transform:translateY(26px);transition:opacity .9s ease,transform .9s cubic-bezier(.2,.7,.3,1)}
.rv.in{opacity:1;transform:none}

/* ---------- reading progress ---------- */
.prog{
  position:fixed;top:0;left:0;height:2px;width:0;z-index:9;pointer-events:none;
  background:linear-gradient(90deg,rgba(198,160,90,.25),var(--gold));
  box-shadow:0 0 14px rgba(198,160,90,.55);transition:width .12s linear;
}

/* ---------- hero parallax ---------- */
.hero-figure{will-change:transform}

/* ---------- card lift ---------- */
.card,.story,.case{transition:transform .45s cubic-bezier(.2,.7,.3,1),box-shadow .45s ease,border-color .45s ease}
.card:hover,.story:hover{
  transform:translateY(-6px);border-color:rgba(198,160,90,.42);
  box-shadow:0 18px 46px rgba(0,0,0,.55),0 0 0 1px rgba(198,160,90,.16) inset;
}
.case:hover{transform:translateY(-4px)}
.case img{transition:box-shadow .45s ease,filter .45s ease}
.case:hover img{box-shadow:0 0 0 2px rgba(198,160,90,.5),0 14px 30px rgba(0,0,0,.5);filter:saturate(1.06)}

/* ---------- draggable rails ---------- */
.rail{cursor:grab}
.rail.dragging{cursor:grabbing;scroll-snap-type:none}
.rail.dragging *{pointer-events:none}
.rail.reviews img{cursor:zoom-in}

/* ---------- review lightbox ---------- */
.lb{
  position:fixed;inset:0;z-index:20;display:none;place-items:center;padding:26px;
  background:rgba(4,4,6,.92);backdrop-filter:blur(6px);opacity:0;transition:opacity .3s ease;
}
.lb.on{display:grid;opacity:1}
.lb img{max-width:min(92vw,560px);max-height:88vh;border-radius:16px;box-shadow:0 30px 90px rgba(0,0,0,.7)}
.lb-x{
  position:absolute;top:20px;right:24px;width:42px;height:42px;border-radius:50%;
  border:1px solid rgba(255,255,255,.22);background:rgba(0,0,0,.35);color:#f5efe4;
  font-size:20px;line-height:40px;text-align:center;cursor:pointer;
}
.lb-nav{
  position:absolute;top:50%;transform:translateY(-50%);width:46px;height:46px;border-radius:50%;
  border:1px solid rgba(255,255,255,.18);background:rgba(0,0,0,.35);color:#f5efe4;
  font-size:22px;line-height:44px;text-align:center;cursor:pointer;user-select:none;
}
.lb-prev{left:16px} .lb-next{right:16px}

/* ---------- breathing cta ---------- */
@keyframes breathe{
  0%,100%{box-shadow:0 10px 30px rgba(0,0,0,.45),0 0 0 0 rgba(198,160,90,.34)}
  50%{box-shadow:0 10px 34px rgba(0,0,0,.5),0 0 34px 6px rgba(198,160,90,.22)}
}
.dock .btn{animation:breathe 3.4s ease-in-out infinite}

/* ---------- responsive ---------- */
@media (max-width:900px){
  body{font-size:17.5px}
  .hero{min-height:auto;padding:84px 0 56px}
  .hero-grid,.author-grid{grid-template-columns:1fr;gap:34px}
  /* портрет не должен съедать первый экран: хук обязан быть виден сразу, без прокрутки */
  .hero-figure{order:-1;max-width:300px;margin-inline:auto}
  .hero-figure img{max-height:38svh;object-fit:cover;object-position:50% 12%}
  /* на 430px капитель антиквы упиралась в оба края экрана, поэтому цитата тут мельче и уже */
  .pull{font-size:26px;max-width:17ch}
  .levels,.results{grid-template-columns:1fr}
  .cases{grid-template-columns:repeat(3,1fr)}
  /* карточки историй по своему содержанию, иначе короткая тянется до высоты самой длинной */
  .rail{align-items:flex-start}
  /* На телефоне в кадре одна история, а высота ленты равна самой длинной карточке, поэтому под
     короткой зияло до 316px пустого фона. Горизонталь тут не лечится выравниванием, поэтому
     истории раскладываем в столбик: и дыра уходит, и вертикальная прокрутка привычнее пальцу.
     Первые три открыты, остальные под кнопкой, чтобы страница не выросла на пять экранов. */
  .rail.stories{
    display:grid;grid-auto-flow:row;gap:18px;overflow:visible;scroll-snap-type:none;
    cursor:auto;padding-bottom:0;margin-top:36px
  }
  .rail.stories .story{flex:none;width:100%;max-width:none}
  .rail.stories .story.more{display:none}
  .rail.stories.open .story.more{display:flex}
  .rail.stories+.rail-hint{display:none}
  .more-btn{display:block}
  .rail.stories.open+.rail-hint+.more-btn{display:none}
  .step{grid-template-columns:60px 1fr}
  .step-n{font-size:32px}
  .read .first::first-letter{font-size:58px}
}
@media (max-width:520px){
  .cases{grid-template-columns:repeat(2,1fr)}
  .btn{padding:17px 30px;font-size:13px;width:100%}
  .cta-row{flex-direction:column;align-items:stretch}
  .dock{display:none}
}
@media (prefers-reduced-motion:reduce){
  .rv{opacity:1;transform:none;transition:none}
  html{scroll-behavior:auto}
  .dock .btn{animation:none}
  .hero-figure{transform:none !important}
}
"""

JS = """
document.addEventListener('DOMContentLoaded',function(){
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
  },{threshold:.12,rootMargin:'0px 0px -8% 0px'});
  document.querySelectorAll('.rv').forEach(function(el){io.observe(el)});

  var dock=document.querySelector('.dock'), hero=document.querySelector('.hero');
  var last=document.querySelector('.final');
  var prog=document.querySelector('.prog');
  var figure=document.querySelector('.hero-figure');
  var calm=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  var wide=window.matchMedia('(min-width:901px)');
  wide.addEventListener('change',function(){ if(figure && !wide.matches) figure.style.transform=''; });

  function onScroll(){
    var y=window.scrollY, h=hero.offsetHeight;
    var nearEnd=last.getBoundingClientRect().top < window.innerHeight*0.9;
    dock.classList.toggle('on', y>h*0.9 && !nearEnd);

    var doc=document.documentElement;
    var max=doc.scrollHeight-window.innerHeight;
    if(prog) prog.style.width=(max>0 ? (y/max)*100 : 0)+'%';

    // портрет едет медленнее текста, пока первый экран в кадре.
    // ТОЛЬКО на широком экране: на телефоне и во встроенном браузере Телеграма портрет
    // наезжал на заголовок, там колонки стоят друг под другом (правка 2026-07-26)
    if(figure && !calm && wide.matches && y<h*1.2) figure.style.transform='translateY('+(y*0.14)+'px)';
  }
  window.addEventListener('scroll',onScroll,{passive:true});
  onScroll();

  // суммы в кейсах набегают от нуля
  function runCount(el){
    var raw=el.getAttribute('data-sum')||el.textContent;
    var digits=raw.replace(/[^0-9]/g,'');
    if(!digits){ return; }
    var target=parseInt(digits,10), t0=null, dur=1100;
    var pre=raw.slice(0, raw.search(/[0-9]/));
    var post=raw.slice(raw.search(/[0-9]/)).replace(/[0-9\\s\\u00a0]/g,'');
    function fmt(n){ return n.toLocaleString('ru-RU').replace(/,/g,' '); }
    function frame(t){
      if(!t0) t0=t;
      var k=Math.min((t-t0)/dur,1);
      var eased=1-Math.pow(1-k,3);
      el.textContent=pre+fmt(Math.round(target*eased))+(post?' '+post:'');
      if(k<1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  var sums=document.querySelectorAll('.case span,.story-sum');
  if(!calm && sums.length){
    var cio=new IntersectionObserver(function(es){
      es.forEach(function(e){
        if(e.isIntersecting){ runCount(e.target); cio.unobserve(e.target); }
      });
    },{threshold:.5});
    sums.forEach(function(el){ el.setAttribute('data-sum',el.textContent); cio.observe(el); });
  }

  // на телефоне истории лежат столбиком, четвёртая и дальше раскрываются по кнопке
  document.querySelectorAll('.more-btn').forEach(function(btn){
    btn.addEventListener('click',function(){
      var rail=document.querySelector('.rail.'+btn.getAttribute('data-rail'));
      if(!rail) return;
      rail.classList.add('open');
      btn.style.display='none';
    });
  });

  // ленты тянутся мышью с инерцией
  document.querySelectorAll('.rail').forEach(function(rail){
    var down=false,sx=0,sl=0,moved=0;
    rail.addEventListener('pointerdown',function(e){
      if(e.pointerType==='touch') return;
      down=true;moved=0;sx=e.clientX;sl=rail.scrollLeft;
    });
    rail.addEventListener('pointermove',function(e){
      if(!down) return;
      var d=e.clientX-sx; moved=Math.abs(d);
      // класс вешаем только когда тянут по-настоящему: он гасит pointer-events у детей,
      // а на простом нажатии это съедало клик по отзыву
      if(moved>6) rail.classList.add('dragging');
      rail.scrollLeft=sl-d;
    });
    ['pointerup','pointerleave','pointercancel'].forEach(function(ev){
      rail.addEventListener(ev,function(){ down=false;rail.classList.remove('dragging'); });
    });
    rail.addEventListener('click',function(e){ if(moved>6) e.preventDefault(); },true);
  });

  // отзыв во весь экран
  var shots=[].slice.call(document.querySelectorAll('.rail.reviews img'));
  if(shots.length){
    var lb=document.createElement('div');
    lb.className='lb';
    lb.innerHTML='<button class="lb-x" aria-label="Закрыть">&#215;</button>'+
      '<button class="lb-nav lb-prev" aria-label="Назад">&#8249;</button>'+
      '<img alt="Отзыв">'+
      '<button class="lb-nav lb-next" aria-label="Вперёд">&#8250;</button>';
    document.body.appendChild(lb);
    var big=lb.querySelector('img'), idx=0;
    function show(i){
      idx=(i+shots.length)%shots.length;
      big.src=shots[idx].getAttribute('src');
      lb.classList.add('on');
      document.body.style.overflow='hidden';
    }
    function hide(){ lb.classList.remove('on'); document.body.style.overflow=''; }
    shots.forEach(function(im,i){ im.addEventListener('click',function(){ show(i); }); });
    lb.querySelector('.lb-x').addEventListener('click',hide);
    lb.querySelector('.lb-prev').addEventListener('click',function(e){ e.stopPropagation(); show(idx-1); });
    lb.querySelector('.lb-next').addEventListener('click',function(e){ e.stopPropagation(); show(idx+1); });
    lb.addEventListener('click',function(e){ if(e.target===lb) hide(); });
    document.addEventListener('keydown',function(e){
      if(!lb.classList.contains('on')) return;
      if(e.key==='Escape') hide();
      if(e.key==='ArrowLeft') show(idx-1);
      if(e.key==='ArrowRight') show(idx+1);
    });
  }
});
"""


NBSP = " "

# служебные слова, которые не должны висеть в конце строки. Только предлоги, союзы и
# частицы: если цеплять подряд все короткие слова, слипается смысловая пара («Час у
# сильного»), и на узком экране такая связка вылезает за край
SHORT = "в во на за к ко с со о об от до по из у и а но да не ни то"
SHORT_RE = re.compile(
    r"(?<![^\s(«„])(" + "|".join(sorted(SHORT.split(), key=len, reverse=True)) + r")\s"
    r"(?=[А-Яа-яЁёA-Za-z0-9«])",
    re.IGNORECASE,
)


def typo(html: str) -> str:
    """Расставить неразрывные пробелы там, где перенос уродует строку.

    Держим вместе разряды числа и валюту («10 000 ₽» на телефоне рвалось на две
    строки) и не оставляем короткие слова висеть в конце строки. Разметку и
    содержимое script/style не трогаем.
    """
    chunks = re.split(r"(<(?:script|style)\b.*?</(?:script|style)>|<[^>]+>)", html, flags=re.S)
    for i, chunk in enumerate(chunks):
        if chunk.startswith("<"):
            continue
        t = chunk
        for _ in range(3):  # 1 200 000 разбирается по одной группе за проход
            t = re.sub(r"(\d)\s(?=\d{3}(?!\d))", r"\1" + NBSP, t)
        t = re.sub(r"(\d)\s(?=(?:₽|млн|тыс|человек|минут|дн[еяй]))", r"\1" + NBSP, t)
        t = SHORT_RE.sub(r"\1" + NBSP, t)
        # частицы липнут к предыдущему слову: «вроде бы», «так же»
        t = re.sub(r"\s(бы|же|ли)(?=[\s,.!?;:)])", NBSP + r"\1", t)
        # две связки подряд («и не пытается») превращаются в длинное неразрывное слово
        # и рвут строку на узком экране, поэтому цепочки длиннее пары расклеиваем
        while True:
            loose = re.sub(NBSP + r"([А-Яа-яЁёA-Za-z]+)" + NBSP, NBSP + r"\1 ", t)
            if loose == t:
                break
            t = loose
        chunks[i] = t
    return "".join(chunks)


def sizes(html: str) -> str:
    """Проставить каждой картинке её настоящие размеры.

    Без width/height браузер не знает высоту кадра до загрузки файла, и страница
    прыгает по мере их подгрузки. В обычном браузере это почти незаметно из-за
    кеша, а во встроенном браузере Telegram выглядит как тряска при прокрутке.
    """
    def add(m: "re.Match[str]") -> str:
        tag, src = m.group(0), m.group(1)
        if "width=" in tag:
            return tag
        path = OUT / src
        if not path.exists():
            return tag
        with Image.open(path) as im:
            w, h = im.size
        return tag[:-1] + f' width="{w}" height="{h}">'

    return re.sub(r'<img [^>]*src="([^"]+)"[^>]*>', add, html)


def p(items):
    return "\n".join(f"<p>{t}</p>" for t in items)


# Поля, которые раньше были вбиты в этот файл литералами: title, meta-теги, имя автора,
# alt и имена файлов фотографий, подписи над блоками. Из-за этого ЛЮБОЙ собранный лендинг
# уходил с именем чужого клиента, даже когда content.py был заполнен правильно: в title,
# в превью ссылки для Telegram и в alt картинок. Дефолта здесь нет намеренно, гейт роняет
# сборку с перечислением незаполненного. Заглушка отмечена маркером TODO_, как в design.md.
META_FIELDS = {
    "title": "<title> страницы: продукт, суть, имя автора",
    "description": "meta description, 1-2 предложения, попадает в выдачу",
    "og_title": "заголовок превью ссылки в Telegram и соцсетях",
    "og_description": "описание превью ссылки",
    "site_name": "имя автора или проекта для og:site_name",
    "twitter_title": "заголовок превью для twitter-карточки",
    "twitter_description": "описание превью для twitter-карточки",
    "favicon_letter": "одна буква в иконку вкладки, обычно первая буква продукта",
    "author_name": "имя автора: заголовок блока про автора и alt его фотографий",
    "hero_img": "файл портрета в первый экран, лежит в out/img/",
    "author_img": "файл фотографии в блок про автора, лежит в out/img/",
    "cases_eyebrow": "подпись над блоком кейсов, например «Клиенты <имя> в цифрах»",
    "stories_eyebrow": "подпись над лентой отзывов",
    "price_hero": "фраза про цену крупным шрифтом, можно с <br> и <em>",
}


def need_meta(c) -> dict:
    """Словарь META из content.py, с проверкой что он заполнен фактурой СВОЕГО клиента."""
    raw = getattr(c, "META", None)
    if not isinstance(raw, dict):
        raise SystemExit(
            "content.py: нет словаря META. Скопируй его из templates/content.template.py "
            "и заполни данными своего клиента. Эти поля уходят в title страницы, в превью "
            "ссылки для Telegram и в alt фотографий."
        )
    miss = [
        f"{k} ({d})"
        for k, d in META_FIELDS.items()
        if not str(raw.get(k, "")).strip() or "TODO_" in str(raw.get(k, ""))
    ]
    if miss:
        raise SystemExit(
            "content.py, META: не заполнено " + str(len(miss)) + " из "
            + str(len(META_FIELDS)) + ":\n  " + "\n  ".join(miss)
            + "\nЗначения снимаются с материалов клиента. Чужие не подставлять даже "
              "как отправную точку: они уедут в title и в превью ссылки."
        )
    return raw


def build() -> str:
    c = C
    m = need_meta(c)
    cases = "\n".join(
        f'<div class="case"><img src="img/case_{i:02d}.jpg" alt="{n}" loading="lazy">'
        f"<b>@{n}</b><span>{s}</span></div>"
        for i, (n, s) in enumerate(c.CASES)
    )
    levels = "\n".join(
        f'<article class="card"><h3>{t}</h3><p>{d}</p></article>' for t, d in c.LEVELS
    )
    steps = "\n".join(
        f'<div class="step rv"><div class="step-n">{i:02d}</div>'
        f"<div><h3>{t}</h3><p>{d}</p></div></div>"
        for i, (t, d) in enumerate(c.STEPS, 1)
    )
    results = "\n".join(f'<div class="result">{r}</div>' for r in c.RESULTS)
    # класс more достаётся историям с четвёртой: на телефоне они прячутся под кнопку,
    # на десктопе класс ни на что не влияет
    stories = "\n".join(
        f"""<article class="story{' more' if i >= 3 else ''}">
  <header class="story-top">
    <img src="img/sav_{i}.jpg" alt="{s['name']}" loading="lazy">
    <div>
      <h3>{s['name']}</h3>
      <p class="story-niche">{s['niche']}</p>
      <p class="story-handle">@{s['handle']}</p>
    </div>
  </header>
  <p class="story-sum">{s['sum']}</p>
  <div class="story-col">
    <p class="story-lbl">Точка А</p>
    <ul class="story-a">{''.join(f'<li>{x}</li>' for x in s['a'])}</ul>
  </div>
  <div class="story-col">
    <p class="story-lbl gold">Точка Б</p>
    <ul class="story-b">{''.join(f'<li>{x}</li>' for x in s['b'])}</ul>
  </div>
</article>"""
        for i, s in enumerate(c.STORIES)
    )
    n_rest = max(len(c.STORIES) - 3, 0)
    tail = n_rest % 10
    if tail == 1 and n_rest % 100 != 11:
        stories_rest = f"{n_rest} историю"
    elif tail in (2, 3, 4) and n_rest % 100 not in (12, 13, 14):
        stories_rest = f"{n_rest} истории"
    else:
        stories_rest = f"{n_rest} историй"
    reviews = "\n".join(
        f'<img src="img/review_{i:02d}.jpg" alt="Отзыв" loading="lazy">' for i in range(10)
    )
    fears = "\n".join(
        f'<article class="fear rv"><h3>{q}</h3><p>{a}</p></article>' for q, a in c.FEARS
    )
    loops = "\n".join(f"<li>{t}</li>" for t in c.LOOPS)

    css = CSS.replace("%GRAIN%", GRAIN)

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{m['title']}</title>
<meta name="description" content="{m['description']}">
<meta property="og:title" content="{m['og_title']}">
<meta property="og:description" content="{m['og_description']}">
<meta property="og:type" content="article">
<!-- превью ссылки: без картинки страница уходит в Telegram голой строкой -->
<meta property="og:image" content="{c.SITE_URL}img/og.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{c.SITE_URL}">
<meta property="og:site_name" content="{m['site_name']}">
<meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{m['twitter_title']}">
<meta name="twitter:description" content="{m['twitter_description']}">
<meta name="twitter:image" content="{c.SITE_URL}img/og.jpg">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%230b0a09'/><text x='16' y='23' font-family='Georgia,serif' font-size='19' fill='%23c6a05a' text-anchor='middle'>{m['favicon_letter']}</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500&family=Manrope:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<div class="prog"></div>

<header class="hero">
  <div class="wrap hero-grid">
    <div>
      <p class="kicker">{c.HERO['kicker']}</p>
      <h1>{c.HERO['h1']}</h1>
      <p class="lead">{c.HERO['sub']}</p>
      <div class="cta-row">
        <a class="btn" href="{c.BOT_URL}" target="_blank" rel="noopener">{c.CTA}</a>
      </div>
      <p class="hero-note">{c.HERO['note']}</p>
      <div class="scroll-hint"><span></span>История ниже</div>
    </div>
    <figure class="hero-figure">
      <img src="img/{m['hero_img']}" alt="{m['author_name']}" fetchpriority="high">
      <figcaption></figcaption>
    </figure>
  </div>
</header>

<hr class="sec-line">

<section>
  <div class="read rv">
    <p class="first lead">{c.PAIN[0]}</p>
    {p(c.PAIN[1:])}
    <p class="qmark">{c.PAIN_Q}</p>
  </div>
  <div class="read rv" style="margin-top:44px">
    {p(c.PAIN2)}
  </div>
  <p class="pull rv">{c.TRUTH}</p>
  <div class="read rv">
    {p(c.PROGRAM)}
    <ol class="loops">{loops}</ol>
  </div>
  <p class="pull rv">{c.CAUSE}</p>
</section>

<hr class="sec-line">

<section class="panel">
  <div class="wrap author-grid rv">
    <figure class="author-figure"><img src="img/{m['author_img']}" alt="{m['author_name']}" loading="lazy"></figure>
    <div>
      <p class="eyebrow">Автор</p>
      <h2>{m['author_name']}</h2>
      <div style="margin-top:26px">{p(c.AUTHOR)}</div>
    </div>
  </div>
</section>

<hr class="sec-line">

<section>
  <div class="wrap">
    <div class="rv" style="max-width:760px">
      <p class="eyebrow">Как это работает</p>
      <h2>{c.HOW_INTRO}</h2>
    </div>
    <div class="levels rv">{levels}</div>
    <div class="read rv" style="margin-top:56px"><p>{c.HOW_MID}</p></div>
    <div class="steps">{steps}</div>
  </div>
</section>

<hr class="sec-line">

<section class="panel">
  <div class="wrap">
    <div class="rv" style="max-width:820px">
      <p class="eyebrow">Результаты</p>
      <h2>Что говорят люди, которые уже прошли этот путь</h2>
    </div>
    <div class="results rv" style="margin-top:44px">{results}</div>
    <div class="read rv" style="margin-left:0"><p class="mute">{c.RESULTS_TAIL}</p></div>

    <div class="rv" style="margin-top:72px">
      <p class="eyebrow">{m['cases_eyebrow']}</p>
      <div class="cases">{cases}</div>
    </div>

    <div class="rv" style="margin-top:84px">
      <p class="eyebrow">Истории до и после</p>
      <div class="rail stories">{stories}</div>
      <p class="rail-hint">Листай в сторону</p>
      <button class="more-btn" type="button" data-rail="stories">Показать ещё {stories_rest}</button>
    </div>

    <div class="rv" style="margin-top:64px">
      <p class="eyebrow">{m['stories_eyebrow']}</p>
      <div class="rail reviews">{reviews}</div>
      <p class="rail-hint">Листай в сторону</p>
    </div>
  </div>
</section>

<hr class="sec-line">

<section>
  <div class="wrap" style="max-width:900px">
    <div class="rv">
      <p class="eyebrow">Честно об опасениях</p>
      <h2>Три вопроса, которые задают чаще всего</h2>
    </div>
    <div class="fears">{fears}</div>
  </div>
</section>

<hr class="sec-line">

<section class="panel">
  <div class="read rv">
    <p class="eyebrow">Сколько это стоит</p>
    <p class="price-hero">{m['price_hero']}</p>
    {p(c.PRICE[1:])}
    <div class="cta-row"><a class="btn btn-ghost" href="{c.BOT_URL}" target="_blank" rel="noopener">{c.CTA}</a></div>
  </div>
</section>

<hr class="sec-line">

<section class="final">
  <div class="read rv">
    <p class="eyebrow">Твой ход</p>
    <h2>Дальше два пути</h2>
    <div style="margin-top:34px">{p(c.FINAL)}</div>
    <div class="cta-row" style="justify-content:center">
      <a class="btn" href="{c.BOT_URL}" target="_blank" rel="noopener">{c.CTA}</a>
    </div>
    <p class="hero-note">{c.HERO['note']}</p>
    <p class="sign">{c.SIGN}</p>
  </div>
</section>

<div class="dock"><a class="btn" href="{c.BOT_URL}" target="_blank" rel="noopener">{c.CTA}</a></div>

<footer>
  <div class="wrap foot-grid">
    <span class="foot-name">{c.FOOTER['name']}</span>
    <span>{c.FOOTER['req']}</span>
    <span>{c.FOOTER['note']}</span>
  </div>
</footer>

<script>{JS}</script>
</body>
</html>
"""


# Шрифт, объявленный в токене, но нигде не подключённый, страница берёт молча:
# браузер уходит в следующее семейство списка, и на глаз в Chromium всё выглядит
# нормально. На iPhone такая подмена ломала набор чисел (пробелы склеивались,
# запятая уезжала к соседнему слову), и заметил это только заказчик на телефоне.
# Проверка ниже говорит об этом на сборке, вместо того чтобы ждать чужого скрина.
#
# По SKILL.md шрифт заголовков берётся с сайта клиента и КЛАДЁТСЯ в out/fonts/.
# Пропуск этого шага и есть источник подмены, поэтому проверяем ФАЙЛ на диске, а
# не только наличие объявления.
_SYSTEM_FAMILIES = {
    "serif", "sans-serif", "monospace", "system-ui", "ui-serif", "ui-sans-serif",
    "georgia", "times new roman", "arial", "helvetica", "roboto", "segoe ui",
    "-apple-system", "blinkmacsystemfont", "courier new", "cursive",
}


_FONT_FACE_RE = re.compile(r"@font-face\s*{[^}]*}", re.I)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_FONT_FAMILY_RE = re.compile(
    r"""font-family\s*:\s*(?:'([^']+)'|"([^"]+)"|([^;}"']+))""", re.I
)
_FONT_SRC_START_RE = re.compile(r"\bsrc\s*:\s*", re.I)
_CSS_URL_RE = re.compile(r"""url\(\s*(?:'([^']*)'|"([^"]*)"|([^)"']*))""", re.I)
_CSS_LOCAL_RE = re.compile(r"\blocal\s*\(", re.I)


def _css_scan_to(text: str, start: int, stops: str) -> int:
    """Индекс первого символа из stops, встреченного ВНЕ строки, начиная с start.

    Учитываются обе кавычки и экранирование обратным слэшем: в CSS `'\\''` это
    строка с кавычкой внутри, и наивный поиск закрывающей кавычки уезжал за границу
    объявления, проглатывая соседнее свойство (поймано Codex). Круглые скобки не
    считаются стопом, их обрабатывает вызывающий.
    """
    quote = ""
    esc = False
    i = start
    while i < len(text):
        ch = text[i]
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch in stops:
            return i
        i += 1
    return len(text)


def _font_face_blocks(css: str) -> list[str]:
    """Тела всех блоков @font-face, без фигурных скобок.

    Границу блока нельзя искать через `[^}]*}`: '}' законна ВНУТРИ строки, например
    в data-URI, и такой поиск обрывал блок посередине, давая ложное предупреждение
    на рабочем шрифте (поймано Codex). Поэтому конец ищется посимвольно, с учётом
    кавычек и экранирования.
    """
    out: list[str] = []
    low = css.lower()
    i = 0
    while True:
        j = low.find("@font-face", i)
        if j < 0:
            return out
        k = css.find("{", j)
        if k < 0:
            return out
        end = _css_scan_to(css, k + 1, "}")
        out.append(css[k + 1:end])
        i = end + 1


def _css_parens_balanced(value: str) -> bool:
    """Сбалансированы ли круглые скобки вне строк.

    Незакрытая `url(` или `local(` это сломанный CSS: браузер такой источник не
    загрузит, поэтому подтверждать им подключение шрифта нельзя (поймано Codex).
    """
    quote = ""
    esc = False
    depth = 0
    for ch in value:
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not quote


def _css_src_values(block: str) -> str:
    """Значения всех объявлений src в блоке, склеенные через пробел.

    Границу объявления нельзя искать простым `[^;}]*`: точка с запятой законно
    встречается ВНУТРИ значения, например в data-URI (`url('data:font/woff;base64,…')`),
    и такая граница рвала адрес посередине. Поэтому идём посимвольно и считаем
    разделителем только ';' или '}' вне кавычек и вне круглых скобок.
    """
    out: list[str] = []
    pos = 0
    # Следующее объявление ищется от КОНЦА предыдущего значения, а не все позиции
    # заранее: при несбалансированных скобках каждое значение тянется до конца блока,
    # и поиск «от начала для каждого src» давал квадратичное время. Замер Codex на
    # повторах «src:(;»: 500 штук 0.93 с, 2000 штук 23 с, 4000 не дождался. Гейт не
    # бросал исключений, но подвешивал сборку на кривом входе.
    while pos < len(block):
        m = _FONT_SRC_START_RE.search(block, pos)
        if m is None:
            break
        start = i = m.end()
        depth = 0
        while i < len(block):
            # Стоп ищем только на верхнем уровне скобок: внутри url(...) точка с
            # запятой законна (data-URI).
            i = _css_scan_to(block, i, ";}()")
            if i >= len(block):
                break
            ch = block[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif depth == 0:
                break
            i += 1
        out.append(block[start:i])
        pos = max(i, m.end())
    return " ".join(out)


def _css_unescape(value: str) -> str:
    """Снять простое CSS-экранирование: `my\\ font.woff` это имя с пробелом.

    Полную спецификацию (шестнадцатеричные коды вида `\\41 `) не разбираем, в наших
    сборках их не бывает. Закрывается ровно обратный слэш перед символом, из-за которого
    существующий файл с пробелом в имени считался отсутствующим (поймано Codex).
    """
    return re.sub(r"\\(.)", r"\1", value)


def _font_url_label(url: str) -> str:
    """Имя файла из URL шрифта, без каталогов: путь в лог попадать не должен.

    Разделителем считается и '/', и '\\': путь вида C:\\Users\\кто-то\\x.woff иначе
    попадал в предупреждение целиком, а это ровно та утечка, которую тут и закрываем
    (поймано Codex).
    """
    bare = url.split("?", 1)[0].split("#", 1)[0]
    # Берётся РОВНО последний сегмент. Адрес, кончающийся разделителем, имени файла
    # не содержит, и подставлять вместо него последний каталог нельзя: в лог уехал бы
    # кусок пути, а исходный URL целиком уезжал там до этого (поймано Codex).
    name = re.split(r"[\\/]", bare)[-1].strip()
    if name:
        return name
    return "(адрес пуст)" if not url.strip() else "(в адресе нет имени файла)"


def _font_url_is_reachable(url: str, out_dir: pathlib.Path) -> bool:
    """Отдастся ли шрифт по этому URL из СОБРАННОЙ страницы.

    Смысл в слове «собранной»: проверяем раздачу, а не машину сборщика.
    - http(s):// и // — грузит браузер, файла в сборке и не должно быть;
    - data: — шрифт лежит в самой странице;
    - file:// — путь машины сборщика, в раздачу не попадёт;
    - всё прочее считается путём ВНУТРИ раздачи, и ведущий '/' тут означает
      корень сайта, а не корень файловой системы: `url('/fonts/x.woff')` это
      законная запись, файл лежит в сборке. Поэтому ведущие слэши срезаются, и
      путь всегда ищется от out_dir. Побочно это отвечает и на абсолютный путь
      машины сборщика: '/чужой/абсолютный/путь/x.woff' внутри сборки не найдётся, и гейт
      скажет об этом. Своей ветки для него не нужно, они неотличимы по виду
      (поймано Codex: безусловный отказ на '/' давал ложное срабатывание).
      pathlib отдельно важен тем, что `out_dir / "/abs"` возвращает САМ
      абсолютный путь, то есть без срезания слэшей проверка ушла бы на чужой
      файл: у сборщика он есть, в раздаче его нет, гейт молчал бы.
    - ?query и #fragment отрезаются: версионный '?v=1' законен.
    """
    low = url.strip().lower()
    if low.startswith(("http://", "https://", "//", "data:")):
        return True
    if low.startswith("file://"):
        return False
    # Экранирование снимается тут, где ищется файл: `my\ font.woff` это имя с пробелом.
    rel = _css_unescape(url).split("?", 1)[0].split("#", 1)[0].lstrip("/")
    if not rel:
        return False
    target = out_dir / rel
    # '..' не должен выводить проверку за пределы сборки: наружу файл всё равно
    # не отдастся, а смотреть там чужие файлы незачем.
    try:
        target.resolve().relative_to(out_dir.resolve())
    except (ValueError, OSError):
        return False
    return target.exists()


def font_warnings(html: str, out_dir: pathlib.Path) -> list[str]:
    """Семейства из токенов --serif/--sans, которые страница не сможет загрузить."""
    linked: set[str] = set()
    linked_missing: list[str] = []
    # Подключённое ссылкой Google Fonts: family=Playfair+Display:wght@400;500
    for fam in re.findall(r"family=([^&:\"']+)", html):
        linked.add(fam.replace("+", " ").strip().lower())
    # Подключённое своим файлом: @font-face{font-family:'X';src:url('...')}
    # Кавычки в CSS законны любые и не обязательны вовсе, поэтому берём все три
    # формы: 'X', "X", X. На одинарных-только регулярках корректный @font-face с
    # двойными кавычками читался как отсутствующий (поймано Codex).
    # Регистр в CSS здесь не значим, а пробелы вокруг двоеточия законны: без re.I и
    # \s* запись «@FONT-FACE { FONT-FAMILY : 'X' }» читалась как отсутствующее
    # объявление и давала ложное предупреждение на рабочей странице (поймано Codex).
    # Комментарии вырезаются из ВСЕГО документа до поиска блоков: если резать уже
    # внутри найденного блока, целиком закомментированный @font-face всё равно
    # считался действующим объявлением (поймано Codex).
    for block in _font_face_blocks(_CSS_COMMENT_RE.sub(" ", html)):
        names = [next(g for g in m if g).strip() for m in _FONT_FAMILY_RE.findall(block)]
        if not names:
            continue
        name = names[0].strip().lower()
        # Источники берутся ТОЛЬКО из декларации src, а не из всего блока: url() в
        # соседнем свойстве к загрузке шрифта отношения не имеет, и запись
        # «src:bogus; foo:url('есть.woff')» выдавала шрифт за подключённый (Codex).
        src_value = _css_src_values(block)
        # Кванторы '*' у url НАРОЧНО: пустой url('') это законный по синтаксису, но
        # неработающий адрес.
        # Экранирование снимается НЕ здесь, а внутри проверки существования файла:
        # для имени в логе обратный слэш это ещё и разделитель windows-пути, и снятое
        # заранее экранирование склеивало путь в одно «имя», то есть возвращало ровно
        # ту утечку, которую мы закрыли (поймано собственным тестом).
        urls = [next((g for g in m if g), "").strip() for m in _CSS_URL_RE.findall(src_value)]
        # src это СПИСОК источников, браузер идёт по нему до первого рабочего. Поэтому
        # шрифт считается подключённым, если достижим хотя бы один, а предупреждение
        # выдаётся, только когда не работает ни один. Судить по первому источнику было
        # неверно: запись src:url('x.woff2'),url('x.woff') штатная, и отсутствие
        # первого файла ещё не значит, что шрифта не будет.
        #
        # local('X') означает «взять с машины читателя», проверять на диске нечего;
        # это единственный законный src без url().
        # Сломанный src (незакрытая url( или local(, незакрытая кавычка) браузер не
        # загрузит, поэтому подтверждать им подключение нельзя.
        if _css_parens_balanced(src_value):
            has_local = bool(_CSS_LOCAL_RE.search(src_value))
            reachable = has_local or any(_font_url_is_reachable(u, out_dir) for u in urls)
        else:
            reachable = False
        if reachable:
            linked.add(name)
        else:
            # Печатаем ТОЛЬКО имя файла. Абсолютный путь из CSS (или out_dir)
            # раскрывал бы в логе имя пользователя и проекта. Обращение к urls[0]
            # здесь делать нельзя: список бывает пустым (блок без url), и на этом
            # гейт падал исключением, то есть ронял сборку, чего ему делать нельзя.
            if len(urls) > 1:
                shown = ", ".join(f"'{_font_url_label(u)}'" for u in urls[:3])
                linked_missing.append(
                    f"@font-face '{names[0]}': ни один из указанных файлов не найден "
                    f"в сборке ({shown})"
                )
            elif urls:
                linked_missing.append(
                    f"@font-face '{names[0]}' ссылается на файл "
                    f"'{_font_url_label(urls[0])}', а в сборке его нет"
                )
            else:
                linked_missing.append(
                    f"@font-face '{names[0]}' не указывает файл шрифта "
                    "(в src нет ни url(), ни local())"
                )
            linked.discard(name)

    warnings: list[str] = list(linked_missing)
    # Граница [;}]: последнее объявление в блоке CSS законно идёт без «;»,
    # и на таком токене проверка молча не находила ничего (поймано тестом).
    for token in re.findall(r"--(?:serif|sans):([^;}]+)[;}]", html):
        families = [f.strip().strip("'\"").lower() for f in token.split(",") if f.strip()]
        # Значим ТОЛЬКО первый: остальные и есть запасные, их браузер берёт
        # штатно. Если первым стоит системное семейство (system-ui и подобные),
        # подключать нечего и претензий нет.
        for fam in families[:1]:
            if fam in _SYSTEM_FAMILIES:
                continue
            if fam not in linked:
                warnings.append(
                    f"шрифт '{fam}' стоит в токене, но не подключён "
                    "(ни ссылкой Google Fonts, ни @font-face с существующим файлом) "
                    "-> браузер молча возьмёт следующий из списка"
                )
            break  # значим только ПЕРВЫЙ, остальные и есть запасные
    return warnings


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    html = sizes(typo(build()))
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"written {OUT/'index.html'} ({len(html)} bytes)")
    # Предупреждение, а не отказ: сборку ломать нельзя, страница рабочая и без
    # своего шрифта. Но молчать об этом тоже нельзя, иначе подмену находит
    # заказчик на своём телефоне.
    for w in font_warnings(html, OUT):
        print(f"ВНИМАНИЕ (шрифты): {w}")
