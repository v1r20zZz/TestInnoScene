from __future__ import annotations
import copy, io, json, os, re, sys, tempfile
from pathlib import Path
import chess
from PySide6.QtCore import Qt,QTimer,QSettings,QMimeData,QSize,QByteArray
from PySide6.QtGui import QAction,QKeySequence,QColor,QIcon,QPixmap,QDrag,QFontDatabase,QImage,QPainter
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QDockWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,QLabel,QPushButton,QToolButton,QLineEdit,QComboBox,QCheckBox,QDoubleSpinBox,QSpinBox,QTabWidget,QScrollArea,QListWidget,QListWidgetItem,QFileDialog,QMessageBox,QInputDialog,QColorDialog,QDialog,QDialogButtonBox,QTextBrowser,QProgressDialog,QStyle,QToolBar)
from .model import Document,diagram,STYLE
from .render import Renderer,builtin_svg
from .canvas import Canvas
from .export import export_file,raster,contact_sheet,profile_bytes,softproof

APP='Конструктор шахматных диаграмм'
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))

class PieceButton(QToolButton):
    def __init__(self,symbol,window):
        super().__init__();self.symbol=symbol;self.window=window;self.setFixedSize(61,61)
        self.setIconSize(QSize(49,49));self.setToolTip(chess.Piece.from_symbol(symbol).unicode_symbol()+' — нажмите, затем клетку; либо перетащите')
        pm=QPixmap(80,80);pm.fill(Qt.transparent);p=QPainter(pm);window.renderer.image(p,builtin_svg(symbol,'Классический'),__import__('PySide6.QtCore',fromlist=['QRectF']).QRectF(0,0,80,80));p.end();self.setIcon(QIcon(pm))
        self.clicked.connect(lambda:window.choose_piece(symbol))
    def mousePressEvent(self,e):self.origin=e.position().toPoint();super().mousePressEvent(e)
    def mouseMoveEvent(self,e):
        if e.buttons()&Qt.LeftButton and (e.position().toPoint()-self.origin).manhattanLength()>10:
            drag=QDrag(self);m=QMimeData();m.setText(self.symbol);drag.setMimeData(m);drag.setPixmap(self.icon().pixmap(48,48));drag.exec(Qt.CopyAction)

