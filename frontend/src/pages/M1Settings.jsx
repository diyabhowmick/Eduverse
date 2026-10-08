import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useLoad, Page, Field, Switch, useToast } from '../ui'

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const show = (v, d) => d === '' ? 'empty' : Array.isArray(d) ? d.join(', ') : typeof d === 'boolean' ? (d ? 'on' : 'off') : String(d)
const STYLE_COLS = ['Font', 'Size (pt)', 'Bold', 'Space before', 'Space after']

function Input({ f, v, onChange, saved }) {
  const val = v[f.name]
  if (f.type === 'bool') return <div className="m1-bool"><Switch checked={val} onChange={onChange} label={f.label} /><span>{val ? 'On' : 'Off'}</span></div>
  if (f.type === 'choice') return <select className="input" value={val} onChange={e => onChange(e.target.value)}>{f.choices.map(c => <option key={c} value={c}>{c}</option>)}</select>
  if (f.type === 'int' || f.type === 'float') return <input className="input" type="number" step={f.type === 'int' ? 1 : 'any'} value={val} onChange={e => onChange(e.target.value === '' ? '' : +e.target.value)} />
  if (f.type === 'list') return <input className="input" value={Array.isArray(val) ? val.join(', ') : val} onChange={e => onChange(e.target.value.split(',').map(s => s.trim()).filter(Boolean))} />
  if (f.secret) return <input className="input" type="password" placeholder={saved === 'saved' ? 'Saved. Type to replace' : 'Paste key'} value={val === 'saved' ? '' : val} onChange={e => onChange(e.target.value || (saved === 'saved' ? 'saved' : ''))} />
  return <input className="input" value={val} onChange={e => onChange(e.target.value)} />
}

function Styles({ val, dflt, onChange }) {
  const set = (name, i, x) => onChange({ ...val, [name]: val[name].map((c, j) => j === i ? x : c) })
  return <div style={{ overflowX: 'auto' }}><table className="table m1-styles"><thead><tr><th>Style</th>{STYLE_COLS.map(c => <th key={c}>{c}</th>)}</tr></thead>
    <tbody>{Object.keys(val).map(n => <tr key={n} className={same(val[n], dflt[n]) ? '' : 'm1-changed'}><td><b>{n}</b></td>
      <td><input className="input" value={val[n][0]} onChange={e => set(n, 0, e.target.value)} /></td>
      <td><input className="input" type="number" step="0.5" value={val[n][1]} onChange={e => set(n, 1, +e.target.value)} /></td>
      <td><Switch checked={val[n][2]} onChange={x => set(n, 2, x)} label="Bold" /></td>
      <td><input className="input" type="number" value={val[n][3]} onChange={e => set(n, 3, +e.target.value)} /></td>
      <td><input className="input" type="number" value={val[n][4]} onChange={e => set(n, 4, +e.target.value)} /></td></tr>)}</tbody></table></div>
}

