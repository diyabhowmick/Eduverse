// Pure text helpers behind MathText: no React, no KaTeX, so they can be tested on their own with node.
//
// Question text holds maths between $ signs, and tables as $$\begin{array}...\end{array}$$ (see backend/app/qtext.py).
// Papers read before that fix are repaired here too, so they look right without being read again.

const FORMAT = /\\(?:textit|textbf|textrm|textsf|texttt|emph|text|mathrm|mathit|mathbf|underline)\s*\{([^{}]*)\}/g

// Old readings cut a table into one $...$ per line: $\begin{array}{|c|c|}$ / $\text{A} & \text{B} \\$ / ... / $\end{array}$
// LaTeX's own markers \[ ... \] and \( ... \) become $$ and $, which is all the screen knows. A marker left as its own
// $\[$ by the old code, or whose partner was lost, is dropped. (\\[4pt] is a row break, not a marker.)
export function repairLegacy(text) {
  return String(text ?? '')
    .replace(/(^|[^$])\$\\begin\{(array|tabular)\}([\s\S]*?)\\end\{\2\}\$(?!\$)/g, (all, pre, env, inner) =>
      inner.includes('$') ? `${pre}$$\\begin{${env}}${inner.replace(/\$/g, '')}\\end{${env}}$$` : all)
    .replace(/\$[ \t]*\\[[\]()][ \t]*\$[ \t]*\n?/g, '')
    .replace(/(?<!\\)\\\[([\s\S]*?)(?:(?<!\\)|(?<=\\\\))\\\]/g, (_, x) => x.includes('$') ? x.trim() : '$$' + x.trim() + '$$')
    .replace(/(?<!\\)\\\(([\s\S]*?)(?:(?<!\\)|(?<=\\\\))\\\)/g, (_, x) => x.includes('$') ? x : '$' + x.trim() + '$')
    .replace(/^[ \t]*\\[[\]][ \t]*\n?/gm, '')
}

// A sentence wrongly put in maths: italic formatting, or several ordinary words. KaTeX would print it with no spaces.
export function isProse(inner) {
  if (inner.includes('\\begin{')) return false
  if (/\\(?:textit|emph|textbf)\{/.test(inner)) return true
  const bare = inner.replace(/\\[A-Za-z]+\s*(\{[^{}]*\})?/g, ' ')
  return (bare.match(/(?<![\\A-Za-z])[A-Za-z]{4,}(?![A-Za-z])/g) || []).length >= 4
}

export const plainWords = s => s.replace(FORMAT, '$1').replace(FORMAT, '$1').replace(/\\([%&#_$])/g, '$1').replace(/\\[,;:! ]/g, ' ')

const FIG = /\[\[fig:(\d+)\]\]/g
// The figure numbers whose [[fig:N]] mark is in the text, so the rest can be shown after it.
export const figureMarks = text => new Set([...String(text ?? '').matchAll(FIG)].map(m => +m[1]))

// -> [{kind: 'text' | 'inline' | 'display' | 'figure', value}]; a figure's value is its number
export function splitMath(text) {
  const src = repairLegacy(text)
  const re = /\$\$([\s\S]+?)\$\$|\$(\\begin\{[\s\S]+?\\end\{[A-Za-z*]+\})\$|\$((?:[^$\\\n]|\\[^\n])+?)\$/g
  const out = []; let last = 0, m
  const pushText = s => {
    String(s ?? '').split(/(\[\[fig:\d+\]\])/).forEach(part => {
      const f = /^\[\[fig:(\d+)\]\]$/.exec(part)
      if (f) out.push({ kind: 'figure', value: +f[1] })
      else if (part) out.push({ kind: 'text', value: plainWords(part) })
    })
  }
  while ((m = re.exec(src))) {
    pushText(src.slice(last, m.index)); last = re.lastIndex
    if (m[1] != null || m[2] != null) out.push({ kind: 'display', value: (m[1] ?? m[2]).trim() })
    else if (isProse(m[3])) pushText(m[3])
    else out.push({ kind: 'inline', value: m[3] })
  }
  pushText(src.slice(last))
  return out
}

// Splits on a separator only at brace depth 0, and not when escaped (\&).
function splitTop(s, sep) {
  const out = []; let cur = '', depth = 0
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (c === '\\' && s[i + 1] && s[i + 1] !== '\\') { cur += c + s[i + 1]; i++; continue }
    if (c === '{') depth++
    else if (c === '}') depth = Math.max(0, depth - 1)
    if (depth === 0 && s.startsWith(sep, i)) { out.push(cur); cur = ''; i += sep.length - 1; continue }
    cur += c
  }
  out.push(cur)
  return out
}

// $$\begin{array}{|l|l|} ... \end{array}$$ -> {rows: [[cell tex]], header} so it can be drawn as an HTML table whose
// long cells wrap. Anything else (a matrix, a formula around an array, a nested array) returns null and stays KaTeX.
export function parseArray(tex) {
  const m = /^\\begin\{(array|tabular)\}\s*(\{[^{}]*\})?([\s\S]*)\\end\{\1\}$/.exec(tex.trim())
  if (!m || /\\begin\{/.test(m[3])) return null
  const rows = splitTop(m[3].replace(/\\hline|\\cline\{[^}]*\}/g, ''), '\\\\')
    .map(r => splitTop(r, '&').map(c => c.trim()))
    .filter(r => r.some(c => c))
  if (!rows.length) return null
  const width = Math.max(...rows.map(r => r.length))
  rows.forEach(r => { while (r.length < width) r.push('') })
  const header = rows.length > 2 && rows[0].every(c => cellPlain(c) != null) && /list|column|name|property/i.test(rows[0].join(' '))
  return { rows, header }
}

// A cell that is only words -> those words; a cell with maths in it -> null (KaTeX draws it).
export function cellPlain(cell) {
  const s = plainWords(cell).replace(/\\quad|\\qquad/g, ' ').replace(/\s+/g, ' ').trim()
  return /[\\^_{}]/.test(s) ? null : s
}
