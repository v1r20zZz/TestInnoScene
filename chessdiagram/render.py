from __future__ import annotations
import math, io
from functools import lru_cache
import chess, chess.svg
from PySide6.QtCore import Qt, QRectF, QPointF, QByteArray
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath, QFont, QLinearGradient, QImage, QTransform
from PySide6.QtSvg import QSvgRenderer
from .model import square_xy,is_dark

@lru_cache(maxsize=200)
def builtin_svg(symbol,kind):
    piece=chess.Piece.from_symbol(symbol)
    if kind=='Классический': return chess.svg.piece(piece,size=80).encode()
    fill='#fffdf5' if symbol.isupper() else '#25332f'; stroke='#25332f' if symbol.isupper() else '#fffdf5'
    paths={
      'p':'M29 62L32 40C17 26 24 12 40 12C56 12 63 26 48 40L51 62Z',
      'r':'M24 62L26 29L19 29L19 12L30 12L30 20L36 20L36 12L44 12L44 20L50 20L50 12L61 12L61 29L54 29L56 62Z',
      'n':'M23 62L27 45L43 34L26 38L17 30L30 18L33 7L42 16C64 17 65 44 56 62Z',
      'b':'M23 62L30 43Q17 29 40 9Q63 29 50 43L57 62ZM40 12L40 31',
      'q':'M26 62L18 22L30 34L40 12L50 34L62 22L54 62Z',
      'k':'M26 62L23 36Q24 24 36 25L36 19L29 19L29 11L36 11L36 4L44 4L44 11L51 11L51 19L44 19L44 25Q56 24 57 36L54 62Z'}
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><g fill="{fill}" stroke="{stroke}" stroke-width="3" stroke-linejoin="round"><path d="{paths[symbol.lower()]}"/><path d="M18 63H62L65 72H15Z"/></g></svg>'.encode()

