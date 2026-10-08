import { useLoad, Page } from '../../ui'
import { BookTile } from './common'

export default function MyBooks() {
  const { data } = useLoad('/api/student/home')
  return (
    <Page title="My books" sub="Books from your school and books you got from the store">
      <div className="tiles">{data?.books.map(b => <BookTile key={b.id} b={b} action={<div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{b.owned === 'school' ? 'From your school' : 'Bought'}</div>} />)}</div>
      {data && !data.books.length && <div className="card empty">No books yet</div>}
    </Page>
  )
}
