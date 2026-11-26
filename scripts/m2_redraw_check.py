"""M2 redraw path with the image model mocked: fallback, aspect, label check."""
import io, sys
import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from app import m2
from PIL import Image
class Store(dict):
    def get(self, k): return self[k]
    def put(self, k, v): self[k] = v
st = Store(); m2.C._store = lambda: st
class Book: content_key = 'bk'; grade = '8'; subject = 'Science'
def png(w, h, col=(200, 180, 120)):
    b = io.BytesIO(); Image.new('RGB', (w, h), col).save(b, 'PNG'); return b.getvalue()
st['bk/images/a.png'] = png(600, 200)
res = []
def ok(name, cond, info=''): res.append(cond); print('PASS' if cond else 'FAIL', name, info)
cfg = {'provider': 'openai', 'providers': {'openai': {'base_url': 'x', 'model': 'gpt-image-1', 'api_key': 'k'}}, 'generate_kinds': ['diagram'], 'deep_describe': False}
m2.SECRET = 'api_key'
# 1 offline: no description, no kind -> clean copy offered for a small picture
r = m2.redo_figure(Book, {'image': 'images/a.png', 'width': 600, 'height': 200}, {}, {**cfg, 'generate_kinds': []}, {})
ok('fallback offers cleaned copy', r['status'] == 'generated' and r['method'] == 'enhance', r.get('note', '')[:80])
ok('fallback note reads well', not r['note'].startswith('.'), r['note'][:60])
# 2 generated picture padded to the printed shape, labels checked
m2.replica = lambda *a, **k: png(1536, 1024, (255, 255, 255))
m2.deep_describe = lambda data, cfg: {'text_in_figure': ['Petal', 'Sepl']}
blk = {'image': 'images/a.png', 'width': 600, 'height': 200, 'desc': {'type': 'diagram', 'summary': 'flower', 'text_in_figure': ['Petal', 'Sepal', 'Centre (ovary)']}}
r = m2.redo_figure(Book, blk, {}, cfg, {})
im = Image.open(io.BytesIO(st['bk/' + r['image']]))
ok('redraw generated', r['status'] == 'generated' and r['method'] == 'openai', r.get('error'))
ok('redraw keeps printed shape 3:1', abs(im.width / im.height - 3) < 0.05, im.size)
ok('missing labels flagged', r['label_check']['missing'] == ['Sepal', 'Centre (ovary)'], r.get('note'))
print(f'SUMMARY {sum(res)} of {len(res)} passed')
