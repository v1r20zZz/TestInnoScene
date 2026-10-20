import copy, math
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QCheckBox,QSpinBox,QDoubleSpinBox,QLineEdit,QPushButton,QScrollArea,QFileDialog,QMessageBox,QGroupBox)
from .model import Document
from .render import Renderer
from .export import raster
from .publishing import DEFAULT_LAYOUT,geometry,preview_page
from .preflight import inspect_document

class ExportStudio(QDialog):
    def __init__(self,window,pages=False,cmyk=False):
        super().__init__(window);self.window=window;self.pages=pages;self.doc=Document();self.doc.data=copy.deepcopy(window.doc.data);self.doc.resources=window.doc.resources
        self.setWindowTitle('Студия публикации — учебные листы' if pages else 'Студия экспорта — диаграмма');self.resize(1140,830)
        outer=QVBoxLayout(self);body=QHBoxLayout();outer.addLayout(body,1);box=QGroupBox('Параметры публикации' if pages else 'Параметры диаграммы');form=QFormLayout(box);box.setFixedWidth(330);body.addWidget(box)
        self.controls={};self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.timeout.connect(self.update_preview)
        def field(key,title,value,lo=0,hi=1000):
            if isinstance(value,bool):w=QCheckBox();w.setChecked(value);w.toggled.connect(self.schedule)
            elif isinstance(value,(int,float)):
                w=QSpinBox() if isinstance(value,int) else QDoubleSpinBox();w.setRange(lo,hi);w.setValue(value);w.valueChanged.connect(self.schedule)
            else:w=QLineEdit(str(value));w.textChanged.connect(self.schedule)
            self.controls[key]=w;form.addRow(title,w)
        if pages:
            opts={**DEFAULT_LAYOUT,**self.doc.data.get('publication',{})};self.paper=QComboBox();self.paper.addItems(['A4','A5']);self.paper.setCurrentText(opts['paper']);form.addRow('Бумага',self.paper);self.paper.currentTextChanged.connect(self.schedule)
            for key,title,lo,hi in [('cols','Столбцы',1,4),('rows','Строки',1,6),('margin','Поля, мм',3,40),('gap','Интервал, мм',0,25),('answer_lines','Строк для ответа',0,5)]:field(key,title,opts[key],lo,hi)
            for key,title in [('landscape','Альбомная страница'),('captions','Названия диаграмм'),('numbering','Нумерация заданий'),('side_to_move','Указывать сторону хода'),('title','Заголовок'),('footer','Подпись внизу')]:field(key,title,opts[key])
        else:
            s=self.doc.d['style'];field('board_mm','Сторона доски, мм',float(s['board_mm']),10,1000);field('dpi','Разрешение, DPI',int(s['dpi']),72,2400);field('transparent','Прозрачный фон',s['transparent'])
        self.format=QComboBox();self.format.addItems(['PDF','CMYK PDF'] if pages else ['PNG','SVG','PDF','TIFF','JPEG','BMP','CMYK TIFF','CMYK PDF']);self.format.setCurrentText('CMYK PDF' if cmyk and pages else 'CMYK TIFF' if cmyk else 'PDF' if pages else 'PNG');form.addRow('Формат',self.format);self.format.currentTextChanged.connect(self.schedule)
        self.info=QLabel();self.info.setWordWrap(True);form.addRow(self.info);self.warning=QLabel();self.warning.setWordWrap(True);form.addRow(self.warning)
        right=QVBoxLayout();body.addLayout(right,1);nav=QHBoxLayout();right.addLayout(nav);self.previous=QPushButton('←');self.next=QPushButton('→');self.page=QSpinBox();self.page.setRange(1,1);self.page.valueChanged.connect(self.schedule)
        nav.addWidget(QLabel('Предпросмотр'));nav.addStretch();nav.addWidget(self.previous);nav.addWidget(self.page);nav.addWidget(self.next);self.previous.clicked.connect(lambda:self.page.setValue(self.page.value()-1));self.next.clicked.connect(lambda:self.page.setValue(self.page.value()+1))
        self.preview=QLabel();self.preview.setAlignment(Qt.AlignCenter);sc=QScrollArea();sc.setWidgetResizable(True);sc.setWidget(self.preview);right.addWidget(sc,1)
        foot=QHBoxLayout();outer.addLayout(foot);hint=QLabel('Предпросмотр уменьшен. PDF и SVG сохраняют векторную геометрию.');foot.addWidget(hint);foot.addStretch();cancel=QPushButton('Закрыть');cancel.clicked.connect(self.reject);foot.addWidget(cancel);self.savebutton=QPushButton('Экспортировать…');self.savebutton.setDefault(True);self.savebutton.clicked.connect(self.save);foot.addWidget(self.savebutton)
        self.update_preview()
    def schedule(self,*args):self.delay.start(180)
    def values(self):
        data={}
        for k,w in self.controls.items():data[k]=w.isChecked() if isinstance(w,QCheckBox) else w.value() if isinstance(w,(QSpinBox,QDoubleSpinBox)) else w.text()
        if self.pages:data['paper']=self.paper.currentText()
        return data
    def update_preview(self):
        try:
            values=self.values();self.warnings=[]
            if self.pages:
                o,w,h,cw,ch,*_=geometry(values);count=math.ceil(len(self.doc.data['diagrams'])/(o['cols']*o['rows']));self.page.setMaximum(count);im=preview_page(self.doc,values,self.page.value()-1,650)
                self.info.setText(f'{w:g} × {h:g} мм · {count} стр.\n{len(self.doc.data["diagrams"])} диаграмм');items=self.doc.data['diagrams']
            else:
                self.doc.d['style'].update(values);rect=Renderer(self.doc).rect();mm=values['board_mm']/640;w,h=rect.width()*mm,rect.height()*mm
                dpi=min(100,650/(max(w,h)/25.4));pil=raster(Renderer(self.doc),self.doc.d,dpi);im=QImage(pil.tobytes(),pil.width,pil.height,pil.width*4,QImage.Format_RGBA8888).copy();items=[self.doc.d]
                self.info.setText(f'Холст: {w:.1f} × {h:.1f} мм\nРастр: {round(w/25.4*values["dpi"])} × {round(h/25.4*values["dpi"])} px');self.page.setMaximum(1)
            self.previous.setEnabled(self.page.value()>1);self.next.setEnabled(self.page.value()<self.page.maximum())
            for d in items:
                self.warnings.extend(inspect_document(self.doc,d))
                if len(self.warnings)>8:break
            if self.format.currentText().startswith('CMYK'):
                from .export import profile_bytes
                profile_bytes(self.doc,self.doc.d)
            if not self.pages and values['transparent'] and self.format.currentText() in ('JPEG','BMP'):self.warnings.append('В этом формате прозрачность заменяется белым фоном.')
            self.warning.setText('\n'.join(self.warnings[:8]) or 'Проверка: явных проблем не найдено.');self.preview.setPixmap(QPixmap.fromImage(im));self.savebutton.setEnabled(True)
        except Exception as exc:self.warning.setText(str(exc));self.savebutton.setEnabled(False)
    def save(self):
        self.update_preview()
        if not self.savebutton.isEnabled():return
        fmt=self.format.currentText();ext={'JPEG':'jpg'}.get(fmt.split()[-1],fmt.split()[-1].lower());name='Учебный лист' if self.pages else self.doc.d['name']
        path,_=QFileDialog.getSaveFileName(self,'Сохранить публикацию',name+'.'+ext,fmt+' (*.'+ext+')')
        if not path:return
        if not Path(path).suffix:path+='.'+ext
        if Path(path).suffix.lower()!='.'+ext:QMessageBox.warning(self,'Формат','Расширение файла должно быть .'+ext);return
        values=self.values()
        if self.pages:self.window.doc.data['publication']=values;self.window.commit('Параметры публикации')
        else:self.window.doc.d['style'].update(values);self.window.commit('Параметры экспорта')
        spec={'kind':'pages' if self.pages else 'diagrams','outputs':[dict(path=path,index=self.window.doc.data['active'],cmyk=fmt.startswith('CMYK'))]}
        if self.pages:spec['layout']=values
        if self.window.start_export(spec):
            if not self.pages:self.window.last_export=(path,fmt.startswith('CMYK'))
            self.accept()
