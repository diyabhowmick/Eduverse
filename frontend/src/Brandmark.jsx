// The EduVerse wordmark with the zPROx credit. Small enough to load with the login form.
export function Brandmark({ small }) {
  return <div className={'brandmark' + (small ? ' small' : '')}>
    <span className="bm-word" aria-label="EduVerse"><span>EDU</span><b>VERSE</b></span>
    <span className="bm-by">by <img src="/brand/zprox_logo_dark.png" alt="zPROx.AI" /></span>
  </div>
}
