// A printed list often carries its own labels: "1.", "(a)", "(ii)". When every item does, the
// browser's own numbers are hidden (no "1. 1. Select..."), and a lettered item under a numbered
// one is indented under it, as in the book.
const LABEL = /^\s*(\(?(\d{1,2}|[a-z]|[ivx]{1,4})[.)])\s+/i
const NUM = /^\s*\(?\d{1,2}[.)]/
export function listShape(items) {
  const own = items.length > 0 && items.every(it => LABEL.test(it.text || ''))
  let seenNum = false
  const sub = items.map(it => {
    const t = it.text || ''
    if (NUM.test(t)) { seenNum = true; return false }
    return own && seenNum
  })
  return { own, sub }
}
