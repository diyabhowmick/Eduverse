import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { useLoad, Page, Field, useToast } from '../../ui'

export default function Profile() {
  const { data } = useLoad('/api/school/profile'); const [v, setV] = useState(null); const toast = useToast(); const ref = useRef()
  useEffect(() => { data && setV(data) }, [data])
  if (!v) return <Page title="School profile" />
  const set = k => ({ value: v[k] || '', onChange: e => setV({ ...v, [k]: e.target.value }) })
  function pick(e) {
    const f = e.target.files[0]; if (!f) return
    if (f.size > 300 * 1024) return toast('Logo must be under 300 KB', true)
    const r = new FileReader(); r.onload = () => setV(x => ({ ...x, logo: r.result })); r.readAsDataURL(f)
  }
  async function save() { try { setV(await api('/api/school/profile', { method: 'PUT', body: { name: v.name, city: v.city, contact_name: v.contact_name, contact_email: v.contact_email, academic_year: v.academic_year, logo: v.logo } })); toast('Profile saved') } catch (e) { toast(e.message, true) } }
  return (
    <Page title="School profile" sub="How your school appears to students" actions={<button className="btn primary" onClick={save}>Save profile</button>}>
      <div className="row">
        <div className="card" style={{ flex: 2 }}><div className="card-b stack">
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>{v.logo ? <img className="logo-prev" src={v.logo} alt="School logo" /> : <div className="logo-prev" style={{ display: 'grid', placeItems: 'center', color: 'var(--ink-3)' }}>Logo</div>}
            <div><button className="btn sm" onClick={() => ref.current.click()}>Upload logo</button>{v.logo && <button className="btn ghost sm" onClick={() => setV({ ...v, logo: '' })}>Remove</button>}
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>PNG, JPG or SVG, under 300 KB</div></div>
            <input ref={ref} hidden type="file" accept="image/png,image/jpeg,image/svg+xml" onChange={pick} /></div>
          <Field label="School name"><input className="input" {...set('name')} /></Field>
          <div className="grid2"><Field label="City"><input className="input" {...set('city')} /></Field><Field label="Academic year"><input className="input" placeholder="2026-27" {...set('academic_year')} /></Field>
            <Field label="Contact person"><input className="input" {...set('contact_name')} /></Field><Field label="Contact email"><input className="input" type="email" {...set('contact_email')} /></Field></div>
        </div></div>
        <div className="card"><div className="card-h"><h3>Set by EduVerse</h3></div><div className="card-b"><dl className="kv">
          <dt>Board</dt><dd>{v.board}</dd><dt>Medium</dt><dd>{v.medium}</dd><dt>Plan</dt><dd>{v.plan}</dd><dt>Seats</dt><dd>{v.seats}</dd></dl>
          <p className="muted" style={{ fontSize: 13 }}>To change these, send a request.</p></div></div>
      </div>
    </Page>
  )
}
