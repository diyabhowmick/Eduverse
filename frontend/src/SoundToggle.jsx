import { useEffect, useState } from 'react'
import { sound } from './sound'

// Small, quiet control: sound is off until someone turns it on.
export default function SoundToggle() {
  const [on, setOn] = useState(sound.on)
  useEffect(() => sound.sub(setOn), [])
  return <button type="button" className={'snd-toggle' + (on ? ' on' : '')} onClick={() => sound.set(!on)}
    aria-pressed={on} aria-label={on ? 'Turn sound off' : 'Turn sound on'} title={on ? 'Sound on' : 'Sound off'}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" />
      {on ? <><path className="w1" d="M15.5 9a4 4 0 0 1 0 6" /><path className="w2" d="M18 6.5a7.5 7.5 0 0 1 0 11" /></> : <path d="M16 9.5l5 5m0-5l-5 5" />}</svg>
    <span>{on ? 'Sound on' : 'Sound off'}</span>
  </button>
}
