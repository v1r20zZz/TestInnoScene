"""Millimetre-based page composition shared by preview and vector PDF."""
import math, os, tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QSizeF, QMarginsF, QPointF
from PySide6.QtGui import QPainter, QImage, QPdfWriter, QPageSize, QColor, QPen, QFont, QFontMetricsF, QPainterPath
from .render import Renderer
from .export import exact_pdf_size, cmyk_pdf, profile_bytes
DEFAULT_LAYOUT=dict(paper='A4',landscape=False,cols=2,rows=3,margin=12.0,gap=8.0,title='Шахматные задания',footer='',numbering=True,side_to_move=True,answer_lines=2,captions=True)
def geometry(options):
    o={**DEFAULT_LAYOUT,**options};w,h=(210.,297.) if o['paper']=='A4' else (148.,210.)
    if o['landscape']:w,h=h,w
    cols,rows=int(o['cols']),int(o['rows']);margin=float(o['margin']);gap=float(o['gap'])
    if not 1<=cols<=4 or not 1<=rows<=6 or not 0<=o['answer_lines']<=5:raise ValueError('Недопустимая сетка страницы')
    if not 3<=margin<=40 or not 0<=gap<=25:raise ValueError('Недопустимые поля или интервал')
    header=14 if o['title'] else 0;cw=(w-2*margin-(cols-1)*gap)/cols;ch=(h-2*margin-header-8-(rows-1)*gap)/rows
    top=(10 if o['captions'] else 0)+(5 if o['side_to_move'] else 0);bottom=o['answer_lines']*5
    if min(cw,ch-top-bottom)<22:raise ValueError('Диаграммы слишком малы: уменьшите сетку, поля или число строк для ответа')
    return o,w,h,cw,ch,header,top,bottom

def label(p,rect,text,size=3.2,bold=False,center=False,max_lines=2):
    font=QFont('DejaVu Sans');font.setPixelSize(round(size*10));font.setBold(bold);fm=QFontMetricsF(font)
    lines=[];line=''
    for word in str(text).replace('\n',' ').split():
        trial=(line+' '+word).strip()
        if line and fm.horizontalAdvance(trial)>rect.width()*10:lines.append(line);line=word
        else:line=trial
    if line:lines.append(line)
    if len(lines)>max_lines:lines=lines[:max_lines-1]+[' '.join(lines[max_lines-1:])]
    p.save();p.setClipRect(rect);p.translate(rect.x(),rect.y());p.scale(.1,.1)
    for i,line in enumerate(lines):
        line=fm.elidedText(line,Qt.ElideRight,rect.width()*10);path=QPainterPath();x=(rect.width()*10-fm.horizontalAdvance(line))/2 if center else 0
        path.addText(QPointF(x,fm.ascent()+i*(size*12)),font,line);p.fillPath(path,QColor('#24352f'))
    p.restore()

def paint_page(p,doc,options,page):
    import chess
    o,w,h,cw,ch,header,top,bottom=geometry(options);m=o['margin'];gap=o['gap'];per=o['cols']*o['rows'];total=math.ceil(len(doc.data['diagrams'])/per)
    p.fillRect(QRectF(0,0,w,h),QColor('white'));p.setRenderHint(QPainter.Antialiasing)
    if header:label(p,QRectF(m,m,w-2*m,11),o['title'],5.4,True,max_lines=1)
    renderer=Renderer(doc)
    for slot,d in enumerate(doc.data['diagrams'][page*per:(page+1)*per]):
        x=m+(slot%o['cols'])*(cw+gap);y=m+header+(slot//o['cols'])*(ch+gap)
        if o['captions']:label(p,QRectF(x,y,cw,10),(f'{page*per+slot+1}. ' if o['numbering'] else '')+d['name'],3.2,True)
        if o['side_to_move']:label(p,QRectF(x,y+(10 if o['captions'] else 0),cw,5),'Ход белых' if chess.Board(d['fen']).turn else 'Ход чёрных',2.8)
        rect=renderer.rect(d);scale=min(cw/rect.width(),(ch-top-bottom)/rect.height())
        p.save();p.translate(x+(cw-rect.width()*scale)/2,y+top);p.scale(scale,scale);p.translate(-rect.x(),-rect.y());renderer.draw(p,d);p.restore()
        p.setPen(QPen(QColor('#b3bcb8'),.2))
        for line in range(o['answer_lines']):
            yy=y+ch-bottom+(line+1)*5-1;p.drawLine(QPointF(x,yy),QPointF(x+cw,yy))
    label(p,QRectF(m,h-m-4,w-2*m-20,6),o['footer'],2.6,max_lines=1);label(p,QRectF(w-m-20,h-m-4,20,6),f'{page+1} / {total}',2.6,center=True,max_lines=1)

def preview_page(doc,options,page,width=760):
    _,w,h,*_=geometry(options);im=QImage(width,round(width*h/w),QImage.Format_ARGB32);im.fill(Qt.white);p=QPainter(im)
    try:p.scale(width/w,width/w);paint_page(p,doc,options,page)
    finally:p.end()
    return im

def export_publication(doc,path,options,cmyk=False):
    o,w,h,*_=geometry(options);profile=profile_bytes(doc,doc.d) if cmyk else None;path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.chess-pages-',dir=path.parent) as td:
        raw=Path(td)/'rgb.pdf';writer=QPdfWriter(str(raw));writer.setResolution(1200);writer.setPageSize(QPageSize(QSizeF(w,h),QPageSize.Millimeter));writer.setPageMargins(QMarginsF(0,0,0,0));writer.setTitle(o['title']);writer.setCreator('Конструктор шахматных диаграмм 0.2.0');p=QPainter(writer)
        try:
            for page in range(math.ceil(len(doc.data['diagrams'])/(o['cols']*o['rows']))):
                if page:writer.newPage()
                p.save();p.scale(writer.width()/w,writer.height()/h);paint_page(p,doc,o,page);p.restore()
        finally:p.end();del p;del writer
        exact_pdf_size(raw,w,h);output=raw
        if cmyk:output=Path(td)/'cmyk.pdf';cmyk_pdf(raw,output,profile,doc.d['style']['intent'])
        os.replace(output,path)
