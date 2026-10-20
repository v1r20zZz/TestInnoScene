import copy, math
from PySide6.QtCore import Qt,QRectF,QPointF,Signal
from PySide6.QtGui import QPainter,QPen,QColor
from PySide6.QtWidgets import QGraphicsView,QGraphicsScene,QGraphicsItem
from .model import square_at,square_xy

class BoardItem(QGraphicsItem):
    def __init__(self,view):super().__init__();self.view=view
    def boundingRect(self):return self.view.window.renderer.rect().adjusted(-20,-20,20,20)
    def paint(self,p,option,widget=None):self.view.window.renderer.draw(p)

class Canvas(QGraphicsView):
    position=Signal(str)
    def __init__(self,window):
        super().__init__();self.window=window;self.setScene(QGraphicsScene(self));self.item=BoardItem(self);self.scene().addItem(self.item)
        self.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform);self.setBackgroundBrush(QColor('#dce3df'))
        self.setMouseTracking(True);self.setAcceptDrops(True);self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.start=None;self.selected=None;self.panning=False;self.points=[];self.pending=None;self.handle=None
    def refresh(self):
        self.item.prepareGeometryChange();self.scene().setSceneRect(self.item.boundingRect());self.viewport().update()
    def fit(self):
        self.fitInView(self.item.boundingRect(),Qt.KeepAspectRatio);self.window.zoomlabel.setText(f'{self.transform().m11()*100:.0f}%')
    def wheelEvent(self,e):
        scale=1.15 if e.angleDelta().y()>0 else 1/1.15
        if .1<self.transform().m11()*scale<8:self.scale(scale,scale)
        self.window.zoomlabel.setText(f'{self.transform().m11()*100:.0f}%')
    def coord(self,e):return self.mapToScene(e.position().toPoint())
    def canonical(self,p):return QPointF(640-p.x(),640-p.y()) if self.window.doc.d['style']['flipped'] else p
    def snapped(self,p):
        if not self.window.snap.isChecked():return p
        return QPointF(math.floor(p.x()/80)*80+40,math.floor(p.y()/80)*80+40)
    def object_rect(self,o):
        ps=o['points'];return QRectF(QPointF(min(x for x,y in ps)-10,min(y for x,y in ps)-10),QPointF(max(x for x,y in ps)+10,max(y for x,y in ps)+10))
    def locked(self,name):return any(x['name']==name and (x['locked'] or not x['visible']) for x in self.window.doc.d['layers'])
    def mousePressEvent(self,e):
        if e.button()==Qt.MiddleButton:self.panning=True;self.last=e.position().toPoint();self.setCursor(Qt.ClosedHandCursor);return
        if e.button() not in (Qt.LeftButton,Qt.RightButton):return
        p=self.coord(e);self.start=p;self.pending=None;w=self.window;d=w.doc.d
        tool='arrow' if e.button()==Qt.RightButton else w.tool
        self.active_tool=tool;self.source=square_at(p.x(),p.y(),d['style']['flipped'])
        self.handle=None
        if tool=='select' and self.selected and self.selected[0]=='object':
            index=self.selected[1]
            if index<len(d['objects']):
                obj=d['objects'][index]
                if not self.locked(obj['layer']):
                    cp=self.canonical(p)
                    for n,(x,y) in enumerate(obj['points']):
                        if (cp-QPointF(x,y)).manhattanLength()<12/max(self.transform().m11(),.1):
                            self.handle=(index,n);self.original_points=copy.deepcopy(obj['points']);return
        if tool=='select':
            self.selected=None;cp=self.canonical(p)
            for i in reversed(range(len(d['objects']))):
                o=d['objects'][i]
                if not self.locked(o['layer']) and self.object_rect(o).contains(cp):self.selected=('object',i);break
            if self.selected is None and self.source is not None and not self.locked('Фигуры'):
                import chess
                if chess.Board(d['fen']).piece_at(self.source):self.selected=('piece',self.source)
            w.show_selected();self.viewport().update()
        elif tool=='piece' and self.source is not None and not self.locked('Фигуры'):
            w.doc.place(self.source,w.piece_symbol);w.commit('Разместить фигуру')
        elif tool=='erase':
            if self.source is not None and not self.locked('Фигуры'):w.doc.place(self.source,None);w.commit('Удалить фигуру')
        elif tool in ('poly','line') and w.multi.isChecked():
            self.points.append(self.canonical(self.snapped(p)));self.start=None
    def mouseMoveEvent(self,e):
        p=self.coord(e);sq=square_at(p.x(),p.y(),self.window.doc.d['style']['flipped'])
        import chess
        self.position.emit(chess.square_name(sq) if sq is not None else '—')
        if self.panning:
            delta=e.position().toPoint()-self.last;self.last=e.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x());self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y());return
        if self.handle is not None:
            i,n=self.handle;cp=self.canonical(self.snapped(p));self.window.doc.d['objects'][i]['points'][n]=[cp.x(),cp.y()];self.viewport().update();return
        if self.start and self.active_tool not in ('select','piece','erase'):
            self.pending=self.make_object(self.start,p);self.viewport().update()
    def make_object(self,a,b):
        w=self.window;tool=self.active_tool
        if tool in ('highlight','outline'):
            a=QPointF(math.floor(a.x()/80)*80,math.floor(a.y()/80)*80);b=QPointF(math.floor(b.x()/80)*80+80,math.floor(b.y()/80)*80+80)
        elif tool not in ('text','ellipse','circle','rect','cross','check'):
            a=self.snapped(a);b=self.snapped(b)
        a=self.canonical(a);b=self.canonical(b)
        if (a-b).manhattanLength()<5:b=a+QPointF(60,60)
        layer='Стрелки' if tool in ('arrow','poly','curve','arc','knight') else 'Подсветка' if tool in ('highlight','outline') else 'Текст' if tool=='text' else 'Графика'
        return dict(kind=tool,layer=layer,points=[[a.x(),a.y()],[b.x(),b.y()]],color=w.ann_color,width=w.ann_width.value(),opacity=w.ann_opacity.value(),
            dash=w.dash.currentText(),head=w.head.currentText(),head_size=w.head_size.value(),double=w.double.isChecked(),outline=w.contour.isChecked(),text='',font_size=24)
    def mouseReleaseEvent(self,e):
        if self.panning:self.panning=False;self.unsetCursor();return
        if self.start is None:return
        w=self.window;p=self.coord(e);tool=self.active_tool
        try:
            if self.handle is not None:
                self.handle=None;w.commit('Изменить узел обозначения');return
            if tool=='select' and self.selected and (p-self.start).manhattanLength()>5:
                typ,index=self.selected
                if typ=='piece':
                    target=square_at(p.x(),p.y(),w.doc.d['style']['flipped'])
                    if target is not None:
                        import chess
                        promotion=chess.QUEEN;piece=chess.Board(w.doc.d['fen']).piece_at(index)
                        if w.doc.d['legal'] and piece and piece.piece_type==chess.PAWN and chess.square_rank(target) in (0,7):
                            from PySide6.QtWidgets import QInputDialog
                            name,ok=QInputDialog.getItem(w,'Превращение пешки','Выберите фигуру',['Ферзь','Ладья','Слон','Конь'],0,False)
                            if not ok:return
                            promotion={'Ферзь':chess.QUEEN,'Ладья':chess.ROOK,'Слон':chess.BISHOP,'Конь':chess.KNIGHT}[name]
                        w.doc.move(index,target,promotion);self.selected=('piece',target);w.commit('Переместить фигуру')
                else:
                    delta=self.canonical(p)-self.canonical(self.start);o=w.doc.d['objects'][index]
                    o['points']=[[x+delta.x(),y+delta.y()] for x,y in o['points']];w.commit('Переместить объект')
            elif tool not in ('select','piece','erase'):
                obj=self.make_object(self.start,p)
                if not self.locked(obj['layer']):
                    if tool=='text':
                        from PySide6.QtWidgets import QInputDialog
                        txt,ok=QInputDialog.getText(w,'Надпись','Текст:')
                        if not ok:return
                        obj['text']=txt
                    w.doc.d['objects'].append(obj);self.selected=('object',len(w.doc.d['objects'])-1);w.commit('Добавить обозначение')
        except Exception as exc:w.error(exc)
        finally:self.start=None;self.pending=None;self.viewport().update()
    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Escape:
            if self.handle is not None:
                self.window.doc.d['objects'][self.handle[0]]['points']=self.original_points;self.handle=None
            self.points=[];self.start=None;self.pending=None;self.selected=None;self.viewport().update();return
        if e.key() in (Qt.Key_Return,Qt.Key_Enter) and len(self.points)>1:
            self.active_tool='poly';o=self.make_object(QPointF(0,0),QPointF(80,80));o['points']=[[p.x(),p.y()] for p in self.points]
            if not self.locked('Стрелки'):self.window.doc.d['objects'].append(o);self.window.commit('Ломаная стрелка')
            self.points=[];return
        super().keyPressEvent(e)
    def drawForeground(self,p,rect):
        if self.pending:self.window.renderer.object(p,self.pending,self.window.doc.d['style']['flipped'])
        if self.selected:
            typ,index=self.selected;d=self.window.doc.d
            if typ=='piece':x,y=square_xy(index,d['style']['flipped']);r=QRectF(x,y,80,80)
            elif index<len(d['objects']):
                r=self.object_rect(d['objects'][index])
                if d['style']['flipped']:r=QRectF(640-r.right(),640-r.bottom(),r.width(),r.height())
            else:return
            p.setPen(QPen(QColor('#f4aa35'),2,Qt.DashLine));p.drawRect(r)
            if typ=='object' and not self.locked(d['objects'][index]['layer']):
                p.setPen(QPen(QColor('#256fbe'),1));p.setBrush(QColor('white'));radius=4/max(self.transform().m11(),.1)
                for x,y in d['objects'][index]['points']:
                    pt=QPointF(640-x,640-y) if d['style']['flipped'] else QPointF(x,y);p.drawRect(QRectF(pt.x()-radius,pt.y()-radius,radius*2,radius*2))
    def dragEnterEvent(self,e):
        if e.mimeData().hasText() and len(e.mimeData().text())==1 and e.mimeData().text() in 'KQRBNPkqrbnp':e.acceptProposedAction()
    def dragMoveEvent(self,e):e.acceptProposedAction()
    def dropEvent(self,e):
        if self.locked('Фигуры'):return
        p=self.mapToScene(e.position().toPoint());sq=square_at(p.x(),p.y(),self.window.doc.d['style']['flipped'])
        if sq is not None:self.window.doc.place(sq,e.mimeData().text());self.window.commit('Разместить фигуру');e.acceptProposedAction()
