import { useLoad, Page } from '../../ui'
import { BookTile } from './common'

export default function MyBooks() {
  const { data } = useLoad('/api/student/home')
  return (
    <Page title="My books and exams" sub="Textbooks and exam packs from your organisation or the store">
      <div className="tiles">{data?.books.map(b => <BookTile key={b.id} b={b} action={<div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{b.owned === 'school' ? 'From your organisation' : 'Bought'}</div>} />)}</div>
      {data && !data.books.length && <div className="card empty">No books yet</div>}
    </Page>
  )
}
