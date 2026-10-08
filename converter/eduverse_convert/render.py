"""Writes a self-contained preview reader (index.html) next to book.json. No server needed."""
import json, shutil
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"


def write_preview(book, report, out: Path):
    a = out / "assets"
    a.mkdir(exist_ok=True)
    for f in ("katex.min.js", "katex.min.css", "zprox_logo_light.png", "zprox_logo_dark.png", "zprox_mark.png"):
        shutil.copy(ASSETS / f, a / f)
    shutil.copytree(ASSETS / "fonts", a / "fonts", dirs_exist_ok=True)
    data = json.dumps({"book": book, "report": report}, ensure_ascii=False, default=list).replace("</", "<\\/")
    (out / "index.html").write_text(TEMPLATE.replace("__DATA__", data), encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EduVerse preview</title>
<link rel="stylesheet" href="assets/katex.min.css"><script src="assets/katex.min.js"></script>
<style>
:root{--red:#E0212F;--red-soft:#FDECEE;--ink:#1B1D22;--ink2:#4A4F59;--ink3:#7D838F;--bg:#fff;--panel:#F5F6F8;--line:#E4E6EA;--line2:#D3D6DC;--mark:#FFF1D6;--markline:#E8A33D}
[data-theme=dark]{--ink:#ECEEF2;--ink2:#B9BEC8;--ink3:#868C98;--bg:#16181D;--panel:#1E2127;--line:#2C3038;--line2:#3A3F49;--red-soft:#3A1519;--mark:#3A2E14;--markline:#C98A2B}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);font-size:15px;line-height:1.55}
button{font:inherit;color:inherit;cursor:pointer}
.top{height:56px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;padding:0 20px;position:sticky;top:0;background:var(--bg);z-index:5}
.top img.mark{width:32px;height:32px;object-fit:contain}.top b{font-size:17px}
.top .crumbs{color:var(--ink3);display:flex;gap:8px;align-items:center}.top .crumbs a{color:var(--ink2);text-decoration:none;cursor:pointer}
.top .sp{margin-left:auto;display:flex;gap:8px}
.btn{border:1px solid var(--line2);background:var(--bg);border-radius:8px;padding:7px 12px;font-weight:700}
.btn.primary{background:var(--red);border-color:var(--red);color:#fff}
.wrap{max-width:1100px;margin:0 auto;padding:28px 24px 60px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:-.3px}.muted{color:var(--ink3)}
.bookcard{display:grid;grid-template-columns:200px 1fr;gap:28px;border:1px solid var(--line);border-radius:14px;padding:22px}
.cover{aspect-ratio:3/4;border-radius:10px;background:#121212;color:#fff;padding:18px;display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden}
.cover .cls{font-size:64px;font-weight:700;color:var(--red);line-height:1}.cover .subj{font-size:22px;font-weight:700}.cover small{color:#B9B9B9}
.cover:after{content:"";position:absolute;right:-30px;top:-30px;width:120px;height:120px;border:14px solid var(--red);border-radius:50%;opacity:.25}
.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid var(--line);border-radius:10px;margin:16px 0}
.facts div{padding:10px 14px;border-right:1px solid var(--line)}.facts div:last-child{border:0}.facts b{display:block;font-size:20px}
.toc{margin-top:26px;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.toc .row{display:grid;grid-template-columns:60px 1fr 90px 110px 120px;align-items:center;padding:11px 16px;border-bottom:1px solid var(--line)}
.toc .row:last-child{border:0}.toc .row.head{font-size:12px;font-weight:700;color:var(--ink3);background:var(--panel)}
.toc .row.on{cursor:pointer}.toc .row.on:hover{background:var(--panel)}.toc .row.off{color:var(--ink3)}
.toc .n{font-weight:700;color:var(--red)}.tag{font-size:12px;font-weight:700;padding:2px 9px;border-radius:20px;background:var(--panel);color:var(--ink2);justify-self:start}
.tag.ok{background:#E6F4EC;color:#1F7A4D}.tag.warn{background:#FFF3DC;color:#9A5B00}
.reader{display:grid;grid-template-columns:270px 1fr 360px;height:calc(100vh - 56px)}
.rail{border-right:1px solid var(--line);overflow:auto;padding:16px 10px;background:var(--panel)}
.rail h3{margin:4px 8px 12px;font-size:15px}.rail .unit{color:var(--red);font-weight:700;font-size:13px;margin:0 8px}
.rail a{display:block;padding:6px 10px;border-radius:7px;color:var(--ink2);text-decoration:none;cursor:pointer;font-size:14px}
.rail a.l3{padding-left:26px;font-size:13px}.rail a:hover{background:var(--bg)}.rail a.cur{background:var(--bg);color:var(--red);font-weight:700;box-shadow:inset 3px 0 0 var(--red)}
.rail .num{color:var(--ink3);margin-right:6px;font-variant-numeric:tabular-nums}.rail .sep{height:1px;background:var(--line);margin:10px 8px}
.page{overflow:auto;padding:26px 44px 80px;scroll-behavior:smooth}
.page .inner{max-width:720px;margin:0 auto}
.chap-head{border-bottom:2px solid var(--red);padding-bottom:12px;margin-bottom:18px}.chap-head .u{color:var(--red);font-weight:700}
.chap-head h1{font-size:32px}
h2.sec{font-size:21px;margin:30px 0 8px}h3.sec{font-size:17px;margin:22px 0 6px}h2.sec .n,h3.sec .n{color:var(--red);margin-right:8px}
p{margin:0 0 12px}ul,ol{margin:0 0 12px;padding-left:24px}li{margin:3px 0}
.kw{font-size:1.08em;font-weight:700;color:var(--red);background:var(--mark);border-bottom:2px solid var(--markline);cursor:pointer;border-radius:3px;padding:1px 3px}
.kw:hover,.kw.sel{background:var(--red-soft);border-color:var(--red)}
.kw:focus-visible{outline:2px solid var(--red);outline-offset:1px}
.box{border:1px solid var(--line);border-left:4px solid var(--red);border-radius:8px;padding:12px 16px;margin:16px 0;background:var(--bg)}
.box .bt{font-weight:700;font-size:13px;color:var(--red);margin-bottom:6px}
.box.points,.box.glossary,.box.exercises,.box.references,.box.internet,.box.concept_map,.box.ict,.box.learning_objectives{border-left-color:var(--ink)}
.box.points .bt,.box.glossary .bt,.box.exercises .bt,.box.references .bt,.box.internet .bt,.box.concept_map .bt,.box.ict .bt,.box.learning_objectives .bt{color:var(--ink)}
.marker{display:inline-block;font-size:12px;font-weight:700;color:var(--ink3);border:1px dashed var(--line2);border-radius:20px;padding:2px 10px;margin:4px 0 12px}
figure{margin:16px 0;text-align:center}figure img{max-width:min(100%,420px);max-height:220px;width:auto;height:auto;object-fit:contain;border-radius:6px;border:1px solid var(--line);cursor:zoom-in}
figure img.big{max-width:100%;max-height:none;cursor:zoom-out}
figcaption{font-size:13px;color:var(--ink2);margin-top:6px}figcaption b{color:var(--red)}
.tbl{overflow-x:auto;margin:16px 0}.tbl table{border-collapse:collapse;width:100%;font-size:14px}
.tbl td,.tbl th{border:1px solid var(--line2);padding:6px 10px;text-align:left;vertical-align:top}.tbl th{background:var(--panel)}
.tcap{font-size:13px;color:var(--ink2);margin-bottom:6px}.tcap b{color:var(--red)}
.eq{margin:10px 0;padding:8px 12px;background:var(--panel);border-radius:8px;overflow-x:auto}
.side{border-left:1px solid var(--line);overflow:auto;padding:18px}
.side .empty{color:var(--ink3);text-align:center;margin-top:60px;padding:0 10px}
.side h2{margin:0 0 4px;font-size:22px}.side .sig{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 14px}
.side .sig span{font-size:11px;border:1px solid var(--line2);border-radius:20px;padding:1px 8px;color:var(--ink2)}
.side .sig span.pre{border-color:var(--red);color:var(--red)}
.side .card{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:12px}
.side .card .h{font-size:12px;font-weight:700;color:var(--ink3);margin-bottom:6px}
.side .card img{max-width:100%;max-height:140px;object-fit:contain;border-radius:6px;margin-bottom:6px}
.side .ai{border-color:var(--red)}
.depths{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 10px}.depths button{border:1px solid var(--line2);background:var(--bg);border-radius:20px;padding:3px 10px;font-size:12px}
.depths button.on{background:var(--red);border-color:var(--red);color:#fff;font-weight:700}
.answer{white-space:pre-wrap;font-size:14.5px}.answer.wait{color:var(--ink3)}.answer .meta{display:block;margin-top:8px;font-size:11px;color:var(--ink3)}
.dots:after{content:"";animation:d 1.2s infinite}@keyframes d{0%{content:""}33%{content:"."}66%{content:".."}100%{content:"..."}}
.selbtn{position:fixed;z-index:20;background:var(--red);color:#fff;border:0;border-radius:18px;padding:6px 12px;font-weight:700;box-shadow:0 6px 18px rgba(0,0,0,.2)}
.side a{color:var(--red);cursor:pointer}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:16px 0}
.stats div{padding:14px 16px;border-right:1px solid var(--line)}.stats div:last-child{border:0}.stats b{display:block;font-size:24px}
table.rep{border-collapse:collapse;width:100%;font-size:14px}table.rep td,table.rep th{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left}
.foot{position:fixed;left:0;bottom:0;width:270px;padding:10px 16px;background:var(--panel);border-top:1px solid var(--line);font-size:11px;color:var(--ink3)}
.foot img{height:20px;display:block;margin-bottom:3px}
@media(max-width:1000px){.reader{grid-template-columns:1fr}.rail,.foot{display:none}.side{border:0;border-top:1px solid var(--line)}.bookcard{grid-template-columns:1fr}}
</style></head><body>
<header class="top"><img class="mark" src="assets/zprox_mark.png" alt=""><b>EduVerse</b><span class="crumbs" id="crumbs"></span>
<span class="sp"><button class="btn" id="rep">Conversion report</button><button class="btn" id="theme">Dark</button></span></header>
<main id="app"></main>
<script>
const D = __DATA__; const B = D.book; const R = D.report;
const $ = s => document.querySelector(s); const app = $('#app');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let theme = 'light'; $('#theme').onclick = () => { theme = theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; $('#theme').textContent = theme === 'dark' ? 'Light' : 'Dark' };
$('#rep').onclick = () => go('#report');
const go = h => { location.hash = h }; addEventListener('hashchange', route);
function crumbs(parts) { $('#crumbs').innerHTML = parts.map(([l, h]) => h ? `<span>/</span><a onclick="go('${h}')">${esc(l)}</a>` : `<span>/</span><span>${esc(l)}</span>`).join('') }

function home() {
  crumbs([['My books']]);
  const b = B.book, n = B.chapters.length;
  app.innerHTML = `<div class="wrap"><h1>My books</h1><p class="muted">Converted from ${esc(b.source_file)}</p>
  <div class="bookcard" style="cursor:pointer" onclick="go('#book')">
    <div class="cover"><small>${esc(b.board)}</small><div><div class="cls">${esc(b.class)}</div><div class="subj">${esc(b.subject)}</div></div><small>${esc(b.edition)}</small></div>
    <div><h1>${esc(b.title)}</h1><div class="muted">${esc(b.board)}${b.publisher ? ', ' + esc(b.publisher) : ''}</div>
      <div class="facts"><div><b>${B.toc.length || n}</b>units in the index</div><div><b>${n}</b>units in this file</div><div><b>${R.figures.kept}</b>figures</div><div><b>${Object.values(R.keywords).reduce((a, k) => a + k.count, 0)}</b>important words</div></div>
      <button class="btn primary">Open book</button></div></div></div>`;
}

function book() {
  crumbs([[B.book.title]]);
  const have = Object.fromEntries(B.chapters.map(c => [c.number, c]));
  const rows = (B.toc.length ? B.toc : B.chapters.map(c => ({ unit: c.number, title: c.title, page: c.page_start, available: true }))).map(t => {
    const c = have[t.unit];
    const st = c ? (c.partial ? '<span class="tag warn">Partly in file</span>' : '<span class="tag ok">Ready</span>') : '<span class="tag">Not in this file</span>';
    return `<div class="row ${c ? 'on' : 'off'}" ${c ? `onclick="go('#ch/${c.number}')"` : ''}><span class="n">${t.unit ?? ''}</span><span>${esc(t.title)}</span><span class="muted">${t.page ?? ''}</span><span class="muted">${esc(t.month || '')}</span>${st}</div>`
  }).join('');
  app.innerHTML = `<div class="wrap"><h1>${esc(B.book.title)}</h1><p class="muted">Index built from the book's own table of contents. Pick a unit to read.</p>
  <div class="toc"><div class="row head"><span>Unit</span><span>Title</span><span>Page</span><span>Month</span><span>Status</span></div>${rows}</div></div>`;
}

function marked(text, marks) {
  if (!marks || !marks.length) return esc(text);
  let out = '', at = 0;
  for (const [s, e, id] of marks) { out += esc(text.slice(at, s)) + `<span class="kw" role="button" tabindex="0" data-k="${id}">${esc(text.slice(s, e))}</span>`; at = e }
  return out + esc(text.slice(at));
}
function katexHTML(l) { try { return katex.renderToString(l, { displayMode: true, throwOnError: false }) } catch { return esc(l) } }
function block(b) {
  const a = `id="${b.id}" data-sec="${b.section}"`;
  switch (b.type) {
    case 'heading': return b.level === 3 ? `<h3 class="sec" ${a}><span class="n">${b.number}</span>${esc(b.text)}</h3>` : `<h2 class="sec" ${a}>${b.number ? `<span class="n">${b.number}</span>` : ''}${esc(b.text)}</h2>`;
    case 'subheading': return `<p ${a}><b>${esc(b.text)}</b></p>`;
    case 'paragraph': return `<p ${a}>${marked(b.text, b.marks)}${(b.math || []).map(katexHTML).join('')}</p>`;
    case 'list': { const t = b.ordered ? 'ol' : 'ul'; return `<${t} ${a}>${b.items.map(i => `<li>${marked(i.text, i.marks)}</li>`).join('')}</${t}>` }
    case 'equation': return `<div class="eq" ${a}>${b.latex.map(katexHTML).join('')}</div>`;
    case 'figure': return `<figure ${a}><img src="${b.image}" alt="${esc(b.desc?.summary || b.caption)}" loading="lazy">${b.caption || b.number ? `<figcaption>${b.number ? `<b>Figure ${b.number}</b> ` : ''}${esc(b.caption)}</figcaption>` : ''}</figure>`;
    case 'table': return `<div class="tbl" ${a}>${b.caption || b.number ? `<div class="tcap"><b>${b.label || 'Table'} ${b.number}</b> ${esc(b.caption)}</div>` : ''}<table>${b.rows.map((r, i) => `<tr>${r.map(c => i === 0 && b.header ? `<th>${esc(c)}</th>` : `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table></div>`;
    case 'marker': return `<span class="marker" ${a}>${esc(b.text)}</span>`;
    case 'box': return `<div class="box ${b.kind}" ${a}><div class="bt">${esc(b.title)}</div>${b.children.map(block).join('')}</div>`;
  }
  return '';
}

let CUR = null;
function chapter(n) {
  const c = B.chapters.find(x => x.number === +n); if (!c) return book();
  CUR = c; crumbs([[B.book.title, '#book'], [`Unit ${c.number} ${c.title}`]]);
  const secs = c.sections.filter(s => s.id.endsWith('-intro') ? c.blocks.some(b => b.section === s.id) : true);
  const tail = s => !s.number && !s.id.endsWith('-intro');
  let rail = '', sepDone = false;
  for (const s of secs) {
    if (tail(s) && !sepDone) { rail += '<div class="sep"></div>'; sepDone = true }
    rail += `<a class="l${s.level}" data-go="${s.id}">${s.number ? `<span class="num">${s.number}</span>` : ''}${esc(s.title)}</a>`;
  }
  app.innerHTML = `<div class="reader"><nav class="rail"><div class="unit">Unit ${c.number}</div><h3>${esc(c.title)}</h3>${rail}</nav>
  <article class="page" id="page"><div class="inner"><div class="chap-head"><span class="u">Unit ${c.number}</span><h1>${esc(c.title)}</h1>
  <span class="muted">Book pages ${c.page_start} to ${c.page_end}${c.partial ? '. Only part of this unit is in the source file.' : ''}</span></div>${c.blocks.map(block).join('')}</div></article>
  <aside class="side" id="side"><div class="empty"><b>Tap a highlighted word</b><br>or select any words and press Explain.<br><br>${c.keywords.length} important words in this unit.</div></aside></div>
  <div class="foot"><img src="assets/zprox_logo_${theme === 'dark' ? 'dark' : 'light'}.png" alt="zPROx.AI">Automate everything effortlessly</div>`;
  const page = $('#page');
  document.querySelectorAll('.rail a').forEach(el => el.onclick = () => { const t = page.querySelector(`[data-sec="${el.dataset.go}"]`); if (t) t.scrollIntoView() });
  page.onkeydown = e => { const k = e.target.closest('.kw'); if (k && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); explain(k.dataset.k, k) } };
  page.onclick = e => { const k = e.target.closest('.kw'); if (k) explain(k.dataset.k, k); if (e.target.matches('figure img')) e.target.classList.toggle('big') };
  let sb = null;
  page.onmouseup = () => setTimeout(() => {
    sb?.remove(); sb = null;
    const sel = getSelection(); const txt = sel.toString().trim();
    if (!txt || txt.length < 2 || txt.length > 60 || txt.split(/\s+/).length > 6) return;
    const r = sel.getRangeAt(0).getBoundingClientRect(); const para = sel.anchorNode?.parentElement?.closest('p,li')?.textContent || '';
    sb = document.createElement('button'); sb.className = 'selbtn'; sb.textContent = 'Explain'; sb.style.left = r.left + 'px'; sb.style.top = (r.bottom + 6) + 'px';
    sb.onmousedown = e => { e.preventDefault(); explainText(txt, para); sb.remove(); sb = null; sel.removeAllRanges() };
    document.body.appendChild(sb);
  }, 0);
  page.addEventListener('scroll', () => { sb?.remove(); sb = null });
  const links = [...document.querySelectorAll('.rail a')];
  page.onscroll = () => {
    const top = page.getBoundingClientRect().top + 80; let cur = null;
    for (const el of page.querySelectorAll('[data-sec]')) { if (el.getBoundingClientRect().top < top) cur = el.dataset.sec; else break }
    links.forEach(l => l.classList.toggle('cur', l.dataset.go === cur));
  };
  page.onscroll();
}

function allFigures(c) { const out = []; const w = bs => bs.forEach(b => { if (b.type === 'figure') out.push(b); if (b.type === 'box') w(b.children) }); w(c.blocks); return out }
const DEPTHS = [['exam', 'Exam'], ['concept_clarity', 'Concept clarity'], ['curiosity', 'Curiosity'], ['research', 'Research']];
let DEPTH = 'concept_clarity'; const CACHE = {}; let LLM = null;
if (location.protocol.startsWith('http')) fetch('explain/config').then(r => r.ok ? r.json() : null).then(c => LLM = c).catch(() => {});
async function ask(req) {
  const box = document.getElementById('answer'); if (!box) return;
  const key = req.term + '|' + req.depth + '|' + req.paragraph.slice(0, 60);
  if (!location.protocol.startsWith('http')) { box.className = 'answer wait'; box.textContent = 'Live explanations need a model. Start the reader with: python -m eduverse_convert.serve <output folder> --llm ollama'; return }
  if (CACHE[key]) return show(CACHE[key]);
  box.className = 'answer wait'; box.innerHTML = `Explaining ${esc(req.term)}<span class="dots"></span>`;
  try {
    const r = await fetch('explain', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) });
    const j = await r.json(); if (j.error) throw new Error(j.error);
    CACHE[key] = j; show(j);
  } catch (e) { box.className = 'answer wait'; box.textContent = e.message }
  function show(j) { const b = document.getElementById('answer'); if (!b) return; b.className = 'answer'; b.innerHTML = esc(j.text) + `<span class="meta">${esc(j.provider)} ${esc(j.model)}, ${j.seconds}s</span>` }
}
function figText(f) { return [f.number ? 'Figure ' + f.number : '', f.caption, f.desc?.summary].filter(Boolean).join(': ') }
const SIG = { glossary: 'In the glossary', definition: 'Defined in the text', heading: 'Topic heading', unit_law: 'Unit, law or instrument', quoted: 'Marked in the text', caption: 'Figure title', points: 'In points to remember', exercises: 'Asked in exercises', frequent: 'Used often', llm: 'Added by AI' };
function explain(id, el) {
  document.querySelectorAll('.kw.sel').forEach(x => x.classList.remove('sel')); document.querySelectorAll(`.kw[data-k="${id}"]`).forEach(x => x.classList.add('sel'));
  const t = CUR.keywords.find(k => k.id === id); if (!t) return;
  const figs = allFigures(CUR).filter(f => ((f.caption || '') + ' ' + (f.desc?.summary || '') + ' ' + (f.desc?.parts || []).join(' ')).toLowerCase().includes(t.key)).slice(0, 2);
  const para = el?.closest('p,li')?.textContent || '';
  $('#side').innerHTML = `<h2>${esc(t.term)}</h2><div class="sig">${t.prerequisite ? '<span class="pre">Learnt in an earlier class</span>' : ''}${t.signals.map(s => `<span>${SIG[s] || s}</span>`).join('')}</div>
   <div class="card"><div class="h">What the book says</div>${esc(t.definition || 'The book uses this word without defining it.')}</div>
   <div class="card"><div class="h">You are reading</div><span class="muted">${esc(para.slice(0, 320))}${para.length > 320 ? '...' : ''}</span></div>
   ${figs.map(f => `<div class="card"><div class="h">${f.number ? 'Figure ' + f.number : 'Related figure'}</div><img src="${f.image}" alt=""><div class="muted" style="font-size:13px">${esc((f.desc?.summary || f.caption).slice(0, 260))}</div></div>`).join('')}
   <div class="card ai"><div class="h">AI explanation</div><div class="depths">${DEPTHS.map(([k, l]) => `<button data-d="${k}" class="${k === DEPTH ? 'on' : ''}">${l}</button>`).join('')}</div><div class="answer" id="answer"></div></div>
   ${t.first_block ? `<a onclick="document.getElementById('${t.first_block}').scrollIntoView()">Jump to first use in this unit</a>` : ''}`;
  const req = () => ({ term: t.term, depth: DEPTH, paragraph: para, definition: t.definition || '', figures: figs.map(figText), chapter: CUR.title,
                       book: { class: B.book.class, subject: B.book.subject, board: B.book.board } });
  document.querySelectorAll('.depths button').forEach(b => b.onclick = () => { DEPTH = b.dataset.d; document.querySelectorAll('.depths button').forEach(x => x.classList.toggle('on', x === b)); ask(req()) });
  ask(req());
}
function explainText(text, para) {
  const key = text.toLowerCase();
  const kw = CUR.keywords.find(k => k.key === key);
  if (kw) { const el = [...document.querySelectorAll('.kw')].find(x => x.dataset.k === kw.id); return explain(kw.id, el) }
  const fake = { id: 'sel', term: text, key, definition: '', signals: [], prerequisite: false, first_block: null };
  CUR.keywords.push(fake); const pEl = { closest: () => ({ textContent: para }) }; explain('sel', pEl); CUR.keywords.pop();
}

function report() {
  crumbs([['Conversion report']]);
  const kw = Object.entries(R.keywords).map(([n, k]) => `<tr><td>Unit ${n}</td><td>${esc(B.chapters.find(c => c.number == n)?.title)}</td><td>${k.count}</td><td>${k.highlights}</td></tr>`).join('');
  const led = Object.entries(R.ledger).sort((a, b) => b[1] - a[1]).map(([w, c]) => `<tr><td>${esc(w)}</td><td>${c}</td></tr>`).join('');
  const rev = R.needs_review.map(l => `<tr><td>${l.page}</td><td>${esc(l.what)}</td><td class="muted">${esc(l.text)}</td></tr>`).join('');
  const ev = Object.entries(R.identity_evidence).map(([k, v]) => `${k} from ${v}`).join(', ');
  app.innerHTML = `<div class="wrap"><h1>Conversion report</h1><p class="muted">${esc(R.source)}, converted in ${R.seconds}s. AI pass: ${esc(R.llm.provider)}. Identity: ${esc(ev)}.</p>
  <div class="stats"><div><b>${R.chapters_in_file.length}</b>units found${R.chapters_partial.length ? ` (unit ${R.chapters_partial.join(', ')} partial)` : ''}</div><div><b>${R.sections}</b>numbered topics</div><div><b>${R.figures.kept}</b>figures, ${R.figures.with_caption} captioned</div><div><b>${R.blocks.table}</b> tables, <b style="display:inline">${R.blocks.equation}</b> equations</div></div>
  <h3>Important words</h3><table class="rep"><tr><th>Unit</th><th>Title</th><th>Words</th><th>Highlights</th></tr>${kw}</table>
  <h3>What was removed or changed, and why</h3><table class="rep"><tr><th>Reason</th><th>Count</th></tr>${led}</table>
  <h3>For the reviewer (${R.needs_review.length})</h3><table class="rep"><tr><th>Page</th><th>Issue</th><th>Text</th></tr>${rev}</table></div>`;
}

function route() {
  const h = location.hash.slice(1);
  if (h.startsWith('ch/')) chapter(h.slice(3)); else if (h === 'book') book(); else if (h === 'report') report(); else home();
}
route();
</script></body></html>"""