class Renderer:
    def __init__(self,document): self.doc=document; self.cache={}
    def resource(self,key): return self.doc.resources.get(key,b'')
    def rect(self,d=None):
        s=(d or self.doc.d)['style']; m=s['margin']
        return QRectF(-m-s['canvas_extra_x']/2,-m-s['canvas_extra_y']/2,
                      640+2*m+s['canvas_extra_x'],640+2*m+s['canvas_extra_y'])
    def image(self,p,b,rect):
        if not b:return
        key=hash(b)
        if key not in self.cache:
            self.cache[key]=QSvgRenderer(QByteArray(b)) if b.lstrip().startswith((b'<svg',b'<?xml')) else QImage.fromData(b)
        obj=self.cache[key]
        if isinstance(obj,QSvgRenderer):
            if obj.isValid(): obj.render(p,rect)
        elif not obj.isNull():
            size=obj.size(); scale=min(rect.width()/size.width(),rect.height()/size.height())
            w,h=size.width()*scale,size.height()*scale
            p.drawImage(QRectF(rect.center().x()-w/2,rect.center().y()-h/2,w,h),obj)
    def text(self,p,rect,text,font,color,flags=Qt.AlignCenter):
        # Text to outlines ensures consistent vector exports even without the font on the recipient's PC.
        from PySide6.QtGui import QFontMetricsF
        fm=QFontMetricsF(font); path=QPainterPath()
        x=rect.center().x()-fm.horizontalAdvance(text)/2
        y=rect.center().y()+(fm.ascent()-fm.descent())/2
        path.addText(QPointF(x,y),font,text); p.fillPath(path,QColor(color))
    def draw(self,p,d=None):
        d=d or self.doc.d; s=d['style']; p.save(); p.setRenderHint(p.RenderHint.Antialiasing)
        for layer in d['layers']:
            if not layer['visible']: continue
            name=layer['name']; p.save()
            if name=='Фон' and not s['transparent']: p.fillRect(self.rect(d),QColor(s['background']))
            elif name=='Рамка' and s['frame']:
                p.setOpacity(s['frame_opacity']); w=s['frame_width']; gap=s['frame_gap']
                rect=QRectF(-w-gap,-w-gap,640+2*(w+gap),640+2*(w+gap))
                if s['frame_shadow']:
                    p.setPen(Qt.NoPen); p.setBrush(QColor(0,0,0,50)); p.drawRoundedRect(rect.translated(5,7),s['frame_radius'],s['frame_radius'])
                p.setPen(QPen(QColor(s['frame_color']),w)); p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(rect.adjusted(w/2,w/2,-w/2,-w/2),s['frame_radius'],s['frame_radius'])
                if s['frame_texture']:
                    clip=QPainterPath(); clip.addRect(rect); clip.addRect(QRectF(-gap,-gap,640+gap*2,640+gap*2)); p.setClipPath(clip)
                    self.image(p,self.resource(s['frame_texture']),rect); p.setClipping(False)
                if s['frame_kind']!='Одинарная':
                    p.setPen(QPen(QColor(s['frame_color']),max(1,w/5))); p.drawRect(rect.adjusted(-4,-4,4,4))
            elif name=='Клетки':
                p.setOpacity(s['board_opacity'])
                for sq in chess.SQUARES:
                    x,y=square_xy(sq,s['flipped']); r=QRectF(x,y,80,80); color=s['dark'] if is_dark(sq) else s['light']
                    brush=QBrush(QColor(color))
                    if s['gradient']:
                        g=QLinearGradient(r.topLeft(),r.bottomRight()); g.setColorAt(0,QColor(color)); g.setColorAt(1,QColor(s['gradient_end'])); brush=QBrush(g)
                    p.fillRect(r,brush)
                    key=s['dark_texture'] if is_dark(sq) else s['light_texture']
                    if key:
                        p.save(); p.setClipRect(r); self.image(p,self.resource(key),r); p.restore()
                if s['board_image']: self.image(p,self.resource(s['board_image']),QRectF(0,0,640,640))
                if s['grid']:
                    p.setPen(QPen(QColor(s['grid_color']),s['grid_width']))
                    for i in range(9):p.drawLine(QPointF(i*80,0),QPointF(i*80,640));p.drawLine(QPointF(0,i*80),QPointF(640,i*80))
            elif name=='Координаты' and s['coords']!='Нет':
                f=QFont(s['font']); f.setPointSizeF(s['font_size']); f.setBold(s['font_bold']); f.setItalic(s['font_italic'])
                off=s['coord_offset']; inside=s['coords']=='Внутри'
                for i in range(8):
                    letter=chr(97+(7-i if s['flipped'] else i)); num=str(i+1 if s['flipped'] else 8-i)
                    if s['letters']:
                        self.text(p,QRectF(i*80,610 if inside else 640+off-15,80,30),letter,f,s['coord_color'])
                        if s['sides']=='Четыре': self.text(p,QRectF(i*80,0 if inside else -off-15,80,30),letter,f,s['coord_color'])
                    if s['numbers'] and s['sides']!='Одна':
                        self.text(p,QRectF(0 if inside else -off-15,i*80,30,80),num,f,s['coord_color'])
                        if s['sides']=='Четыре': self.text(p,QRectF(610 if inside else 640+off-15,i*80,30,80),num,f,s['coord_color'])
            elif name=='Фигуры':
                b=chess.Board(d['fen'])
                for sq,piece in b.piece_map().items():
                    ov=d['piece_overrides'].get(str(sq),{}); x,y=square_xy(sq,s['flipped'])
                    scale=ov.get('scale',s['piece_scale'])*(s['white_scale'] if piece.color else s['black_scale']); size=scale*80
                    r=QRectF(x+40-size/2+ov.get('dx',s['piece_dx']),y+40-size/2+ov.get('dy',s['piece_dy']),size,size)
                    p.setOpacity(ov.get('opacity',s['piece_opacity']))
                    custom=d['sets'].get(s['piece_set'],{}).get(piece.symbol())
                    self.image(p,self.resource(custom) if custom else builtin_svg(piece.symbol(),s['piece_set']),r)
            else:
                for o in d['objects']:
                    if o['layer']==name: self.object(p,o,s['flipped'])
            p.restore()
        p.restore()
    def object(self,p,o,flipped=False):
        p.save(); p.setOpacity(o.get('opacity',0.85))
        # Annotation coordinates are white-oriented board coordinates, and rotate with the board.
        pts=[QPointF(640-x,640-y) if flipped else QPointF(x,y) for x,y in o['points']]
        if not pts: p.restore(); return
        a=pts[0]; b=pts[-1]; color=QColor(o.get('color','#e04c51')); width=o.get('width',5)
        pen=QPen(color,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin)
        if o.get('dash')=='Пунктир':pen.setStyle(Qt.DashLine)
        if o.get('dash')=='Точки':pen.setStyle(Qt.DotLine)
        p.setPen(pen); p.setBrush(Qt.NoBrush); kind=o['kind']; r=QRectF(a,b).normalized(); path=QPainterPath(a)
        if kind in ('arrow','line','poly','curve','arc','knight'):
            if kind=='knight':path.lineTo(QPointF(a.x(),b.y()));path.lineTo(b)
            elif kind in ('curve','arc'):
                ctrl=pts[1] if len(pts)>2 else QPointF((a.x()+b.x())/2-(b.y()-a.y())*.3,(a.y()+b.y())/2+(b.x()-a.x())*.3)
                path.quadTo(ctrl,b)
            else:
                for v in pts[1:]:path.lineTo(v)
            if o.get('outline'):
                p.setPen(QPen(QColor(o.get('outline_color','#ffffff')),width+4,pen.style(),Qt.RoundCap,Qt.RoundJoin));p.drawPath(path);p.setPen(pen)
            p.drawPath(path)
            if kind!='line' and o.get('head','Треугольник')!='Нет':
                def head(t,back):
                    tip=path.pointAtPercent(t); near=path.pointAtPercent(back); angle=math.atan2(tip.y()-near.y(),tip.x()-near.x()); n=o.get('head_size',20)
                    if o.get('head')=='Круг':p.setBrush(color);p.drawEllipse(tip,n/3,n/3);return
                    v1=tip-QPointF(n*math.cos(angle-.48),n*math.sin(angle-.48)); v2=tip-QPointF(n*math.cos(angle+.48),n*math.sin(angle+.48))
                    h=QPainterPath(tip);h.lineTo(v1)
                    if o.get('head')=='Открытый':h.moveTo(tip);h.lineTo(v2);p.drawPath(h)
                    else:h.lineTo(v2);h.closeSubpath();p.fillPath(h,color)
                head(1,.97)
                if o.get('double'):head(0,.03)
        elif kind in ('rect','highlight','outline'):
            if kind=='highlight':p.setPen(Qt.NoPen);p.setBrush(color)
            p.drawRect(r)
        elif kind in ('ellipse','circle'):p.drawEllipse(r)
        elif kind=='cross':p.drawLine(r.topLeft(),r.bottomRight());p.drawLine(r.bottomLeft(),r.topRight())
        elif kind=='check':
            path.moveTo(r.left(),r.center().y());path.lineTo(r.center().x(),r.bottom());path.lineTo(r.right(),r.top());p.drawPath(path)
        elif kind=='image':self.image(p,self.resource(o['resource']),r)
        elif kind=='text':
            f=QFont(o.get('font','DejaVu Sans')); f.setPointSizeF(o.get('font_size',24));f.setBold(o.get('bold',False))
            self.text(p,r,o.get('text',''),f,o.get('color','#222222'))
        p.restore()
