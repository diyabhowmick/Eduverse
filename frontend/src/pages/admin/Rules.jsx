import { useEffect, useState } from 'react'
import { api, day } from '../../api'
import { useLoad, Page, Field, Switch, useToast, Icon } from '../../ui'

const DEPTHS = [['exam', 'Exam', 'Short, exam focused answers'], ['concept_clarity', 'Concept clarity', 'Plain explanation with an example'], ['curiosity', 'Curiosity', 'The why and real world uses'], ['research', 'Research', 'First principles and links to higher classes']]

export default function Rules() {
  const { data } = useLoad('/api/school/rules'); const { data: classes } = useLoad('/api/school/classes')
  const [v, setV] = useState(null); const toast = useToast()
  useEffect(() => { data && setV(structuredClone(data)) }, [data])
  if (!v) return <Page title="Learning rules" />
  const tog = k => setV(x => ({ ...x, allowed_depths: x.allowed_depths.includes(k) ? x.allowed_depths.filter(d => d !== k) : [...x.allowed_depths, k] }))
  const setW = (i, k, val) => setV(x => ({ ...x, exam_windows: x.exam_windows.map((w, j) => j === i ? { ...w, [k]: val } : w) }))
  async function save() { try { setV(await api('/api/school/rules', { method: 'PUT', body: v })); toast('Learning rules saved') } catch (e) { toast(e.message, true) } }
  return (
    <Page title="Learning rules" sub="How the AI explains things to your students" actions={<button className="btn primary" onClick={save}>Save rules</button>}>
      <div className="stack">
        <div className="row">
          <div className="card"><div className="card-h"><h3>Explanation depths students can pick</h3></div>
            <div className="card-b">{DEPTHS.map(([k, l, d]) => <label key={k} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '9px 0', borderBottom: '1px solid var(--line)' }}>
              <Switch checked={v.allowed_depths.includes(k)} onChange={() => tog(k)} label={l} /><span><b>{l}</b><div className="muted" style={{ fontSize: 13 }}>{d}</div></span></label>)}</div></div>
          <div className="card"><div className="card-h"><h3>Daily limit</h3></div>
            <div className="card-b"><Field label="Explanations per student per day" hint={`EduVerse allows up to ${v.platform_cap}`}><input className="input" type="number" min="0" max={v.platform_cap} value={v.daily_explanations} onChange={e => setV({ ...v, daily_explanations: +e.target.value })} /></Field></div></div>
        </div>
        <div className="card"><div className="card-h"><h3>Exam mode windows</h3><span className="sub">During a window, chosen classes only get exam depth answers</span>
          <button className="btn sm right" onClick={() => setV(x => ({ ...x, exam_windows: [...x.exam_windows, { name: '', start: '', end: '', class_ids: [] }] }))}><Icon n="plus" s={14} />Add window</button></div>
          <div className="card-b stack">
            {v.exam_windows.map((w, i) => <div key={i} style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 14 }} className="stack">
              <div className="grid3"><Field label="Name"><input className="input" placeholder="Quarterly exams" value={w.name} onChange={e => setW(i, 'name', e.target.value)} /></Field>
                <Field label="Starts"><input className="input" type="date" value={w.start} onChange={e => setW(i, 'start', e.target.value)} /></Field>
                <Field label="Ends"><input className="input" type="date" value={w.end} onChange={e => setW(i, 'end', e.target.value)} /></Field></div>
              <Field label="Classes" hint="None selected means every class"><div className="chips">{classes?.map(c => <button key={c.id} className={'chip' + (w.class_ids.includes(c.id) ? ' on' : '')}
                onClick={() => setW(i, 'class_ids', w.class_ids.includes(c.id) ? w.class_ids.filter(x => x !== c.id) : [...w.class_ids, c.id])}>{c.label}</button>)}</div></Field>
              <div><button className="btn ghost sm" style={{ color: 'var(--red)' }} onClick={() => setV(x => ({ ...x, exam_windows: x.exam_windows.filter((_, j) => j !== i) }))}>Remove window</button>
                {w.start && w.end && <span className="muted" style={{ marginLeft: 8 }}>{day(w.start)} to {day(w.end)}</span>}</div>
            </div>)}
            {!v.exam_windows.length && <div className="empty">No exam windows set</div>}
          </div></div>
      </div>
    </Page>
  )
}
