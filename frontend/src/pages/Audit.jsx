import { useState } from 'react'
import { when, actionLabel } from '../api'
import { useLoad, Page, Tag } from '../ui'
import { api } from '../api'

const AREAS = [['', 'Everything'], ['admin', 'Admins'], ['school', 'Schools'], ['plan', 'Plans'], ['discount', 'Discounts'], ['book', 'Books'], ['job', 'Processing'], ['settings', 'Settings'], ['login', 'Sign ins']]

export default function Audit() {
  const [area, setArea] = useState(''); const [q, setQ] = useState('')
  const { data } = useLoad(`/api/audit?action=${area}&q=${encodeURIComponent(q)}`, [area, q])
  const [check, setCheck] = useState(null); const [busy, setBusy] = useState(false)
  async function verify() { setBusy(true); try { setCheck(await api('/api/audit/verify')) } catch (e) { setCheck({ error: e.message }) } finally { setBusy(false) } }
  return (
    <Page title="Audit log" sub="Every change made on the platform, with who made it">
      <div className="toolbar">
        <select className="input" style={{ maxWidth: 200 }} value={area} onChange={e => setArea(e.target.value)}>{AREAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <input className="input" placeholder="Filter by person" value={q} onChange={e => setQ(e.target.value)} />
        <button className="btn" disabled={busy} onClick={verify} title="Each entry carries the fingerprint of the one before it, so an edited or deleted entry shows up here">{busy ? 'Checking' : 'Check the log has not been changed'}</button>
      </div>
      {check && <div className="note" role="status">{check.error ? check.error
        : check.intact ? <><Tag s="ok">Intact</Tag> All {check.checked} entries are as they were written.</>
          : <><Tag s="bad">Changed</Tag> Entry {String(check.first_break?.id ?? check.first_break)} or one just before it was edited or deleted after it was written. {check.checked} entries checked.</>}</div>}
      <div className="card">
        <table className="t"><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
          <tbody>{data?.map(a => <tr key={a.id}><td className="muted" style={{ whiteSpace: 'nowrap' }}>{when(a.at)}</td><td>{a.actor}<div className="muted">{a.role.replace('_', ' ')}</div></td>
            <td><b>{actionLabel(a.action)}</b><div className="muted mono">{a.action}</div></td><td className="muted">{a.target_type} {a.target_id}</td>
            <td className="muted mono">{Object.entries(a.detail || {}).map(([k, v]) => `${k}: ${v}`).join(', ')}</td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">Nothing recorded for this filter</div>}
      </div>
    </Page>
  )
}
