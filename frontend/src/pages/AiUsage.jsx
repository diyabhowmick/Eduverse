import { useEffect, useState } from 'react'
import { api, num, when } from '../api'
import { useLoad, Page, Modal, Field, Tag, LineChart, MathText, useToast } from '../ui'
import { STYLE } from '../ExplainPanel'

const KIND = { explain: 'New explanations', explain_deep: 'Level 3 and own questions', prepare: 'Written in advance', doubt: 'Typed questions', paper_read: 'Reading papers', paper_answers: 'Writing answers', recap: 'Chapter recaps' }
const money = (v, cur) => v == null ? '' : (cur === 'INR' ? '₹' : cur === 'USD' ? '$' : cur + ' ') + v.toFixed(v < 1 ? 4 : 2)

function Prepare({ book, onClose, onStarted }) {
  const [styles, setStyles] = useState(['concept_clarity']); const [est, setEst] = useState(null); const [err, setErr] = useState('')
  useEffect(() => { setEst(null); if (styles.length) api(`/api/learn/admin/prepare/${book.id}/estimate?styles=${styles.join(',')}`).then(setEst).catch(e => setErr(e.message)) }, [styles.join()])
  async function go() { try { onStarted(await api('/api/learn/admin/prepare', { method: 'POST', body: { book_id: book.id, styles } })) } catch (e) { setErr(e.message) } }
  const over = est && est.budget_left != null && est.tokens > est.budget_left
  return <Modal title={'Write explanations ahead: ' + book.title} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button>
    <button className="btn primary" disabled={!est?.requests || over} onClick={go}>Start writing</button></>}>
    {err && <div className="err">{err}</div>}
    <p style={{ marginTop: 0 }}>{book.track === 'exam' ? 'Every question in its approved papers' : 'Every highlighted word in the book, and the hard words inside each explanation,'} gets a saved explanation, so students are served instantly and at no cost.</p>
    <Field label="Styles to write">{Object.entries(STYLE).map(([k, l]) => <label key={k} style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '4px 0' }}>
      <input type="checkbox" checked={styles.includes(k)} onChange={e => setStyles(s => e.target.checked ? [...s, k] : s.filter(x => x !== k))} />{l}</label>)}</Field>
    {est && <div className="note">{est.note || <>About <b>{num(est.requests)}</b> requests and <b>{num(est.tokens)}</b> tokens with {est.model}
      {est.marks ? <> ({num(est.level1)} level 1, {num(est.marks)} to pick level 2 words, about {num(est.level2)} level 2)</> : null}.
      {est.budget_left != null && <> This month's budget has {num(Math.max(0, est.budget_left))} tokens left.</>}{over && <b> Not enough budget left.</b>}</>}</div>}
  </Modal>
}

export default function AiUsage() {
  const [days, setDays] = useState(30)
  const { data, reload } = useLoad('/api/learn/admin/usage?days=' + days, [days])
  const books = useLoad('/api/books'); const jobs = useLoad('/api/learn/admin/prepare/jobs')
  const ai = useLoad('/api/settings/ai'); const toast = useToast()
  const [prep, setPrep] = useState(null); const [prices, setPrices] = useState(null)
  const running = jobs.data?.some(j => ['queued', 'running'].includes(j.status))
  useEffect(() => { if (!running) return; const t = setInterval(() => { jobs.reload(); reload() }, 3000); return () => clearInterval(t) }, [running])
  useEffect(() => { if (ai.data && !prices) setPrices({ currency: ai.data.currency || 'USD', prices: ai.data.prices || {} }) }, [ai.data])
  async function savePrices() {
    try { await api('/api/settings/ai', { method: 'PUT', body: { ...ai.data, ...prices } }); toast('Prices saved'); ai.reload(); reload() } catch (e) { toast(e.message, true) }
  }
  async function act(e, a) { try { await api(`/api/learn/admin/explanations/${e.id}/${a}`, { method: 'POST' }); toast(a === 'restore' ? 'Back in use' : 'Retired'); reload() } catch (x) { toast(x.message, true) } }
  const d = data
  const usedPct = d?.budget ? Math.min(100, d.month_tokens / d.budget * 100) : null
  const models = [...new Set([...(d?.by_model || []).map(m => m.model), ai.data?.exam_model, ai.data?.answer_model, ai.data?.providers?.openai?.model].filter(Boolean))]
  const titles = Object.fromEntries((books.data || []).map(b => [b.id, b.title]))
  return (
    <Page title="AI usage" sub="What AI costs, how much is served from saved explanations, and what students find hardest"
      actions={<div className="seg">{[[7, '7 days'], [30, '30 days'], [90, '90 days']].map(([k, l]) => <button key={k} className={days === k ? 'on' : ''} onClick={() => setDays(k)}>{l}</button>)}</div>}>
      {d && <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{num(d.month_tokens)}</div><div className="l">Tokens this month{d.budget ? ` of ${num(d.budget)}` : ''}</div>
            {usedPct != null && <div className="bar-track" style={{ marginTop: 8 }}><i style={{ width: usedPct + '%', background: usedPct > 85 ? 'var(--red)' : undefined }} /></div>}</div>
          <div className="metric"><div className="v">{d.hit_rate == null ? '–' : d.hit_rate + '%'}</div><div className="l">Explanations served from saved copies</div></div>
          <div className="metric"><div className="v">{num(d.requests)}</div><div className="l">Model requests, {days} days</div></div>
          <div className="metric"><div className="v">{d.cost == null ? '–' : money(d.cost, d.currency)}</div><div className="l">{d.cost == null ? 'Add prices below to see cost' : `Estimated cost, ${days} days${d.cost_partial ? ' (some models unpriced)' : ''}`}</div></div>
        </div>
        <div className="row">
          <div className="card"><div className="card-h"><h3>Explanations served</h3><span className="sub">Saved copies against newly written</span></div>
            <div className="card-b"><LineChart data={d.daily} keys={[{ key: 'saved', color: '#1F7A4D' }, { key: 'generated', color: '#E0212F' }]} height={190} /></div></div>
          <div className="card"><div className="card-h"><h3>Tokens per day</h3></div>
            <div className="card-b"><LineChart data={d.daily} keys={[{ key: 'tokens', color: '#1E4F9A' }]} height={190} /></div></div>
        </div>
        <div className="row">
          <div className="card"><div className="card-h"><h3>Where tokens go</h3></div>
            <table className="t"><thead><tr><th>Use</th><th className="num">Requests</th><th className="num">Tokens</th><th className="num">Served saved</th></tr></thead>
              <tbody>{d.by_kind.map(k => <tr key={k.kind}><td>{KIND[k.kind] || k.kind}</td><td className="num">{num(k.requests)}</td><td className="num">{num(k.tokens)}</td><td className="num">{k.saved ? num(k.saved) : ''}</td></tr>)}</tbody></table>
            {!d.by_kind.length && <div className="empty">No AI use yet in this period</div>}</div>
          <div className="card"><div className="card-h"><h3>Prices</h3><span className="sub">Per million tokens, from your provider's price page</span></div>
            {prices && <div className="card-b stack">
              <Field label="Currency"><select className="input" style={{ maxWidth: 140 }} value={prices.currency} onChange={e => setPrices(p => ({ ...p, currency: e.target.value }))}>{['USD', 'INR'].map(c => <option key={c}>{c}</option>)}</select></Field>
              {models.map(m => <div key={m} className="grid3" style={{ alignItems: 'end' }}><b style={{ paddingBottom: 10 }}>{m}</b>
                {['in', 'out'].map(k => <Field key={k} label={k === 'in' ? 'Input' : 'Output'}><input className="input" type="number" min="0" step="0.01" value={prices.prices[m]?.[k] ?? ''}
                  onChange={e => setPrices(p => ({ ...p, prices: { ...p.prices, [m]: { ...p.prices[m], [k]: e.target.value === '' ? '' : +e.target.value } } }))} /></Field>)}</div>)}
              <button className="btn" style={{ justifySelf: 'start' }} onClick={savePrices}>Save prices</button></div>}</div>
        </div>
        <div className="card"><div className="card-h"><h3>Write explanations ahead</h3><span className="sub">One cost per book, then free for every student</span></div>
          <table className="t"><thead><tr><th>Book or exam pack</th><th>Stage</th><th>Last run</th><th /></tr></thead>
            <tbody>{(books.data || []).filter(b => b.track === 'exam' || ['live', 'in_review', 'approved'].includes(b.status)).map(b => {
              const j = jobs.data?.find(x => x.book_id === b.id)
              return <tr key={b.id}><td><b>{b.title}</b><div className="muted">{b.track === 'exam' ? 'Exam pack' : 'Textbook'}</div></td><td><Tag s={b.status} /></td>
                <td>{j ? <>{['queued', 'running'].includes(j.status) ? <><div className="bar-track" style={{ maxWidth: 160 }}><i style={{ width: (j.total ? j.done / j.total * 100 : 0) + '%' }} /></div><span className="muted">{j.done} of {j.total}</span></>
                  : <><Tag s={j.status === 'done' ? 'done' : 'failed'}>{j.status === 'done' ? 'Done' : 'Failed'}</Tag> <span className="muted">{j.done} written{j.failed ? `, ${j.failed} failed` : ''}, {num(j.tokens)} tokens, {when(j.finished_at)}</span></>}
                  {j.error && j.status !== 'running' && <div className="muted" style={{ fontSize: 12 }}>{j.error}</div>}</> : <span className="muted">Never</span>}</td>
                <td className="acts"><button className="btn sm" disabled={running} onClick={() => setPrep(b)}>Write ahead</button></td></tr>
            })}</tbody></table></div>
        <div className="row">
          <div className="card"><div className="card-h"><h3>What students find hardest</h3><span className="sub">Most explained, {days} days</span></div>
            <table className="t"><thead><tr><th>Word or question</th><th>Where</th><th className="num">Times asked</th></tr></thead>
              <tbody>{d.confusion.map((c, i) => <tr key={i}><td><b>{c.term}</b></td><td className="muted">{c.where}</td><td className="num">{num(c.taps)}</td></tr>)}</tbody></table>
            {!d.confusion.length && <div className="empty">Nothing yet. This fills as students ask for explanations.</div>}</div>
          <div className="card"><div className="card-h"><h3>Reported explanations</h3><span className="sub">Not shown to students until restored</span></div>
            <div className="card-b stack">{d.flagged.map(e => <div key={e.id} className="note"><b>{e.term}</b> <span className="muted">{titles[e.book_id] || ''}, {e.reports} reports</span>
              <div style={{ margin: '6px 0', maxHeight: 120, overflow: 'auto' }}><MathText text={e.text} /></div>
              <button className="btn sm" onClick={() => act(e, 'restore')}>Restore</button> <button className="btn ghost sm" onClick={() => act(e, 'retire')}>Retire</button></div>)}
              {!d.flagged.length && <div className="empty">No reports</div>}</div></div>
        </div>
        <div className="muted" style={{ fontSize: 13 }}>{num(d.explanations.total)} saved explanations: {num(d.explanations.final || 0)} final, {num(d.explanations.candidate || 0)} being compared, {num(d.explanations.flagged || 0)} reported, {num(d.explanations.retired || 0)} retired.</div>
      </div>}
      {prep && <Prepare book={prep} onClose={() => setPrep(null)} onStarted={() => { setPrep(null); toast('Writing explanations'); jobs.reload() }} />}
    </Page>
  )
}