class Window(QMainWindow):
    def __init__(self,recover=True):
        super().__init__();self.doc=Document();self.renderer=Renderer(self.doc);self.settings=QSettings('ChessDiagram','Constructor')
        self.tool='select';self.piece_symbol='P';self.ann_color='#df504f';self.busy=False;self.controls={};self.actions={}
        self.store=Path(os.environ.get('APPDATA',Path.home()/'.local/share'))/'ChessDiagramConstructor';self.store.mkdir(parents=True,exist_ok=True)
        self.recovery=self.store/f'recovery-{os.getpid()}-{__import__("uuid").uuid4().hex[:8]}.chessdiagram';self.export_job=None;self.resize(1450,960)
        self.canvas=Canvas(self);self.setCentralWidget(self.canvas)
        self.zoomlabel=QLabel('100%');self.positionlabel=QLabel('—');self.infolabel=QLabel('')
        self.statusBar().addWidget(self.infolabel,1);self.statusBar().addPermanentWidget(self.positionlabel);self.statusBar().addPermanentWidget(self.zoomlabel)
        self.canvas.position.connect(self.positionlabel.setText)
        self.build_tools();self.build_properties();self.build_collections();self.build_menus();self.build_toolbar()
        self.resizeDocks([self.bottomdock],[175],Qt.Vertical)
        self.resizeDocks([self.leftdock,self.rightdock],[275,355],Qt.Horizontal)
        self.default_layout=self.saveState()
        if self.settings.value('layout'):self.restoreState(self.settings.value('layout'))
        self.theme(self.settings.value('theme','Светлая'));self.refresh();QTimer.singleShot(50,self.canvas.fit)
        self.timer=QTimer(self);self.timer.timeout.connect(self.autosave);self.timer.start(60000)
        if recover:self.restore_recovery()
    def restore_recovery(self):
        from PySide6.QtCore import QLockFile
        self.session_lock=QLockFile(str(self.recovery)+'.lock');self.session_lock.setStaleLockTime(0);self.session_lock.tryLock(0)
        for path in sorted(self.store.glob('recovery*.chessdiagram'),key=lambda p:p.stat().st_mtime,reverse=True):
            if path==self.recovery:continue
            lock=QLockFile(str(path)+'.lock');lock.setStaleLockTime(0)
            if not lock.tryLock(0):continue
            try:
                if QMessageBox.question(self,'Восстановление','Найдена резервная копия после незавершённого сеанса. Восстановить?')==QMessageBox.Yes:
                    self.doc.load(path);self.doc.path=None;self.doc.dirty=True;self.load_fonts();self.refresh();path.unlink();break
            except Exception as e:self.error(e)
            finally:lock.unlock()
    def build_toolbar(self):
        bar=QToolBar('Быстрые действия',self);bar.setObjectName('quickActions');bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);self.addToolBar(bar)
        for title,icon in [('Новый проект',QStyle.SP_FileIcon),('Открыть…',QStyle.SP_DialogOpenButton),('Сохранить',QStyle.SP_DialogSaveButton),('Отменить',QStyle.SP_ArrowBack),('Повторить',QStyle.SP_ArrowForward),('Вписать в окно',QStyle.SP_TitleBarMaxButton),('RGB…',QStyle.SP_DialogApplyButton),('Страницы A4/A5',QStyle.SP_FileDialogDetailedView)]:
            action=self.actions[title];action.setIcon(self.style().standardIcon(icon));bar.addAction(action)
    def start_export(self,spec):
        if self.export_job is not None:self.error('Дождитесь завершения текущего экспорта.');return False
        from .jobs import ExportJob
        self.export_job=ExportJob(self,spec);return True
    def error(self,e):
        __import__('logging').getLogger('chessdiagram').error('%s',e);QMessageBox.warning(self,'Не удалось выполнить действие',str(e))
    def guarded(self,fn):
        def run(*args):
            try:return fn()
            except Exception as e:self.error(e)
        return run
    def action(self,menu,text,fn,shortcut=None):
        a=QAction(text,self);a.triggered.connect(self.guarded(fn));menu.addAction(a);self.actions[text]=a
        key=self.settings.value('shortcut/'+text,shortcut or '')
        if key:a.setShortcut(QKeySequence(key))
        return a
    def dock(self,title,widget,area):
        d=QDockWidget(title,self);d.setObjectName(title);d.setWidget(widget);self.addDockWidget(area,d);return d
    def button(self,layout,text,fn):
        b=QPushButton(text);b.clicked.connect(self.guarded(fn));layout.addWidget(b);return b
    def build_tools(self):
        w=QWidget();v=QVBoxLayout(w);v.setContentsMargins(12,12,12,12);v.addWidget(QLabel('ФИГУРЫ'))
        self.setcombo=QComboBox();self.setcombo.addItems(['Классический','Геометрический']);self.setcombo.currentTextChanged.connect(lambda t:self.set_style('piece_set',t));v.addWidget(self.setcombo)
        g=QGridLayout()
        for i,s in enumerate('KQRBNPkqrbnp'):g.addWidget(PieceButton(s,self),i//3,i%3)
        v.addLayout(g);self.tool_label=QLabel('Инструмент: Выбор');v.addWidget(self.tool_label)
        tools=[('Выбор / перемещение','select'),('Ластик','erase'),('Стрелка','arrow'),('Ход коня','knight'),('Кривая','curve'),('Дуга','arc'),('Ломаная','poly'),('Линия','line'),('Круг / овал','ellipse'),('Прямоугольник','rect'),('Заливка клеток','highlight'),('Обводка клеток','outline'),('Крестик','cross'),('Галочка','check'),('Текст / ! / ?','text')]
        self.toolcombo=QComboBox()
        for label,key in tools:self.toolcombo.addItem(label,key)
        self.toolcombo.currentIndexChanged.connect(lambda i:self.choose_tool(self.toolcombo.itemData(i)));v.addWidget(self.toolcombo)
        self.snap=QCheckBox('Привязка к центрам клеток');self.snap.setChecked(True);v.addWidget(self.snap)
        self.multi=QCheckBox('Ломаная по точкам • Enter — готово');v.addWidget(self.multi)
        self.button(v,'Цвет обозначений',self.pick_ann_color)
        f=QFormLayout();self.ann_width=QDoubleSpinBox();self.ann_width.setRange(.2,40);self.ann_width.setValue(6);f.addRow('Толщина',self.ann_width)
        self.ann_opacity=QDoubleSpinBox();self.ann_opacity.setRange(.01,1);self.ann_opacity.setSingleStep(.05);self.ann_opacity.setValue(.85);f.addRow('Непрозрачность',self.ann_opacity)
        self.dash=QComboBox();self.dash.addItems(['Сплошная','Пунктир','Точки']);f.addRow('Линия',self.dash)
        self.head=QComboBox();self.head.addItems(['Треугольник','Открытый','Круг','Нет']);f.addRow('Наконечник',self.head)
        self.head_size=QDoubleSpinBox();self.head_size.setRange(2,80);self.head_size.setValue(22);f.addRow('Размер',self.head_size)
        v.addLayout(f);self.double=QCheckBox('Два наконечника');v.addWidget(self.double);self.contour=QCheckBox('Двойной контур');v.addWidget(self.contour)
        self.button(v,'Начальная позиция',lambda:self.position(chess.STARTING_FEN));self.button(v,'Пустая доска',lambda:self.position(chess.Board(None).fen()))
        v.addStretch();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(w);self.leftdock=self.dock('Инструменты',scroll,Qt.LeftDockWidgetArea)
    def choose_piece(self,s):self.tool='piece';self.piece_symbol=s;self.tool_label.setText('Разместить: '+chess.Piece.from_symbol(s).unicode_symbol())
    def choose_tool(self,t):self.tool=t;self.canvas.points=[];self.tool_label.setText('Инструмент: '+self.toolcombo.currentText())
    def pick_ann_color(self):
        c=QColorDialog.getColor(QColor(self.ann_color),self)
        if c.isValid():self.ann_color=c.name()
    def property(self,form,key,title,kind=None,options=None,lo=0,hi=10000):
        default=STYLE[key]
        if options:
            w=QComboBox();w.addItems(options);w.currentTextChanged.connect(lambda val:self.set_style(key,val))
        elif isinstance(default,bool):
            w=QCheckBox();w.toggled.connect(lambda val:self.set_style(key,val))
        elif isinstance(default,(float,int)):
            w=QDoubleSpinBox();w.setDecimals(3 if 'scale' in key or 'opacity' in key else 2);w.setRange(lo,hi);w.setKeyboardTracking(False)
            w.editingFinished.connect(lambda:self.set_style(key,int(w.value()) if isinstance(default,int) else w.value()))
        elif default.startswith('#'):
            w=QPushButton();w.clicked.connect(lambda:self.color_property(key))
        else:
            w=QLineEdit();w.editingFinished.connect(lambda:self.set_style(key,w.text()))
        self.controls[key]=w;form.addRow(title,w);return w
    def tabform(self,tabs,title):
        w=QWidget();f=QFormLayout(w);f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);sc=QScrollArea();sc.setWidgetResizable(True);sc.setWidget(w);tabs.addTab(sc,title);return f
    def build_properties(self):
        tabs=QTabWidget();tabs.setMinimumWidth(335)
        f=self.tabform(tabs,'Доска')
        for k,t,lo,hi in [('board_mm','Сторона доски, мм',1,1000),('margin','Поля, ед. холста',0,500),('canvas_extra_x','Доп. ширина холста',0,2000),('canvas_extra_y','Доп. высота холста',0,2000),('board_opacity','Непрозрачность',0,1),('grid_width','Толщина сетки',.1,10)]:self.property(f,k,t,lo=lo,hi=hi)
        for k,t in [('light','Светлые клетки'),('dark','Тёмные клетки'),('background','Фон'),('grid_color','Цвет сетки'),('gradient_end','Конец градиента'),('gradient','Градиент'),('grid','Сетка'),('flipped','Со стороны чёрных'),('transparent','Прозрачный фон')]:self.property(f,k,t)
        b=QPushButton('Размер в см / px / pt');b.clicked.connect(self.physical_size);f.addRow(b)
        for key,title in [('light_texture','Текстура светлых клеток'),('dark_texture','Текстура тёмных клеток'),('board_image','Изображение всей доски')]:
            b=QPushButton(title);b.clicked.connect(self.guarded(lambda k=key:self.import_style_resource(k)));f.addRow(b)
        f=self.tabform(tabs,'Рамка')
        for k,t in [('frame','Показывать рамку'),('frame_color','Цвет'),('frame_width','Толщина'),('frame_gap','Внутренний отступ'),('frame_radius','Скругление'),('frame_shadow','Тень')]:self.property(f,k,t)
        self.property(f,'frame_opacity','Непрозрачность',hi=1);self.property(f,'frame_kind','Стиль',options=['Одинарная','Двойная'])
        b=QPushButton('Загрузить текстуру рамки');b.clicked.connect(self.guarded(lambda:self.import_style_resource('frame_texture')));f.addRow(b)
        f=self.tabform(tabs,'Координаты')
        self.property(f,'coords','Положение',options=['Снаружи','Внутри','На рамке','Нет']);self.property(f,'sides','Стороны',options=['Одна','Две','Четыре'])
        for k,t in [('letters','Буквы'),('numbers','Цифры'),('font','Шрифт'),('font_size','Размер'),('font_bold','Жирный'),('font_italic','Курсив'),('coord_color','Цвет'),('coord_offset','Отступ')]:self.property(f,k,t)
        b=QPushButton('Загрузить шрифт TTF/OTF');b.clicked.connect(self.guarded(self.import_font));f.addRow(b)
        f=self.tabform(tabs,'Фигуры')
        for k,t,lo,hi in [('piece_scale','Общий масштаб',.4,1.2),('white_scale','Множитель белых',.4,1.5),('black_scale','Множитель чёрных',.4,1.5),('piece_dx','Смещение X',-80,80),('piece_dy','Смещение Y',-80,80),('piece_opacity','Непрозрачность',0,1)]:self.property(f,k,t,lo=lo,hi=hi)
        for title,fn in [('Импорт набора из папки',self.import_set),('Импорт одной фигуры',self.import_piece),('Экспорт текущего набора',self.export_set)]:b=QPushButton(title);b.clicked.connect(self.guarded(fn));f.addRow(b)
        f=self.tabform(tabs,'Экспорт')
        self.property(f,'dpi','DPI',lo=1,hi=2400)
        self.intentcombo=QComboBox();self.intentcombo.addItems(['Перцепционный','Относительный','Насыщенность','Абсолютный']);self.intentcombo.currentIndexChanged.connect(lambda i:self.set_style('intent',i));f.addRow('Рендеринг',self.intentcombo)
        self.icclabel=QLabel('ICC-профиль не выбран');self.icclabel.setWordWrap(True);f.addRow(self.icclabel)
        for title,fn in [('Загрузить CMYK ICC',lambda:self.import_style_resource('icc')),('Цветопроба ICC',self.proof),('Экспорт RGB…',lambda:self.export_dialog(False)),('Экспорт CMYK…',lambda:self.export_dialog(True)),('Повторить последний экспорт',self.repeat_export)]:b=QPushButton(title);b.clicked.connect(self.guarded(fn));f.addRow(b)
        self.rightdock=self.dock('Свойства диаграммы',tabs,Qt.RightDockWidgetArea)
        self.selectedlabel=QLabel('Выберите фигуру или обозначение');self.selectedlabel.setWordWrap(True)
        sw=QWidget();sv=QVBoxLayout(sw);sv.addWidget(self.selectedlabel)
        for t,fn in [('Редактировать свойства',self.edit_selected),('Дублировать',self.duplicate_selected),('Удалить',self.delete_selected),('Повернуть',self.rotate_selected),('На передний план',lambda:self.order_object(True)),('На задний план',lambda:self.order_object(False))]:self.button(sv,t,fn)
        self.selecteddock=self.dock('Выбранный объект',sw,Qt.RightDockWidgetArea);self.tabifyDockWidget(self.rightdock,self.selecteddock);self.rightdock.raise_()
    def build_collections(self):
        tabs=QTabWidget();self.diagrams=QListWidget();self.diagrams.currentRowChanged.connect(self.switch_diagram)
        dw=QWidget();v=QVBoxLayout(dw);v.addWidget(self.diagrams);h=QHBoxLayout();v.addLayout(h)
        for t,fn in [('+',self.new_diagram),('Копия',self.duplicate_diagram),('Имя',self.rename_diagram),('↑',lambda:self.move_diagram(-1)),('↓',lambda:self.move_diagram(1)),('Удалить',self.delete_diagram)]:self.button(h,t,fn)
        tabs.addTab(dw,'Диаграммы');self.history=QListWidget();self.history.currentRowChanged.connect(self.history_jump);tabs.addTab(self.history,'История')
        lw=QWidget();v=QVBoxLayout(lw);self.layers=QListWidget();self.layers.itemChanged.connect(self.layer_changed);v.addWidget(self.layers)
        for t,fn in [('Блокировать / разблокировать',self.lock_layer),('Поднять',lambda:self.move_layer(1)),('Опустить',lambda:self.move_layer(-1))]:self.button(v,t,fn)
        tabs.addTab(lw,'Слои');self.bottomdock=self.dock('Проект',tabs,Qt.BottomDockWidgetArea)
    def build_menus(self):
        menus={x:self.menuBar().addMenu(x) for x in ['Файл','Правка','Вид','Доска','Фигуры','Аннотации','Шаблоны','Экспорт','Настройки','Справка']}
        def add(m,t,f,s=None):return self.action(menus[m],t,f,s)
        for t,f,s in [('Новый проект',self.new_project,'Ctrl+N'),('Открыть…',self.open_project,'Ctrl+O'),('Сохранить',self.save,'Ctrl+S'),('Сохранить как…',lambda:self.save(True),'Ctrl+Shift+S'),('Последние проекты',self.open_recent,None),('Импорт FEN',self.import_fen,None),('Импорт списка FEN',self.import_fen_list,None),('Импорт PGN',self.import_pgn,None),('Экспорт PGN',self.export_pgn,None),('Выход',self.close,'Alt+F4')]:add('Файл',t,f,s)
        add('Правка','Отменить',lambda:self.undo(-1),'Ctrl+Z');a=add('Правка','Повторить',lambda:self.undo(1),'Ctrl+Y');a.setShortcuts([QKeySequence('Ctrl+Y'),QKeySequence('Ctrl+Shift+Z')])
        for t,f,s in [('Удалить выбранное',self.delete_selected,'Delete'),('Дублировать выбранное',self.duplicate_selected,'Ctrl+D'),('Копировать диаграмму',self.copy_image,'Ctrl+Shift+C'),('Вставить изображение',self.paste_image,'Ctrl+Shift+V'),('Копировать FEN',lambda:QApplication.clipboard().setText(self.doc.d['fen']),None),('Вставить FEN',lambda:self.position(QApplication.clipboard().text()),None)]:add('Правка',t,f,s)
        add('Вид','Поиск команды…',self.command_palette,'Ctrl+K');add('Вид','Вписать в окно',self.canvas.fit,'Ctrl+0');add('Вид','Восстановить панели',lambda:self.restoreState(self.default_layout))
        for d in [self.leftdock,self.rightdock,self.selecteddock,self.bottomdock]:menus['Вид'].addAction(d.toggleViewAction())
        add('Доска','Повернуть',lambda:self.set_style('flipped',not self.doc.d['style']['flipped']),'F');add('Доска','Начальная позиция',lambda:self.position(chess.STARTING_FEN));add('Доска','Пустая доска',lambda:self.position(chess.Board(None).fen()))
        add('Доска','Сторона хода',self.choose_turn)
        add('Доска','Проверить позицию',self.validate_position);add('Доска','Включить / выключить легальные ходы',self.toggle_legal)
        add('Доска','Предыдущий ход PGN',lambda:self.goto_ply(-1),'Left');add('Доска','Следующий ход PGN',lambda:self.goto_ply(1),'Right');add('Доска','Показать ходы PGN',self.show_pgn)
        add('Доска','Выделить центр',self.highlight_center)
        add('Доска','Сохранить в избранное',self.favorite_save);add('Доска','Открыть избранную позицию',self.favorite_open)
        add('Фигуры','Импорт набора',self.import_set);add('Фигуры','Импорт одной фигуры',self.import_piece)
        add('Аннотации','Свойства выбранного объекта',self.edit_selected,'Return');add('Аннотации','Удалить все обозначения',self.clear_annotations)
        add('Шаблоны','Библиотека шаблонов',self.template_library)
        for t,f in [('Сохранить шаблон…',self.save_template),('Применить шаблон…',self.load_template),('Применить оформление ко всем',self.apply_all),('Сделать оформление стандартным',self.set_default_template)]:add('Шаблоны',t,f)
        for name in ['Учебник','Детская тетрадь','Цветная','Минималистичная','Без координат','Крупные фигуры','Чёрно-белая']:add('Шаблоны',name,lambda n=name:self.preset(n))
        for t,f,s in [('RGB…',lambda:self.export_dialog(False),'Ctrl+E'),('CMYK…',lambda:self.export_dialog(True),None),('Пакетный экспорт',self.batch_export,None),('Страницы A4/A5',self.export_pages,None),('Экспорт FEN',self.export_fen,None),('Повторить экспорт',self.repeat_export,'F5')]:add('Экспорт',t,f,s)
        add('Настройки','Светлая тема',lambda:self.theme('Светлая'));add('Настройки','Тёмная тема',lambda:self.theme('Тёмная'));add('Настройки','Горячие клавиши',self.edit_shortcuts)
        add('Справка','Руководство',self.help);add('Справка','О программе',lambda:QMessageBox.information(self,APP,'Версия 0.2.0 — предварительный выпуск\nРедактор диаграмм и учебных листов.\nКоммерческая приёмка ещё не завершена.\nGPL-3.0-or-later; лицензии — в папке LICENSES.'))
    def set_style(self,key,val):
        if self.busy or self.doc.d['style'][key]==val:return
        self.doc.d['style'][key]=val;self.commit('Настройка: '+key)
    def color_property(self,key):
        # QColorDialog supports RGB/HEX; an additional numeric CMYK input is exposed below.
        options=['RGB / HEX','CMYK (проценты)'];kind,ok=QInputDialog.getItem(self,'Цвет','Способ ввода',options,0,False)
        if not ok:return
        if kind==options[0]:
            c=QColorDialog.getColor(QColor(self.doc.d['style'][key]),self)
            if c.isValid():self.set_style(key,c.name())
        else:
            txt,ok=QInputDialog.getText(self,'CMYK','C M Y K, 0–100 (экранное приближение; экспорт через ICC):')
            if ok:
                try:
                    values=[float(x)/100 for x in txt.replace(',',' ').split()]
                    if len(values)!=4 or any(not 0<=x<=1 for x in values):raise ValueError('Введите четыре значения от 0 до 100')
                    self.set_style(key,QColor.fromCmykF(*values).name())
                except Exception as e:self.error(e)
    def physical_size(self):
        unit,ok=QInputDialog.getItem(self,'Размер доски','Единица',['мм','см','px','pt'],0,False)
        if not ok:return
        value,ok=QInputDialog.getDouble(self,'Размер доски','Сторона:',120,.1,100000,3)
        if ok:
            mm=value*{'мм':1,'см':10,'px':25.4/self.doc.d['style']['dpi'],'pt':25.4/72}[unit]
            if not 1<=mm<=1000:self.error('Размер должен быть от 1 до 1000 мм');return
            self.set_style('board_mm',mm)
    def commit(self,label):self.doc.checkpoint(label);self.refresh()
    def refresh(self):
        self.busy=True
        try:
            self.actions['Отменить'].setEnabled(self.doc.cursor>0);self.actions['Повторить'].setEnabled(self.doc.cursor<len(self.doc.states)-1)
            d=self.doc.d;s=d['style']
            for key,w in self.controls.items():
                val=s[key]
                if isinstance(w,QComboBox):w.setCurrentText(str(val))
                elif isinstance(w,QCheckBox):w.setChecked(val)
                elif isinstance(w,QDoubleSpinBox):w.setValue(val)
                elif isinstance(w,QLineEdit):w.setText(str(val))
                else:w.setText(val);w.setStyleSheet(f'background:{val};color:{"#ffffff" if QColor(val).lightness()<120 else "#222222"}')
            self.setcombo.clear();self.setcombo.addItems(['Классический','Геометрический']+list(d['sets']));self.setcombo.setCurrentText(s['piece_set'])
            self.intentcombo.setCurrentIndex(s['intent']);self.icclabel.setText('ICC: '+self.doc.data['resources'].get(s['icc'],'не выбран'))
            self.diagrams.clear();self.diagrams.addItems([x['name'] for x in self.doc.data['diagrams']]);self.diagrams.setCurrentRow(self.doc.data['active'])
            self.history.clear();self.history.addItems(self.doc.labels);self.history.setCurrentRow(self.doc.cursor)
            selected_layer=self.layers.currentRow();self.layers.clear()
            for layer in d['layers']:
                i=QListWidgetItem(('🔒 ' if layer['locked'] else '')+layer['name']);i.setFlags(i.flags()|Qt.ItemIsUserCheckable);i.setCheckState(Qt.Checked if layer['visible'] else Qt.Unchecked);self.layers.addItem(i)
            self.layers.setCurrentRow(selected_layer)
            self.setWindowTitle(('* ' if self.doc.dirty else '')+d['name']+' — '+APP)
            self.infolabel.setText(f"Доска {s['board_mm']:g} × {s['board_mm']:g} мм  ·  {len(self.doc.data['diagrams'])} диаграмм  ·  {'Легальные ходы' if d['legal'] else 'Свободная расстановка'}")
            self.canvas.refresh();self.show_selected()
        finally:self.busy=False
    def undo(self,delta):self.doc.restore(self.doc.cursor+delta);self.canvas.selected=None;self.refresh()
    def history_jump(self,row):
        if not self.busy:self.doc.restore(row);self.canvas.selected=None;self.refresh()
    def position(self,fen):self.doc.set_fen(fen);self.canvas.selected=None;self.commit('Изменить позицию')
    def import_fen(self):
        text,ok=QInputDialog.getMultiLineText(self,'Импорт FEN','FEN:',self.doc.d['fen'])
        if ok:self.position(text)
    def import_fen_list(self):
        path,_=QFileDialog.getOpenFileName(self,'Список FEN','','Текст (*.txt *.fen)')
        if not path:return
        lines=[x.strip() for x in Path(path).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
        boards=[chess.Board(line) for line in lines]
        for b in boards:
            d=diagram('Задача № '+str(len(self.doc.data['diagrams'])+1));d['fen']=b.fen();d['style']=copy.deepcopy(self.doc.d['style']);self.doc.data['diagrams'].append(d)
        self.commit('Импорт списка FEN')
    def import_pgn(self):
        path,_=QFileDialog.getOpenFileName(self,'Импорт PGN','','PGN (*.pgn)')
        if not path:return
        text=Path(path).read_text(encoding='utf-8-sig')
        mode,ok=QInputDialog.getItem(self,'Импорт PGN','Режим',['Все партии — отдельными диаграммами','Первую партию в текущую диаграмму'],0,False)
        if not ok:return
        if mode.startswith('Все'):self.doc.import_games(text)
        else:self.doc.import_pgn(text)
        self.canvas.selected=None;self.commit('Импорт PGN')
    def export_pgn(self):
        if not self.doc.d['pgn']:raise ValueError('Нет импортированной партии. Произвольная расстановка сохраняется как FEN.')
        path,_=QFileDialog.getSaveFileName(self,'Экспорт PGN','','PGN (*.pgn)')
        if path:Path(path).write_text(self.doc.d['pgn'],encoding='utf-8')
    def export_fen(self):
        path,_=QFileDialog.getSaveFileName(self,'Экспорт FEN','','FEN (*.fen)')
        if path:Path(path).write_text(self.doc.d['fen'],encoding='utf-8')
    def goto_ply(self,delta):self.doc.goto_ply(self.doc.d['ply']+delta);self.commit('Просмотр партии')
    def show_pgn(self):QMessageBox.information(self,'Партия PGN',self.doc.d['pgn'] or 'Партия не загружена')
    def choose_turn(self):
        board=chess.Board(self.doc.d['fen']);name,ok=QInputDialog.getItem(self,'Сторона хода','Кто ходит?',['Белые','Чёрные'],0 if board.turn else 1,False)
        if ok:board.turn=name=='Белые';self.position(board.fen(en_passant='fen'))
    def validate_position(self):
        b=chess.Board(self.doc.d['fen']);QMessageBox.information(self,'Проверка позиции','Позиция допустима.' if b.is_valid() else f'Позиция не соответствует правилам обычной партии (код {int(b.status())}).\nДля учебных диаграмм это разрешено.')
    def toggle_legal(self):self.doc.d['legal']=not self.doc.d['legal'];self.commit('Режим проверки ходов')
    def switch_diagram(self,row):
        if not self.busy and row>=0:self.doc.data['active']=row;self.canvas.selected=None;self.commit('Выбрать диаграмму')
    def new_diagram(self):
        self.doc.data['diagrams'].append(diagram('Диаграмма '+str(len(self.doc.data['diagrams'])+1)));self.doc.data['active']=len(self.doc.data['diagrams'])-1;self.canvas.selected=None;self.commit('Новая диаграмма')
    def duplicate_diagram(self):
        d=copy.deepcopy(self.doc.d);d['name']+=' — копия';self.doc.data['diagrams'].append(d);self.doc.data['active']=len(self.doc.data['diagrams'])-1;self.canvas.selected=None;self.commit('Дублировать диаграмму')
    def rename_diagram(self):
        name,ok=QInputDialog.getText(self,'Название диаграммы','Название:',text=self.doc.d['name'])
        if ok and name:self.doc.d['name']=name;self.commit('Переименовать диаграмму')
    def move_diagram(self,delta):
        i=self.doc.data['active'];j=i+delta;ds=self.doc.data['diagrams']
        if 0<=j<len(ds):ds[i],ds[j]=ds[j],ds[i];self.doc.data['active']=j;self.commit('Порядок диаграмм')
    def delete_diagram(self):
        if len(self.doc.data['diagrams'])<=1:raise ValueError('В проекте должна оставаться хотя бы одна диаграмма')
        if QMessageBox.question(self,'Удаление','Удалить текущую диаграмму?')==QMessageBox.Yes:
            self.doc.data['diagrams'].pop(self.doc.data['active']);self.doc.data['active']=0;self.canvas.selected=None;self.commit('Удалить диаграмму')
    def layer_changed(self,item):
        if not self.busy:self.doc.d['layers'][self.layers.row(item)]['visible']=item.checkState()==Qt.Checked;self.commit('Видимость слоя')
    def lock_layer(self):
        i=self.layers.currentRow()
        if i>=0:self.doc.d['layers'][i]['locked']=not self.doc.d['layers'][i]['locked'];self.commit('Блокировка слоя')
    def move_layer(self,delta):
        i=self.layers.currentRow();j=i+delta;ls=self.doc.d['layers']
        if 0<=i<len(ls) and 0<=j<len(ls):ls[i],ls[j]=ls[j],ls[i];self.commit('Порядок слоёв');self.layers.setCurrentRow(j)
    def selected(self):
        sel=self.canvas.selected
        if not sel:return None
        typ,i=sel
        if typ=='object':return self.doc.d['objects'][i] if i<len(self.doc.d['objects']) else None
        return self.doc.d['piece_overrides'].get(str(i),{})
    def show_selected(self):
        s=self.canvas.selected;self.selectedlabel.setText('Выберите фигуру или обозначение' if not s else ('Фигура '+chess.square_name(s[1]) if s[0]=='piece' else 'Графический объект № '+str(s[1]+1)))
    def delete_selected(self):
        sel=self.canvas.selected
        if not sel:return
        typ,i=sel
        if typ=='piece':
            if self.canvas.locked('Фигуры'):return
            self.doc.place(i,None)
        elif i<len(self.doc.d['objects']):
            if self.canvas.locked(self.doc.d['objects'][i]['layer']):return
            self.doc.d['objects'].pop(i)
        self.canvas.selected=None;self.commit('Удалить выбранное')
    def duplicate_selected(self):
        sel=self.canvas.selected
        if sel and sel[0]=='object':
            o=copy.deepcopy(self.selected())
            if self.canvas.locked(o['layer']):return
            o['points']=[[x+15,y+15] for x,y in o['points']];self.doc.d['objects'].append(o);self.canvas.selected=('object',len(self.doc.d['objects'])-1);self.commit('Дублировать объект')
    def order_object(self,front):
        sel=self.canvas.selected
        if sel and sel[0]=='object':
            os_=self.doc.d['objects'];o=os_[sel[1]]
            if self.canvas.locked(o['layer']):return
            os_.pop(sel[1]);os_.append(o) if front else os_.insert(0,o);self.canvas.selected=('object',len(os_)-1 if front else 0);self.commit('Порядок объекта')
    def edit_selected(self):
        sel=self.canvas.selected
        if not sel:return
        if sel[0]=='piece':
            if self.canvas.locked('Фигуры'):return
            s=self.doc.d['style'];values=dict(scale=s['piece_scale'],dx=s['piece_dx'],dy=s['piece_dy'],opacity=s['piece_opacity']);values.update(self.selected())
        else:
            values=copy.deepcopy(self.selected())
            if not values or self.canvas.locked(values['layer']):return
        dlg=QDialog(self);dlg.setWindowTitle('Свойства выбранного объекта');v=QVBoxLayout(dlg);f=QFormLayout();v.addLayout(f);widgets={}
        labels={'scale':'Масштаб','dx':'Смещение X','dy':'Смещение Y','opacity':'Непрозрачность','color':'Цвет HEX','width':'Толщина','head_size':'Наконечник','text':'Текст','font_size':'Размер текста','font':'Шрифт','double':'Два наконечника','outline':'Двойной контур','dash':'Линия','head':'Наконечник','points':'Координаты точек (JSON)'}
        for key,val in values.items():
            if key not in labels:continue
            if isinstance(val,bool):w=QCheckBox();w.setChecked(val)
            elif isinstance(val,(int,float)):
                w=QDoubleSpinBox();w.setRange(-5000,5000);w.setValue(val);w.setDecimals(3)
                if key=='opacity':w.setRange(0,1)
                if key=='scale':w.setRange(.4,1.2)
                if key in ('width','head_size','font_size'):w.setRange(.1,200)
            else:w=QLineEdit(json.dumps(val) if key=='points' else str(val))
            widgets[key]=w;f.addRow(labels[key],w)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);v.addWidget(buttons)
        if dlg.exec()!=QDialog.Accepted:return
        for key,w in widgets.items():
            val=w.isChecked() if isinstance(w,QCheckBox) else w.value() if isinstance(w,QDoubleSpinBox) else w.text()
            if key=='points':
                val=json.loads(val)
                if not 2<=len(val)<=1000 or any(len(p)!=2 or any(not isinstance(n,(float,int)) for n in p) for p in val):raise ValueError('Нужен список точек [[x,y],[x,y],…]')
            if key=='color' and not QColor(val).isValid():raise ValueError('Некорректный цвет')
            values[key]=val
        if sel[0]=='piece':self.doc.d['piece_overrides'][str(sel[1])]=values
        else:self.doc.d['objects'][sel[1]]=values
        self.commit('Свойства объекта')
    def clear_annotations(self):self.doc.d['objects']=[o for o in self.doc.d['objects'] if self.canvas.locked(o['layer'])];self.canvas.selected=None;self.commit('Очистить обозначения')
    def highlight_center(self):
        if self.canvas.locked('Подсветка'):return
        self.doc.d['objects'].append(dict(kind='highlight',layer='Подсветка',points=[[240,240],[400,400]],color='#ffcb47',opacity=.4,width=2));self.commit('Выделить центр')
    def import_style_resource(self,key):
        path,_=QFileDialog.getOpenFileName(self,'Загрузить ресурс','','ICC (*.icc *.icm)' if key=='icc' else 'Изображения (*.svg *.png *.jpg *.jpeg *.bmp *.tif *.tiff)')
        if not path:return
        if key=='icc':
            from PIL import ImageCms
            pr=ImageCms.getOpenProfile(path)
            if pr.profile.xcolor_space.strip()!='CMYK':raise ValueError('Нужен CMYK-профиль')
        else:self.check_image(path)
        self.doc.d['style'][key]=self.doc.add_resource(path);self.commit('Импорт ресурса')
    def check_image(self,path):
        b=Path(path).read_bytes()
        if str(path).lower().endswith('.svg'):
            from PySide6.QtSvg import QSvgRenderer
            if not QSvgRenderer(QByteArray(b)).isValid():raise ValueError('Повреждённый SVG')
        elif QImage.fromData(b).isNull():raise ValueError('Не удалось прочитать изображение')
    def import_font(self):
        path,_=QFileDialog.getOpenFileName(self,'Загрузить шрифт','','Шрифты (*.ttf *.otf)')
        if path:
            idx=QFontDatabase.addApplicationFont(path)
            if idx<0:raise ValueError('Не удалось загрузить шрифт')
            key=self.doc.add_resource(path);self.doc.data['fonts'].append(key);self.doc.d['style']['font']=QFontDatabase.applicationFontFamilies(idx)[0];self.commit('Добавить шрифт')
    def import_set(self):
        folder=QFileDialog.getExistingDirectory(self,'Папка набора: wK.svg, wQ.svg, …, bP.svg (или PNG)')
        if not folder:return
        selected={}
        for symbol in 'KQRBNPkqrbnp':
            stem=('w' if symbol.isupper() else 'b')+symbol.upper()
            matches=[x for x in Path(folder).iterdir() if x.stem==stem and x.suffix.lower() in ('.svg','.png','.jpg','.jpeg','.bmp')]
            if not matches:raise ValueError('Не найдено изображение '+stem)
            self.check_image(matches[0]);selected[symbol]=matches[0]
        name,ok=QInputDialog.getText(self,'Набор фигур','Название:',text=Path(folder).name)
        if not ok or not name:return
        if name in ('Классический','Геометрический'):raise ValueError('Выберите другое название')
        if name in self.doc.d['sets'] and QMessageBox.question(self,'Замена','Заменить набор?')!=QMessageBox.Yes:return
        self.doc.d['sets'][name]={s:self.doc.add_resource(p) for s,p in selected.items()};self.doc.d['style']['piece_set']=name;self.commit('Импорт набора фигур')
    def import_piece(self):
        symbol,ok=QInputDialog.getItem(self,'Импорт фигуры','K Q R B N P — белые; k q r b n p — чёрные',list('KQRBNPkqrbnp'),0,False)
        if not ok:return
        path,_=QFileDialog.getOpenFileName(self,'Изображение фигуры','','Изображения (*.svg *.png *.jpg *.jpeg *.bmp)')
        if path:
            self.check_image(path);name='Пользовательский';self.doc.d['sets'].setdefault(name,{})[symbol]=self.doc.add_resource(path);self.doc.d['style']['piece_set']=name;self.commit('Импорт фигуры')
    def export_set(self):
        folder=QFileDialog.getExistingDirectory(self,'Экспорт набора фигур')
        if not folder:return
        name=self.doc.d['style']['piece_set'];mapping=self.doc.d['sets'].get(name,{})
        files=[]
        for symbol in 'KQRBNPkqrbnp':
            key=mapping.get(symbol);ext=Path(key).suffix if key else '.svg';p=Path(folder)/(('w' if symbol.isupper() else 'b')+symbol.upper()+ext)
            files.append((p,self.doc.resources[key] if key else builtin_svg(symbol,name)))
        if any(p.exists() for p,b in files) and QMessageBox.question(self,'Перезапись','Заменить существующие файлы набора?')!=QMessageBox.Yes:return
        for p,b in files:p.write_bytes(b)
    def confirm_save(self):
        if not self.doc.dirty:return True
        answer=QMessageBox.question(self,'Несохранённые изменения','Сохранить изменения?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        if answer==QMessageBox.Cancel:return False
        if answer==QMessageBox.Save:return self.save()
        return True
    def new_project(self):
        if not self.confirm_save():return
        self.doc=Document();self.renderer=Renderer(self.doc);self.canvas.selected=None
        default=self.store/'default.chessdiagram'
        if default.exists():self.apply_template_file(default)
        self.doc.path=None;self.refresh();self.canvas.fit()
    def open_project(self,path=None):
        if not self.confirm_save():return
        if not path:path,_=QFileDialog.getOpenFileName(self,'Открыть проект','','Проекты (*.chessdiagram)')
        if not path:return
        new=Document();new.load(path);self.doc=new;self.renderer=Renderer(self.doc);self.load_fonts();self.canvas.selected=None;self.remember(path);self.refresh();self.canvas.fit()
    def load_fonts(self):
        for key in self.doc.data['fonts']:
            if key in self.doc.resources:QFontDatabase.addApplicationFontFromData(QByteArray(self.doc.resources[key]))
    def save(self,as_new=False):
        path=self.doc.path
        if not path or as_new:path,_=QFileDialog.getSaveFileName(self,'Сохранить проект',path or 'Диаграммы.chessdiagram','Проект (*.chessdiagram)')
        if not path:return False
        if not path.lower().endswith('.chessdiagram'):path+='.chessdiagram'
        self.doc.save(path);self.remember(path);self.refresh()
        if self.recovery.exists():self.recovery.unlink()
        return True
    def remember(self,path):
        rec=self.settings.value('recent',[]) or []
        if isinstance(rec,str):rec=[rec]
        self.settings.setValue('recent',[str(path)]+[x for x in rec if x!=str(path)][:9])
    def open_recent(self):
        items=self.settings.value('recent',[]) or []
        if not items:return
        path,ok=QInputDialog.getItem(self,'Последние проекты','Проект:',items,0,False)
        if ok:self.open_project(path)
    def autosave(self):
        if not self.doc.dirty:return
        try:self.doc.save(self.recovery,autosave=True);self.statusBar().showMessage('Резервная копия сохранена',3000)
        except Exception as e:self.statusBar().showMessage('Не удалось сохранить резервную копию: '+str(e),10000)
    def closeEvent(self,e):
        if self.export_job is not None:
            self.statusBar().showMessage('Дождитесь завершения экспорта или отмените его.',6000);e.ignore();return
        try:
            if not self.confirm_save():e.ignore();return
            self.settings.setValue('layout',self.saveState());self.timer.stop()
            if hasattr(self,'session_lock'):self.session_lock.unlock()
            if self.recovery.exists():self.recovery.unlink()
            e.accept()
        except Exception as exc:self.error(exc);e.ignore()
    def save_template(self,path=None):
        if path is None:path,_=QFileDialog.getSaveFileName(self,'Сохранить оформление','','Шаблон (*.chesstemplate)')
        if not path:return
        t=Document();d=copy.deepcopy(self.doc.d);d['fen']=chess.Board(None).fen();d['objects']=[];d['piece_overrides']={};d['pgn']='';d['ply']=0
        t.data['diagrams']=[d];t.resources=copy.deepcopy(self.doc.resources);t.data['resources']=copy.deepcopy(self.doc.data['resources']);t.data['fonts']=copy.deepcopy(self.doc.data['fonts']);t.save(path)
    def load_template(self):
        path,_=QFileDialog.getOpenFileName(self,'Применить оформление','','Шаблон (*.chesstemplate *.chessdiagram)')
        if path:self.apply_template_file(path);self.commit('Применить шаблон')
    def apply_template_file(self,path):
        t=Document();t.load(path)
        for key in ['style','sets','layers']:self.doc.d[key]=copy.deepcopy(t.d[key])
        self.doc.resources.update(t.resources);self.doc.data['resources'].update(t.data['resources']);self.doc.data['fonts']=list(set(self.doc.data['fonts']+t.data['fonts']));self.load_fonts()
    def apply_all(self):
        d=self.doc.d
        for target in self.doc.data['diagrams']:
            if target is d:continue
            for key in ['style','sets','layers']:target[key]=copy.deepcopy(d[key])
        self.commit('Общее оформление')
    def set_default_template(self):self.save_template(self.store/'default.chessdiagram');self.statusBar().showMessage('Оформление сохранено по умолчанию',4000)
    def preset(self,name):
        s=self.doc.d['style'];s.update(light='#ffffff',dark='#bbbbbb',frame_color='#222222',coord_color='#222222',coords='Снаружи',piece_scale=.85,gradient=False,board_image='',light_texture='',dark_texture='')
        if name=='Детская тетрадь':s.update(light='#fff3ce',dark='#8cbfb4',font_size=24,piece_scale=.95)
        elif name=='Цветная':s.update(light='#f1eedf',dark='#608275')
        elif name=='Без координат':s.update(coords='Нет')
        elif name=='Крупные фигуры':s.update(piece_scale=1.1)
        elif name=='Минималистичная':s.update(frame=False,dark='#e0e3e2',piece_set='Геометрический')
        elif name=='Чёрно-белая':s.update(light='#ffffff',dark='#999999',background='#ffffff')
        self.commit('Шаблон: '+name)
    def export_dialog(self,cmyk=False):
        from .studio import ExportStudio
        ExportStudio(self,cmyk=cmyk).exec()
    def repeat_export(self):
        if not hasattr(self,'last_export'):return self.export_dialog(False)
        path,cmyk=self.last_export
        if Path(path).exists() and QMessageBox.question(self,'Перезапись','Перезаписать '+Path(path).name+'?')!=QMessageBox.Yes:return
        self.start_export({'kind':'diagrams','outputs':[dict(path=path,cmyk=cmyk,index=self.doc.data['active'])]})
    def batch_export(self):
        folder=QFileDialog.getExistingDirectory(self,'Папка пакетного экспорта')
        if not folder:return
        fmt,ok=QInputDialog.getItem(self,'Пакетный экспорт','Формат',['PNG','SVG','PDF','TIFF','CMYK TIFF','CMYK PDF'],0,False)
        if not ok:return
        pattern,ok=QInputDialog.getText(self,'Имена файлов','Поля: {n}, {name}',text='{n:03d}_{name}')
        if not ok:return
        ext='.'+fmt.split()[-1].lower();paths=[]
        for i,d in enumerate(self.doc.data['diagrams'],1):
            name=pattern.format(n=i,name=d['name']);name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .')
            if not name:raise ValueError('Пустое имя файла')
            paths.append(Path(folder)/(name+ext))
        if len({str(p).casefold() for p in paths})!=len(paths):raise ValueError('Шаблон создаёт одинаковые имена. Добавьте {n}.')
        if any(p.exists() for p in paths) and QMessageBox.question(self,'Перезапись','Заменить совпадающие файлы?')!=QMessageBox.Yes:return
        self.start_export({'kind':'diagrams','outputs':[dict(path=str(path),index=i,cmyk=fmt.startswith('CMYK')) for i,path in enumerate(paths)]})
    def export_pages(self):
        from .studio import ExportStudio
        ExportStudio(self,pages=True).exec()
    def proof(self):
        profile=profile_bytes(self.doc,self.doc.d);im=softproof(raster(self.renderer,self.doc.d,120),profile,self.doc.d['style']['intent'])
        b=io.BytesIO();im.save(b,format='PNG');label=QLabel();label.setPixmap(QPixmap.fromImage(QImage.fromData(b.getvalue())))
        dlg=QDialog(self);dlg.setWindowTitle('ICC-цветопроба • монитор предполагается sRGB');v=QVBoxLayout(dlg);sc=QScrollArea();sc.setWidget(label);v.addWidget(sc);dlg.resize(800,800);dlg.exec()
    def copy_image(self):
        im=raster(self.renderer,self.doc.d,self.doc.d['style']['dpi']);b=io.BytesIO();im.save(b,format='PNG');QApplication.clipboard().setImage(QImage.fromData(b.getvalue()))
    def paste_image(self):
        im=QApplication.clipboard().image()
        if im.isNull():raise ValueError('В буфере обмена нет изображения')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'clipboard.png';im.save(str(path));key=self.doc.add_resource(path)
        self.doc.d['objects'].append(dict(kind='image',layer='Графика',points=[[160,160],[480,480]],resource=key,opacity=1));self.commit('Вставить изображение')
    def theme(self,name):
        self.settings.setValue('theme',name)
        if name=='Тёмная':colors=(' #242d32','#e5ebe8','#323e43','#50685d')
        else:colors=('#f5f7f6','#213a30','#ffffff','#d8e6df')
        bg,fg,field,hover=colors
        self.setStyleSheet(f'QWidget {{background:{bg};color:{fg};font-size:12px;}} QLineEdit,QComboBox,QAbstractSpinBox,QListWidget,QTextBrowser {{background:{field};border:1px solid #87998f;border-radius:4px;padding:4px;}} QPushButton,QToolButton {{background:{field};border:1px solid #a1b2a7;border-radius:5px;padding:6px;}} QPushButton:hover,QToolButton:hover {{background:{hover};}} QDockWidget::title {{padding:7px;font-weight:bold;}} QTabBar::tab {{padding:8px;}} QMenu::item:selected {{background:{hover};}}')
    def command_palette(self):
        dlg=QDialog(self);dlg.setWindowTitle('Поиск команды');v=QVBoxLayout(dlg);search=QLineEdit();search.setPlaceholderText('Название команды, например: экспорт, фигуры, шаблон…');v.addWidget(search);items=QListWidget();v.addWidget(items)
        def update(text=''):
            items.clear()
            for name,action in self.actions.items():
                if action.isEnabled() and all(word in name.casefold() for word in text.casefold().split()):
                    item=QListWidgetItem(name+('    '+action.shortcut().toString() if not action.shortcut().isEmpty() else ''));item.setData(Qt.UserRole,name);items.addItem(item)
            if items.count():items.setCurrentRow(0)
        def choose(*args):
            item=items.currentItem()
            if item:dlg.accept();self.actions[item.data(Qt.UserRole)].trigger()
        search.textChanged.connect(update);search.returnPressed.connect(choose);items.itemActivated.connect(choose);update();dlg.resize(620,480);search.setFocus();dlg.exec()
    def edit_shortcuts(self):
        names=list(self.actions);name,ok=QInputDialog.getItem(self,'Горячие клавиши','Команда:',names,0,False)
        if not ok:return
        value,ok=QInputDialog.getText(self,'Горячая клавиша','Например Ctrl+Alt+E; пусто — отключить:',text=self.actions[name].shortcut().toString())
        if ok:
            sequence=QKeySequence(value)
            if value and sequence.isEmpty():raise ValueError('Не удалось разобрать сочетание')
            for other,a in self.actions.items():
                if other!=name and value and sequence in a.shortcuts():raise ValueError('Сочетание уже используется: '+other)
            self.actions[name].setShortcut(sequence);self.settings.setValue('shortcut/'+name,value)
    def help(self):
        dlg=QDialog(self);dlg.setWindowTitle('Руководство');v=QVBoxLayout(dlg);text=QTextBrowser()
        path=ROOT/'РУКОВОДСТВО.md';text.setMarkdown(path.read_text(encoding='utf-8') if path.exists() else 'Выберите фигуру и нажмите клетку. Стрелка — правой кнопкой. Ctrl+S — сохранить.')
        v.addWidget(text);dlg.resize(800,700);dlg.exec()

    def rotate_selected(self):
        sel=self.canvas.selected
        if not sel or sel[0]!='object':return
        o=self.selected()
        if self.canvas.locked(o['layer']):return
        angle,ok=QInputDialog.getDouble(self,'Поворот','Угол, градусов:',90,-360,360,1)
        if not ok:return
        import math
        points=o['points'];cx=sum(x for x,y in points)/len(points);cy=sum(y for x,y in points)/len(points);a=math.radians(angle)
        o['points']=[[cx+(x-cx)*math.cos(a)-(y-cy)*math.sin(a),cy+(x-cx)*math.sin(a)+(y-cy)*math.cos(a)] for x,y in points]
        self.commit('Повернуть точки объекта')
    def favorite_save(self):
        name,ok=QInputDialog.getText(self,'Избранное','Название:',text=self.doc.d['name'])
        if not ok or not name:return
        path=self.store/'favorites.json';data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if name in data and QMessageBox.question(self,'Замена','Заменить позицию?')!=QMessageBox.Yes:return
        data[name]=self.doc.d['fen'];path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    def favorite_open(self):
        path=self.store/'favorites.json';data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not data:QMessageBox.information(self,'Избранное','Сохранённых позиций нет.');return
        name,ok=QInputDialog.getItem(self,'Избранное','Позиция:',list(data),0,False)
        if ok:self.position(data[name])
    def template_library(self):
        folder=self.store/'templates';folder.mkdir(exist_ok=True)
        dlg=QDialog(self);dlg.setWindowTitle('Библиотека шаблонов');v=QVBoxLayout(dlg);items=QListWidget();v.addWidget(items)
        def reload():
            items.clear();items.addItems([p.stem for p in sorted(folder.glob('*.chesstemplate'))])
        def current():
            return folder/(items.currentItem().text()+'.chesstemplate') if items.currentItem() else None
        def name_input(default):
            name,ok=QInputDialog.getText(dlg,'Название','Название шаблона:',text=default)
            if not ok or not name:return None
            if re.search(r'[<>:"/\\|?*]',name) or name in ('.','..'):raise ValueError('Недопустимое имя')
            target=folder/(name+'.chesstemplate')
            if target.exists():raise ValueError('Шаблон с таким названием уже существует')
            return target
        def create():
            p=name_input('Мой шаблон')
            if p:self.save_template(p);reload()
        def duplicate():
            p=current()
            if p:
                target=name_input(p.stem+' — копия')
                if target:target.write_bytes(p.read_bytes());reload()
        def rename():
            p=current()
            if p:
                target=name_input(p.stem)
                if target:p.rename(target);reload()
        def delete():
            p=current()
            if p and QMessageBox.question(dlg,'Удаление','Удалить шаблон '+p.stem+'?')==QMessageBox.Yes:p.unlink();reload()
        def apply():
            p=current()
            if p:self.apply_template_file(p);self.commit('Применить шаблон');dlg.accept()
        def import_file():
            p,_=QFileDialog.getOpenFileName(dlg,'Импорт шаблона','','Шаблон (*.chesstemplate)')
            if p:
                check=Document();check.load(p);target=name_input(Path(p).stem)
                if target:target.write_bytes(Path(p).read_bytes());reload()
        def export_template():
            p=current()
            if p:
                target,_=QFileDialog.getSaveFileName(dlg,'Экспорт шаблона',p.name,'Шаблон (*.chesstemplate)')
                if target:Path(target).write_bytes(p.read_bytes())
        for title,fn in [('Создать из текущего оформления',create),('Применить',apply),('Дублировать',duplicate),('Переименовать',rename),('Удалить',delete),('Импорт',import_file),('Экспорт',export_template)]:self.button(v,title,fn)
        reload();dlg.resize(450,500);dlg.exec()

def main():
    app=QApplication(sys.argv);QFontDatabase.addApplicationFont(str(ROOT/'assets'/'DejaVuSans.ttf'));app.setApplicationName(APP);app.setOrganizationName('ChessDiagram');app.setStyle('Fusion')
    if '--export-job' in sys.argv:
        from .jobs import execute_job
        return execute_job(sys.argv[sys.argv.index('--export-job')+1])
    w=Window(recover='--smoke-test' not in sys.argv);w.show()
    if len(sys.argv)>1 and not sys.argv[1].startswith('--'):
        QTimer.singleShot(0,w.guarded(lambda:w.open_project(sys.argv[1])))
    if '--smoke-test' in sys.argv:QTimer.singleShot(500,app.quit)
    return app.exec()
