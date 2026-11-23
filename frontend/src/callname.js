// What Eddie calls the student: their chosen name ("call me Nas AI"), else their first name.
export function callName(name, profile) {
  const nick = (profile?.nickname || '').trim()
  if (nick) {
    try {
      localStorage.setItem('ev_nick', nick)
      const l = JSON.parse(localStorage.getItem('ev_last_student') || 'null'); if (l && l.nick !== nick) localStorage.setItem('ev_last_student', JSON.stringify({ ...l, nick }))
    } catch { /* private mode */ }
    return nick
  }
  try { if (profile !== undefined) localStorage.removeItem('ev_nick'); else { const saved = localStorage.getItem('ev_nick'); if (saved) return saved } } catch { /* private mode */ }
  return (name || 'there').split(' ')[0]
}
export function forgetCallName() { try { localStorage.removeItem('ev_nick') } catch { /* private mode */ } }