export default function M1Settings() {
  const { data, setData } = useLoad('/api/pipeline/m1')
  const [v, setV] = useState(null); const [q, setQ] = useState(''); const [open, setOpen] = useState({})
  const [check, setCheck] = useState(null); const [busy, setBusy] = useState(false); const toast = useToast()
  useEffect(() => { data && setV(structuredClone(data.values)) }, [data])
  const byName = useMemo(() => Object.fromEntries((data?.fields || []).map(f => [f.name, f])), [data])
  if (!v) return <Page title="Book extraction (M1)" />
  const visible = f => !f.show_when || v[f.show_when[0]] === f.show_when[1]
  const dirty = !same(v, data.values)
  const changedCount = data.fields.filter(f => !same(v[f.name], f.default) && !(f.secret)).length
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  const run = async (fn, msg) => { try { const r = await fn(); setData(r); msg && toast(msg) } catch (e) { toast(e.message, true) } }
  const save = () => run(() => api('/api/pipeline/m1', { method: 'PUT', body: v }), 'M1 settings saved. New uploads use them.')
  const resetAll = () => confirm('Put every M1 setting back to its default? Saved API keys are cleared too.') && run(() => api('/api/pipeline/m1/reset', { method: 'POST', body: {} }), 'All M1 settings back to default')
  const checkModels = async () => { setBusy(true); setCheck(null); try { setCheck(await api('/api/pipeline/m1/check', { method: 'POST', body: v })) } catch (e) { setCheck({ ok: false, error: e.message }) } setBusy(false) }
  const row = f => {
    const changed = !f.secret && !same(v[f.name], f.default)
    const hint = <>{f.help && <span>{f.help} </span>}<span className="m1-def">Default: {show(v[f.name], f.default)}</span>
      {changed && <button className="linkbtn" onClick={() => set(f.name, structuredClone(f.default))}>Reset</button>}</>
    if (f.type === 'styles') return <div key={f.name} style={{ gridColumn: '1 / -1' }}><Field label={f.label} hint={<span className="m1-def">Font, size and spacing of each paragraph style in the flow document</span>}><Styles val={v[f.name]} dflt={f.default} onChange={x => set(f.name, x)} /></Field></div>
    return <div key={f.name} className={'m1-field' + (changed ? ' m1-changed' : '')}><Field label={f.label} hint={hint}><Input f={f} v={v} saved={data.values[f.name]} onChange={x => set(f.name, x)} /></Field></div>
  }
  const model = data.fields.filter(f => f.group === 'Model' && f.common && f.name !== 'provider' && visible(f))
  const common = data.fields.filter(f => f.common && f.group !== 'Model')
  const ql = q.trim().toLowerCase()
  const adv = data.groups.map(g => [g, data.fields.filter(f => f.group === g && !f.common && visible(f) && (!ql || (f.label + ' ' + f.name + ' ' + f.help).toLowerCase().includes(ql)))]).filter(([, fs]) => fs.length)
  return (
    <Page title="Book extraction (M1)" sub="How a printed book (PDF or Word) is read into the flow document. Every setting and default comes from M1 itself."
      actions={<><button className="btn" onClick={resetAll}>Reset all</button><button className="btn primary" disabled={!dirty} onClick={save}>Save changes</button></>}>
      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>Model</h3><span className="sub">Reads scanned pages, describes figures, reads tables and maths</span>
            <button className="btn sm right" disabled={busy} onClick={checkModels}>{busy ? 'Checking' : 'Check model'}</button></div>
          <div className="card-b stack">
            <div className="seg" role="radiogroup">{[['ollama', 'Ollama (local)'], ['openai', 'OpenAI']].map(([k, l]) =>
              <button key={k} className={v.provider === k ? 'on' : ''} onClick={() => set('provider', k)} role="radio" aria-checked={v.provider === k}>{l}</button>)}</div>
            <div className="grid3">{model.map(row)}</div>
            {check && <div className={'note ' + (check.ok ? 'm1-ok' : 'm1-bad')}>
              {check.ok ? <><b>Model ready.</b> {check.offline ? 'Offline test mode: no model is called.' : `${(check.models || []).slice(0, 4).join(', ')} answered and can see images.`}</>
                : <><b>Not ready.</b> {check.error || (check.missing?.length ? `Not installed: ${check.missing.join(', ')}. Run: ollama pull ${check.missing[0]}` : check.vision?.note || check.vision?.error || 'The model did not see the test image')}</>}</div>}
          </div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Common settings</h3><span className="sub">{changedCount ? `${changedCount} changed from default` : 'All at default'}</span></div>
          <div className="card-b grid3">{common.map(row)}</div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Advanced</h3><span className="sub">Every other M1 setting, by area</span>
            <input className="input right" style={{ maxWidth: 260 }} placeholder="Find a setting" value={q} onChange={e => setQ(e.target.value)} /></div>
          <div className="card-b stack">{adv.map(([g, fs]) => {
            const on = open[g] || !!ql; const n = fs.filter(f => !f.secret && !same(v[f.name], f.default)).length
            return <div key={g} className="m1-group"><button className="m1-gh" onClick={() => setOpen(o => ({ ...o, [g]: !o[g] }))} aria-expanded={on}>
              <span>{on ? '▾' : '▸'}</span><b>{g}</b><span className="muted">{fs.length} settings{n ? `, ${n} changed` : ''}</span></button>
              {on && <div className="grid3" style={{ marginTop: 12 }}>{fs.map(row)}</div>}</div>
          })}{!adv.length && <div className="empty">No setting matches</div>}</div>
        </div>
        <div className="note">Changes apply to the next book you upload. Each job keeps a copy of the settings it ran with (Processing, Settings used).</div>
      </div>
    </Page>
  )
}
