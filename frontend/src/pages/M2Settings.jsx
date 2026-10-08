import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLoad, Page, Field, Switch, useToast } from '../ui'

const PROV = [['openai', 'OpenAI', 'gpt-image-1, dall-e-3'], ['gemini', 'Google Gemini', 'Imagen 4, Gemini image models'], ['local', 'Local', 'Stable Diffusion WebUI or Forge on your server']]
const KINDS = ['photo', 'diagram', 'chart', 'map']

export default function M2Settings() {
  const { data, setData } = useLoad('/api/pipeline/m2')
  const [v, setV] = useState(null); const [test, setTest] = useState(null); const [busy, setBusy] = useState(false); const toast = useToast()
  useEffect(() => { data && setV(structuredClone(data.values)) }, [data])
  if (!v) return <Page title="Figure redraw (M2)" />
  const p = v.providers[v.provider]; const saved = data.values.providers[v.provider]
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  const setP = (k, x) => setV(s => ({ ...s, providers: { ...s.providers, [s.provider]: { ...s.providers[s.provider], [k]: x } } }))
  const toggle = (k, kind) => set(k, v[k].includes(kind) ? v[k].filter(x => x !== kind) : [...v[k], kind])
  const dirty = JSON.stringify(v) !== JSON.stringify(data.values)
  const save = async () => { try { setData(await api('/api/pipeline/m2', { method: 'PUT', body: v })); toast('M2 settings saved') } catch (e) { toast(e.message, true) } }
  const reset = async () => { if (!confirm('Put every M2 setting back to default? Saved API keys are kept.')) return; try { setData(await api('/api/pipeline/m2/reset', { method: 'POST' })); toast('M2 settings back to default') } catch (e) { toast(e.message, true) } }
  const runTest = async () => { if (dirty) return toast('Save first, then test', true); setBusy(true); setTest(null); try { setTest(await api('/api/pipeline/m2/test', { method: 'POST' })) } catch (e) { setTest({ ok: false, error: e.message }) } setBusy(false) }
  return (
    <Page title="Figure redraw (M2)" sub="After conversion, every figure is drawn again from its description. The original is always kept and the reviewer picks which one students see."
      actions={<><button className="btn" onClick={reset}>Reset</button><button className="btn primary" disabled={!dirty} onClick={save}>Save changes</button></>}>
      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>M2</h3><span className="sub">{v.enabled ? 'Runs on every new book before it reaches the reviewer' : 'Off: books go to the reviewer with their original figures'}</span>
            <div className="right m1-bool"><Switch checked={v.enabled} onChange={x => set('enabled', x)} label="Run M2" /><span>{v.enabled ? 'On' : 'Off'}</span></div></div>
          <div className="card-b stack">
            <div className="grid2">
              <div className="m2-kind"><b>Redraw as SVG (no model, no cost)</b><p className="muted">Diagrams, charts and maps M1 read as a structure are drawn as clean vector art in the EduVerse style.</p>
                <div className="m1-bool"><Switch checked={v.svg_redraw} onChange={x => set('svg_redraw', x)} label="SVG redraw" /><span>{v.svg_redraw ? 'On' : 'Off'}</span></div>
                <div className="chips" style={{ marginTop: 8 }}>{['diagram', 'chart', 'map'].map(k => <button key={k} className={'chip' + (v.svg_kinds.includes(k) ? ' on' : '')} onClick={() => toggle('svg_kinds', k)}>{k}</button>)}</div></div>
              <div className="m2-kind"><b>Generate with the image model</b><p className="muted">Everything else, from the description, the named parts, the printed labels and the caption.</p>
                <div className="chips">{KINDS.map(k => <button key={k} className={'chip' + (v.generate_kinds.includes(k) ? ' on' : '')} onClick={() => toggle('generate_kinds', k)}>{k}</button>)}</div>
                <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>Decorations and text banners are never redrawn.</p></div>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Image model</h3><button className="btn sm right" disabled={busy} onClick={runTest}>{busy ? 'Generating' : 'Test with one image'}</button></div>
          <div className="card-b stack">
            <div className="seg" role="radiogroup">{PROV.map(([k, l]) => <button key={k} className={v.provider === k ? 'on' : ''} onClick={() => set('provider', k)} role="radio" aria-checked={v.provider === k}>{l}</button>)}</div>
            <div className="muted" style={{ fontSize: 13 }}>{PROV.find(x => x[0] === v.provider)[2]}</div>
            <div className="grid3">
              <Field label="Model" hint={v.provider === 'local' ? 'Checkpoint name, empty for the one loaded' : ''}><input className="input" value={p.model} onChange={e => setP('model', e.target.value)} /></Field>
              <Field label="Address"><input className="input" value={p.base_url} onChange={e => setP('base_url', e.target.value)} /></Field>
              <Field label="API key" hint={saved.api_key === 'saved' ? 'A key is saved. Type to replace it.' : v.provider === 'local' ? 'Only if your server asks for one' : 'Stored on the server, never shown again'}>
                <input className="input" type="password" placeholder={saved.api_key === 'saved' ? 'Saved' : 'Paste key'} value={p.api_key === 'saved' ? '' : p.api_key} onChange={e => setP('api_key', e.target.value || (saved.api_key === 'saved' ? 'saved' : ''))} /></Field>
              {v.provider === 'openai' && <Field label="Quality" hint="gpt-image-1 only"><select className="input" value={p.quality || 'medium'} onChange={e => setP('quality', e.target.value)}>{['low', 'medium', 'high', 'auto'].map(q => <option key={q}>{q}</option>)}</select></Field>}
              {v.provider === 'local' && <Field label="Steps"><input className="input" type="number" min="1" value={p.steps || 25} onChange={e => setP('steps', +e.target.value)} /></Field>}
              <Field label="Size" hint="auto follows the shape of the original"><input className="input" value={v.size} onChange={e => set('size', e.target.value)} /></Field>
            </div>
            {test && <div className={'note ' + (test.ok ? 'm1-ok' : 'm1-bad')}>{test.ok ? <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}><img src={test.image} alt="Test result" style={{ width: 140, borderRadius: 8, border: '1px solid var(--line)' }} /><b>The image model works.</b></div> : <><b>Did not work.</b> {test.error}</>}</div>}
          </div>
        </div>
        <div className="row">
          <div className="card">
            <div className="card-h"><h3>Style prompt</h3><span className="sub">Put in front of every figure's description</span></div>
            <div className="card-b"><textarea className="input" rows="5" value={v.style_prompt} onChange={e => set('style_prompt', e.target.value)} /></div>
          </div>
          <div className="card">
            <div className="card-h"><h3>Limits</h3></div>
            <div className="card-b grid2">
              <Field label="Images per book" hint="Spend limit. SVG redraws do not count."><input className="input" type="number" min="0" value={v.max_images_per_book} onChange={e => set('max_images_per_book', e.target.value)} /></Field>
              <Field label="Timeout per image (seconds)"><input className="input" type="number" min="10" value={v.timeout_s} onChange={e => set('timeout_s', e.target.value)} /></Field>
            </div>
          </div>
        </div>
      </div>
    </Page>
  )
}
