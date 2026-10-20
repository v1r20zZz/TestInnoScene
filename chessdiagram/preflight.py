"""Report effective raster resolution and potential content cropping."""
from PySide6.QtGui import QImage
from .render import Renderer
import chess
from .model import square_xy

def inspect_document(doc,d):
    warnings=[];s=d['style'];minimum=min(300,s['dpi']);mm_per_unit=s['board_mm']/640
    def check(key,units,label):
        if not key or key.lower().endswith('.svg'):return
        image=QImage.fromData(doc.resources.get(key,b''))
        if image.isNull():warnings.append(label+': изображение не читается');return
        dpi=min(image.width(),image.height())/(units*mm_per_unit/25.4)
        if dpi<minimum:warnings.append(f'{label}: эффективное разрешение {dpi:.0f} DPI (желательно {minimum})')
    for symbol,key in d['sets'].get(s['piece_set'],{}).items():
        check(key,80*s['piece_scale']*(s['white_scale'] if symbol.isupper() else s['black_scale']),'Фигура '+symbol)
    for key,units,label in [('board_image',640,'Изображение доски'),('light_texture',80,'Светлые клетки'),('dark_texture',80,'Тёмные клетки')]:check(s[key],units,label)
    rect=Renderer(doc).rect(d)
    for sq,p in chess.Board(d['fen']).piece_map().items():
        ov=d['piece_overrides'].get(str(sq),{});x,y=square_xy(sq,s['flipped']);size=80*ov.get('scale',s['piece_scale'])*(s['white_scale'] if p.color else s['black_scale'])
        cx=x+40+ov.get('dx',s['piece_dx']);cy=y+40+ov.get('dy',s['piece_dy'])
        if cx-size/2<rect.left() or cx+size/2>rect.right() or cy-size/2<rect.top() or cy+size/2>rect.bottom():warnings.append('Возможно обрезание фигуры '+chess.square_name(sq))
    for o in d['objects']:
        if o['kind']=='image':check(o.get('resource',''),max(abs(o['points'][-1][0]-o['points'][0][0]),abs(o['points'][-1][1]-o['points'][0][1]),1),'Вставленное изображение')
    return warnings
