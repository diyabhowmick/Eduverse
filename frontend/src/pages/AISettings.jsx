import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, num } from '../api'
import { useLoad, Page, Field, useToast } from '../ui'

const PROV = [['ollama', 'Ollama', 'Runs on your own server'], ['anthropic', 'Claude', 'Anthropic API'], ['openai', 'OpenAI', 'OpenAI API']]
const DEPTH = [['exam', 'Exam'], ['concept_clarity', 'Concept clarity'], ['curiosity', 'Curiosity'], ['research', 'Research']]

export default function AISettings() {
  const { data } = useLoad('/api/settings/ai')
  const [v, setV] = useState(null); const toast = useToast()
  const status = useLoad('/api/settings/openai/status')
  const [test, setTest] = useState(null); const [testing, setTesting] = useState(false)
  useEffect(() => { data && setV(structuredClone(data)) }, [data])
  if (!v) return <Page title="AI settings" />
  const p = v.providers[v.provider]
  const setP = (k, x) => setV(s => ({ ...s, providers: { ...s.providers, [s.provider]: { ...s.providers[s.provider], [k]: x } } }))
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  const o = v.providers.openai
  const setO = x => setV(s => ({ ...s, providers: { ...s.providers, openai: { ...s.providers.openai, api_key: x } } }))
  async function saveAndTest() {
    setTesting(true); setTest(null)
    try {
      setV(await api('/api/settings/ai', { method: 'PUT', body: v })); status.reload()
      const r = await api('/api/settings/openai/test', { method: 'POST' })
      setTest({ ok: true, text: `Connected. ${r.model} answered using the key ${r.source === 'env' ? 'in backend/.env' : 'saved here'}.` })
    } catch (e) { setTest({ ok: false, text: e.message }) } finally { setTesting(false) }
  }
  async function save() { try { setV(await api('/api/settings/ai', { method: 'PUT', body: v })); toast('AI settings saved') } catch (e) { toast(e.message, true) } }
  return (
    <Page title="AI settings" sub="The model behind every student explanation, and how far it goes" actions={<button className="btn primary" onClick={save}>Save changes</button>}>
      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>OpenAI connection</h3><span className="sub">Reads question papers and writes answers</span>
            {status.data && <span className={'tag right ' + (status.data.has_key ? 'ok' : 'warn')}>{status.data.has_key ? (status.data.source === 'env' ? 'Key in backend/.env' : 'Key saved') : 'No key yet'}</span>}</div>
          <div className="card-b stack">
            <div className="grid3">
              <Field label="OpenAI API key" hint={o.api_key === 'saved' ? 'A key is saved. Type to replace it.' : 'Starts with sk-. Stored on this server and never shown again.'}><input className="input" type="password" autoComplete="off" placeholder={o.api_key === 'saved' ? 'Saved' : 'Paste your key'} value={o.api_key === 'saved' ? '' : o.api_key} onChange={e => setO(e.target.value || (data.providers.openai.api_key === 'saved' ? 'saved' : ''))} /></Field>
              <Field label="Model for reading papers" hint="Must accept images. It copies each page."><input className="input" value={v.exam_model ?? 'gpt-4.1'} onChange={e => set('exam_model', e.target.value)} /></Field>
              <Field label="Model for writing answers" hint="Works out each answer. Stronger models are more accurate and cost more."><input className="input" value={v.answer_model ?? 'gpt-5.5'} onChange={e => set('answer_model', e.target.value)} /></Field>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn primary" disabled={testing} onClick={saveAndTest}>{testing ? 'Testing' : 'Save and test connection'}</button>
              {test && <span className={test.ok ? 'tag ok' : 'tag bad'} style={{ whiteSpace: 'normal' }} role="status">{test.text}</span>}
            </div>
            <div className="note">This does not change the model behind student explanations, which is set below. Each paper page and each generated answer is a paid OpenAI request.</div>
          </div>
        </div>
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
