"""The upload page served at /. One file, no build step, no framework."""

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EduVerse book to DOCX</title>
<style>
:root{--red:#E0212F;--ink:#1a1a1a;--mut:#6b6b6b;--line:#e3e1da;--bg:#faf9f6;--ok:#1d7a4c}
*{box-sizing:border-box}
body{font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:var(--bg);
margin:0;padding:32px 24px;line-height:1.5}
.wrap{max-width:980px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:24px}
.panel{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:20px}
#drop{border:2px dashed var(--line);border-radius:10px;padding:36px 20px;text-align:center;
cursor:pointer;transition:.15s;background:#fff}
#drop.hot{border-color:var(--red);background:#fff7f7}
#drop b{display:block;font-size:16px;margin-bottom:4px}
#drop span{color:var(--mut);font-size:13px}
.opts{display:flex;flex-wrap:wrap;gap:16px;margin:18px 0 8px;font-size:13px}
.opts label{display:flex;align-items:center;gap:6px;cursor:pointer}
button{background:var(--red);color:#fff;border:0;border-radius:6px;padding:10px 20px;
font-size:14px;cursor:pointer}
button:disabled{background:#c9c7c0;cursor:default}
button.ghost{background:#fff;color:var(--ink);border:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px}
.bar{height:6px;background:#eee;border-radius:3px;overflow:hidden;min-width:110px}
.bar>i{display:block;height:100%;background:var(--red);width:0;transition:width .3s}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;background:#f1efe8;color:var(--mut)}
.pill.ready{background:#e6f5ec;color:var(--ok)}
.pill.failed{background:#fdecec;color:var(--red)}
.pill.running{background:#fff3d9;color:#8a5a00}
a{color:var(--red);text-decoration:none;font-size:12px;margin-right:10px}
a:hover{text-decoration:underline}
.small{font-size:12px;color:var(--mut)}
.err{color:var(--red);font-size:13px;margin-top:10px;white-space:pre-wrap}
code{background:#f1efe8;padding:1px 5px;border-radius:3px;font-size:12px}
</style></head><body><div class="wrap">

<h1>EduVerse book to DOCX</h1>
<div class="sub">A printed book in, a digital book out. Nothing is declared, the
pipeline detects it. <span id="health"></span></div>

<div class="panel">
  <div id="drop">
    <b>Drop a PDF or Word file here</b>
    <span>or click to choose. Up to 200 MB.</span>
    <input id="file" type="file" accept=".pdf,.docx,.dotx" hidden>
  </div>
  <div class="opts">
    <label><input type="checkbox" id="describe" checked> Describe figures</label>
    <label><input type="checkbox" id="split_composites" checked> Split composite figures</label>
    <label><input type="checkbox" id="page_markers" checked> Page markers</label>
    <label><input type="checkbox" id="page_lock"> One docx page per printed page</label>
    <label><input type="checkbox" id="layout_docx"> Also write layout.docx</label>
    <label>DPI <input type="number" id="dpi" value="300" min="150" max="600" step="50" style="width:70px"></label>
  </div>
  <button id="go" disabled>Convert</button>
  <span id="picked" class="small"></span>
  <div id="err" class="err"></div>
</div>

<div class="panel">
  <table><thead><tr>
    <th>File</th><th>Status</th><th>Progress</th><th>Result</th><th>Downloads</th><th></th>
  </tr></thead><tbody id="rows">
    <tr><td colspan="6" class="small">Nothing converted yet.</td></tr>
  </tbody></table>
</div>

<script>
const $ = s => document.querySelector(s);
let picked = null;

fetch('/api/health').then(r=>r.json()).then(h=>{
  const o = h.ollama || {};
  $('#health').innerHTML = o.offline ? 'Running offline.' :
    (o.ok ? 'Models ready: <code>'+h.models.ocr+'</code> <code>'+h.models.vlm+'</code>'
          : '<span style="color:#E0212F">Ollama not reachable'+
            (o.missing&&o.missing.length?', missing '+o.missing.join(', '):'')+'</span>');
}).catch(()=>{});

const drop = $('#drop');
drop.onclick = () => $('#file').click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('hot'); };
drop.ondragleave = () => drop.classList.remove('hot');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('hot');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); };
$('#file').onchange = e => { if (e.target.files[0]) setFile(e.target.files[0]); };

function setFile(f){
  picked = f;
  $('#picked').textContent = f.name + '  ' + (f.size/1048576).toFixed(1) + ' MB';
  $('#go').disabled = false;
  $('#err').textContent = '';
}

$('#go').onclick = async () => {
  if (!picked) return;
  $('#go').disabled = true;
  const fd = new FormData();
  fd.append('file', picked);
  for (const k of ['page_lock','layout_docx','page_markers','describe','split_composites'])
    fd.append(k, $('#'+k).checked ? 'true' : 'false');
  fd.append('dpi', $('#dpi').value);
  try {
    const r = await fetch('/api/jobs', {method:'POST', body:fd});
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'upload failed');
    picked = null; $('#picked').textContent = ''; $('#file').value = '';
    poll();
  } catch (e) {
    $('#err').textContent = e.message;
    $('#go').disabled = false;
  }
};

function pill(s){ return '<span class="pill '+s+'">'+s+'</span>'; }

function result(j){
  if (j.status === 'failed') return '<span class="small" style="color:#E0212F">'+
    (j.error||'failed').split('\n').slice(-2).join(' ').slice(0,180)+'</span>';
  if (j.status !== 'ready') return '<span class="small">'+(j.stage||'')+'</span>';
  const s = j.summary || {}, l = s.ledger || {}, d = s.detected || {}, c = s.counts || {};
  const bits = Object.keys(c).sort().map(k => k+' '+c[k]).join(', ');
  return '<div class="small">'+s.pages+' pages, '+bits+
    '<br>ledger '+(l.balanced ? 'balanced' : '<b style="color:#E0212F">OFF BY '+
      (l.detected-l.emitted-l.dropped)+'</b>')+
    ', gate '+(s.gate_passed ? '<b style="color:#1d7a4c">pass</b>'
                             : '<b style="color:#E0212F">fail</b>')+
    (s.coverage ? '<br>readable '+(s.coverage.coverage*100).toFixed(1)+'% ('+
      s.coverage.opaque+' opaque), '+s.coverage.figures_regenerable+'/'+
      s.coverage.figures+' figures regenerable' : '')+
    (d.board||d.grade||d.subject ? '<br>detected '+[d.board,d.grade&&('class '+d.grade),d.subject]
      .filter(Boolean).join(', ') : '')+'</div>';
}

function links(j){
  if (j.status !== 'ready') return '';
  const base = '/api/jobs/'+j.id;
  let out = (j.files||[]).filter(f=>f!=='eduverse_base.docx')
    .map(f => '<a href="'+base+'/files/'+f+'">'+f+'</a>').join('');
  out += '<a href="'+base+'/digital" target="_blank">open digital book</a>';
  out += '<a href="'+base+'/report" target="_blank">open report</a>';
  return out;
}

async function poll(){
  const r = await fetch('/api/jobs');
  const d = await r.json();
  const rows = $('#rows');
  if (!d.jobs.length){
    rows.innerHTML = '<tr><td colspan="6" class="small">Nothing converted yet.</td></tr>';
  } else {
    rows.innerHTML = d.jobs.map(j => '<tr>'+
      '<td>'+j.filename+'<div class="small">'+j.elapsed_s+'s</div></td>'+
      '<td>'+pill(j.status)+'</td>'+
      '<td><div class="bar"><i style="width:'+j.percent+'%"></i></div>'+
        '<div class="small">'+(j.total? j.stage+' '+j.done+'/'+j.total : '')+'</div></td>'+
      '<td>'+result(j)+'</td>'+
      '<td>'+links(j)+'</td>'+
      '<td><button class="ghost" onclick="del(\''+j.id+'\')">remove</button></td>'+
    '</tr>').join('');
  }
  $('#go').disabled = !picked;
  if (d.jobs.some(j => j.status === 'queued' || j.status === 'running'))
    setTimeout(poll, 1200);
}

async function del(id){
  await fetch('/api/jobs/'+id, {method:'DELETE'});
  poll();
}
poll();
</script>
</div></body></html>
"""
