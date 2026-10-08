import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, num } from '../api'
import { useLoad, Page, Field, useToast } from '../ui'

const PROV = [['ollama', 'Ollama', 'Runs on your own server'], ['anthropic', 'Claude', 'Anthropic API'], ['openai', 'OpenAI', 'OpenAI API']]
const DEPTH = [['exam', 'Exam'], ['concept_clarity', 'Concept clarity'], ['curiosity', 'Curiosity'], ['research', 'Research']]

export default function AISettings() {
  const { data } = useLoad('/api/settings/ai')
  const [v, setV] = useState(null); const toast = useToast()
  useEffect(() => { data && setV(structuredClone(data)) }, [data])
  if (!v) return <Page title="AI settings" />
  const p = v.providers[v.provider]
  const setP = (k, x) => setV(s => ({ ...s, providers: { ...s.providers, [s.provider]: { ...s.providers[s.provider], [k]: x } } }))
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  async function save() { try { setV(await api('/api/settings/ai', { method: 'PUT', body: v })); toast('AI settings saved') } catch (e) { toast(e.message, true) } }
  return (
    <Page title="AI settings" sub="The model behind every student explanation, and how far it goes" actions={<button className="btn primary" onClick={save}>Save changes</button>}>
      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>Explanation model</h3><span className="sub">Used in the student reader</span></div>
          <div className="card-b stack">
            <div className="seg" role="radiogroup">{PROV.map(([k, l]) => <button key={k} className={v.provider === k ? 'on' : ''} onClick={() => set('provider', k)} role="radio" aria-checked={v.provider === k}>{l}</button>)}</div>
            <div className="grid3">
              <Field label="Model"><input className="input" value={p.model} onChange={e => setP('model', e.target.value)} /></Field>
              <Field label="Endpoint"><input className="input" value={p.base_url} onChange={e => setP('base_url', e.target.value)} /></Field>
              {v.provider !== 'ollama'
                ? <Field label="API key" hint={p.api_key === 'saved' ? 'A key is saved. Type to replace it.' : 'Stored on the server, never shown again'}><input className="input" type="password" placeholder={p.api_key === 'saved' ? 'Saved' : 'Paste key'} value={p.api_key === 'saved' ? '' : p.api_key} onChange={e => setP('api_key', e.target.value || (data.providers[v.provider].api_key === 'saved' ? 'saved' : ''))} /></Field>
                : <Field label="API key" hint="Not needed for Ollama"><input className="input" disabled value="" /></Field>}
              <Field label="Temperature" hint="Lower is more consistent"><input className="input" type="number" step="0.1" min="0" max="1" value={v.temperature} onChange={e => set('temperature', +e.target.value)} /></Field>
              <Field label="Max answer length (tokens)"><input className="input" type="number" value={v.max_tokens} onChange={e => set('max_tokens', +e.target.value)} /></Field>
            </div>
          </div>
        </div>
        <div className="row">
          <div className="card">
            <div className="card-h"><h3>Usage limits</h3></div>
            <div className="card-b grid2">
              <Field label="Explanations per student per day"><input className="input" type="number" value={v.daily_explanations_per_student} onChange={e => set('daily_explanations_per_student', +e.target.value)} /></Field>
              <Field label="Monthly token budget" hint={num(v.monthly_token_budget) + ' tokens'}><input className="input" type="number" value={v.monthly_token_budget} onChange={e => set('monthly_token_budget', +e.target.value)} /></Field>
            </div>
          </div>
          <div className="card">
            <div className="card-h"><h3>Book processing</h3><Link className="right linkbtn" to="/sa/extraction">M1 settings</Link></div>
            <div className="card-b grid2">
              <Field label="Credits per page" hint="Charged for each page M1 reads"><input className="input" type="number" min="0" value={v.m1_credits_per_page} onChange={e => set('m1_credits_per_page', +e.target.value)} /></Field>
              <div className="note" style={{ alignSelf: 'center' }}>Models for reading books and redrawing figures are set in Book extraction (M1) and Figure redraw (M2).</div>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Depth rules</h3><span className="sub">The student picks a purpose; the model follows its rule</span></div>
          <div className="card-b stack">{DEPTH.map(([k, l]) => (
            <div className="depth" key={k}><label style={{ fontWeight: 700, paddingTop: 8 }}>{l}</label>
              <textarea className="input" rows="2" value={v.depth_rules[k]} onChange={e => set('depth_rules', { ...v.depth_rules, [k]: e.target.value })} /></div>))}</div>
        </div>
      </div>
    </Page>
  )
}
