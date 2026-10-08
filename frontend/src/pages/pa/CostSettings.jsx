import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, num } from '../../api'
import { useLoad, Page, Switch, useToast } from '../../ui'

/* Cost settings.
   Six knobs, gathered from three different screens. They are not copies — each
   one is read from and written back to the place it already lives, so this
   screen and the M1, M2 and AI screens can never disagree. Everything else on
   those screens is about how a book reads; only these six move the bill. */
const BOOL = ['describe_figures', 'm2_enabled']

export default function CostSettings() {
  const { data, reload } = useLoad('/api/factory/cost-settings')
  const [v, setV] = useState(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  useEffect(() => { if (data) setV({ ...data.values }) }, [data])
  if (!data || !v) return <Page title="Cost settings" />

  const dirty = Object.keys(v).some(k => v[k] !== data.values[k])
  const set = (k, x) => setV(p => ({ ...p, [k]: x }))

  async function save() {
    setBusy(true)
    try {
      const changed = {}
      for (const k of Object.keys(v)) if (v[k] !== data.values[k]) changed[k] = v[k]
      await api('/api/factory/cost-settings', { method: 'PUT', body: changed })
      toast('Cost settings saved'); reload()
    } catch (e) { toast(e.message, true) } finally { setBusy(false) }
  }

  const ex = data.example
  const sc = data.example_scanned

  return (
    <Page title="Cost settings" sub="The handful of settings that actually change what a book costs"
      actions={<>
        {dirty && <button className="btn" onClick={() => setV({ ...data.values })}>Undo</button>}
        <button className="btn primary" disabled={!dirty || busy} onClick={save}>{busy ? 'Saving' : 'Save changes'}</button>
      </>}>

      <p className="headline">
        At these settings a 288 page book costs about <em>${ex.total.toFixed(2)}</em> to make, once.
      </p>

      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>What moves the bill</h3>
            <span className="sub">Each value is stored on its own screen — this is the same setting, not a copy</span></div>
          <table className="t">
            <thead><tr><th style={{ width: '38%' }}>Setting</th><th>What it changes</th><th style={{ width: 150 }}>Value</th><th>Lives on</th></tr></thead>
            <tbody>{data.knobs.map(k => (
              <tr key={k.name}>
                <td><b>{k.label}</b></td>
                <td className="muted">{k.help}</td>
                <td>{BOOL.includes(k.name)
                  ? <Switch checked={!!v[k.name]} onChange={x => set(k.name, x)} label={v[k.name] ? 'On' : 'Off'} />
                  : <input className="input" type="number" value={v[k.name] ?? ''} onChange={e => set(k.name, e.target.value === '' ? '' : +e.target.value)} />}
                </td>
                <td className="muted" style={{ fontSize: 12 }}>{k.screen}</td>
              </tr>))}</tbody>
          </table>
        </div>

        <div className="note">
          <b>Page picture quality is the one to be careful with.</b> It is how large a picture of
          each scanned page the model is sent. Halving it roughly halves what that page costs, but
          small print and subscripts start to be misread — and a misread page is caught by a
          reviewer, which costs more than the saving. 150 is the tested setting.
        </div>

        <div className="card">
          <div className="card-h"><h3>Where the money actually goes</h3>
            <span className="sub">A 288 page book, printed text, 330 figures, 2000 keywords explained ahead of time</span></div>
          <table className="t">
            <thead><tr><th>Part</th><th className="num">Cost</th></tr></thead>
            <tbody>
              <tr><td>Reading pages the model has to transcribe</td><td className="num">${ex.pages.toFixed(3)}</td></tr>
              <tr><td>Describing the figures<div className="muted" style={{ fontSize: 12 }}>Two calls each — a description, then a spec for the ones that can be redrawn</div></td><td className="num">${ex.figures.toFixed(3)}</td></tr>
              <tr><td>Explanations written ahead of time<div className="muted" style={{ fontSize: 12 }}>Every keyword, every depth, once — paid here instead of every time a student taps</div></td><td className="num">${ex.explanations.toFixed(3)}</td></tr>
              <tr><td><b>Total, once</b></td><td className="num"><b>${ex.total.toFixed(2)}</b></td></tr>
              <tr><td className="muted">Add this if the same book arrives scanned instead of printed text</td><td className="num muted">+${sc.extra_vs_native.toFixed(2)}</td></tr>
            </tbody>
          </table>
          <div className="note">
            The explanations line is the one worth understanding. Writing every keyword's
            explanation once, while the book is in review, is what stops cost growing with use —
            without it, every student tapping the same word pays for the same answer again. See
            <Link to="/pa/demand" style={{ marginLeft: 4 }}>Catalogue and cost</Link> for what each
            book has actually cost and how many classes it serves.
          </div>
        </div>

        <div className="note">
          Student asks are capped at <b>{num(v.daily_explanations_per_student || 0)} a day each</b>.
          Per student, not a shared school pool — one keen reader would empty a pool by lunchtime
          and everyone else would find the feature broken.
        </div>
      </div>
    </Page>
  )
}
