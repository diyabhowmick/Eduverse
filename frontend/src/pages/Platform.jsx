import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLoad, Page, Field, Switch, useToast } from '../ui'

const FEAT = { student_store: 'Store in the student app', upcoming_books: 'Show upcoming books', explain_panel: 'Explain panel in the reader', notebook: 'Student notebook',
  practice_questions: 'Practice questions', knowledge_graph: 'Knowledge graph', school_bulk_upload: 'Bulk student upload for schools', dark_mode: 'Dark mode' }
const PERM = { manage_admins: 'Manage admins', manage_pricing: 'Manage pricing', manage_schools: 'Manage schools', manage_catalogue: 'Manage catalogue', run_processing: 'Run processing',
  review_books: 'Review and approve books', manage_students: 'Manage students', assign_books: 'Assign books to classes', view_school_analytics: 'School analytics',
  view_platform_analytics: 'Platform analytics', read_books: 'Read books' }
const ROLES = [['super_admin', 'Super Admin'], ['admin', 'School Admin'], ['reviewer', 'Reviewer'], ['student', 'Student']]

function useSetting(key) {
  const { data } = useLoad('/api/settings/' + key); const [v, setV] = useState(null); const toast = useToast()
  useEffect(() => { data && setV(structuredClone(data)) }, [data])
  const save = async () => { try { setV(await api('/api/settings/' + key, { method: 'PUT', body: v })); toast('Saved') } catch (e) { toast(e.message, true) } }
  return [v, setV, save]
}

export default function Platform() {
  const [b, setB, saveB] = useSetting('branding'); const [f, setF, saveF] = useSetting('features'); const [p, setP, saveP] = useSetting('permissions')
  const toggle = (perm, role) => setP(x => ({ ...x, [perm]: x[perm].includes(role) ? x[perm].filter(r => r !== role) : [...x[perm], role] }))
  return (
    <Page title="Platform settings" sub="Branding, features and what each role can do">
      <div className="stack">
        {b && <div className="card"><div className="card-h"><h3>Branding</h3><button className="btn primary sm right" onClick={saveB}>Save branding</button></div>
          <div className="card-b grid3">
            {[['product_name', 'Product name'], ['company_name', 'Company name'], ['tagline', 'Tagline'], ['font', 'Font'], ['support_email', 'Support email']].map(([k, l]) =>
              <Field key={k} label={l}><input className="input" value={b[k]} onChange={e => setB({ ...b, [k]: e.target.value })} /></Field>)}
            <Field label="Accent colour"><div style={{ display: 'flex', gap: 8 }}><input type="color" value={b.accent} onChange={e => setB({ ...b, accent: e.target.value })} style={{ width: 44, height: 36, border: 0, background: 'none' }} /><input className="input mono" value={b.accent} onChange={e => setB({ ...b, accent: e.target.value })} /></div></Field>
          </div></div>}
        <div className="row">
          {f && <div className="card"><div className="card-h"><h3>Features</h3><span className="sub">On for every school</span><button className="btn primary sm right" onClick={saveF}>Save features</button></div>
            <div className="card-b">{Object.keys(FEAT).map(k => <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--line)' }}><Switch checked={f[k]} onChange={on => setF({ ...f, [k]: on })} label={FEAT[k]} />{FEAT[k]}</label>)}</div></div>}
          {p && <div className="card" style={{ flex: 1.5 }}><div className="card-h"><h3>Role permissions</h3><button className="btn primary sm right" onClick={saveP}>Save permissions</button></div>
            <table className="t matrix"><thead><tr><th>Permission</th>{ROLES.map(([, l]) => <th key={l}>{l}</th>)}</tr></thead>
              <tbody>{Object.keys(PERM).map(k => <tr key={k}><td>{PERM[k]}</td>{ROLES.map(([r]) => <td key={r}>
                <input type="checkbox" checked={p[k]?.includes(r)} onChange={() => toggle(k, r)} disabled={r === 'super_admin' && k.startsWith('manage_')} aria-label={PERM[k] + ' for ' + r} style={{ accentColor: 'var(--red)', width: 16, height: 16 }} /></td>)}</tr>)}</tbody></table></div>}
        </div>
      </div>
    </Page>
  )
}
