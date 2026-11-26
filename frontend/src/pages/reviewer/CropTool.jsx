import { useRef, useState } from 'react'
import { api } from '../../api'
import { Modal, Field } from '../../ui'

/* Crop on the original page.

   Draw a box on the printed page. Replace: the picture becomes exactly that box (a cut-off or too-tight picture).
   Tick the other pieces to join them into it (a figure that came out in pieces). Add: a new picture after the
   block you choose (a missing picture, or the second half of one that should be two). Cut from the uploaded PDF,
   so it is sharp. */
export default function CropTool({ bookId, page, mode, figure, figures = [], blocks = [], onClose, onDone }) {
  const box = useRef(); const [r, setR] = useState(null); const [drag, setDrag] = useState(null)
  const [remove, setRemove] = useState([]); const [after, setAfter] = useState(blocks[blocks.length - 1]?.id || '')
  const [caption, setCaption] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const at = e => {
    const b = box.current.getBoundingClientRect()
    const p = e.touches ? e.touches[0] : e
    return [Math.min(1, Math.max(0, (p.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (p.clientY - b.top) / b.height))]
  }
  const down = e => { e.preventDefault(); const p = at(e); setDrag(p); setR([p[0], p[1], p[0], p[1]]) }
  const moveTo = e => { if (!drag) return; const p = at(e); setR([Math.min(drag[0], p[0]), Math.min(drag[1], p[1]), Math.max(drag[0], p[0]), Math.max(drag[1], p[1])]) }
  const up = () => setDrag(null)
  const ok = r && r[2] - r[0] > 0.02 && r[3] - r[1] > 0.02
  async function save() {
    setBusy(true); setErr('')
    try {
      await api(`/api/review/books/${bookId}/pages/${page}/crop`, { method: 'POST', body: mode === 'replace'
        ? { box: r, mode, block_id: figure.id, remove, caption }
        : { box: r, mode, block_id: after || null, caption } })
      onDone(mode === 'replace' ? (remove.length ? `Picture cropped again, ${remove.length} piece(s) joined into it` : 'Picture cropped again') : 'Picture added')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const others = figures.filter(f => f.id !== figure?.id)
  return <Modal title={mode === 'replace' ? `Crop again on page ${page}` : `Add a picture from page ${page}`} onClose={onClose}
    footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!ok || busy} onClick={save}>{busy ? 'Saving' : mode === 'replace' ? 'Use this crop' : 'Add this picture'}</button></>}>
    <p className="muted" style={{ margin: '0 0 8px' }}>Drag a box round the whole picture on the printed page, labels included.</p>
    <div ref={box} className="crop-page" onMouseDown={down} onMouseMove={moveTo} onMouseUp={up} onMouseLeave={up}
      onTouchStart={down} onTouchMove={moveTo} onTouchEnd={up}>
      <img src={`/api/review/books/${bookId}/pages/${page}/original.png`} alt={`Original page ${page}`} draggable="false" />
      {r && <div className="crop-box" style={{ left: r[0] * 100 + '%', top: r[1] * 100 + '%', width: (r[2] - r[0]) * 100 + '%', height: (r[3] - r[1]) * 100 + '%' }} />}
    </div>
    {mode === 'replace' && others.length > 0 && <Field label="Other pictures on this page that are pieces of this one" hint="Ticked pieces are removed: your box replaces them all">
      <div className="chips">{others.map(f => <label key={f.id} className={'chip' + (remove.includes(f.id) ? ' on' : '')} style={{ cursor: 'pointer' }}>
        <input type="checkbox" style={{ display: 'none' }} checked={remove.includes(f.id)} onChange={e => setRemove(x => e.target.checked ? [...x, f.id] : x.filter(y => y !== f.id))} />
        {f.number ? 'Figure ' + f.number : (f.caption || 'Picture ' + f.id)}</label>)}</div></Field>}
    {mode === 'add' && blocks.length > 0 && <Field label="Put it after">
      <select className="input" value={after} onChange={e => setAfter(e.target.value)}>{blocks.map(b => <option key={b.id} value={b.id}>
        {(b.type === 'figure' ? 'Picture: ' + (b.caption || b.id) : b.type === 'table' ? 'Table' : (b.text || '').slice(0, 70)) || b.type}</option>)}</select></Field>}
    <Field label="Caption (optional)"><input className="input" value={caption} onChange={e => setCaption(e.target.value)} placeholder={figure?.caption || 'Figure 2.3 Parts of a flower'} /></Field>
    {err && <div className="err">{err}</div>}
  </Modal>
}
