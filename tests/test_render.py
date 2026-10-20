import io,os,copy
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest,chess
from PIL import Image,ImageCms
from PySide6.QtWidgets import QApplication
from chessdiagram.model import Document
from chessdiagram.render import Renderer
from chessdiagram.export import export_file,raster,convert_cmyk,softproof,contact_sheet,ghostscript
from pypdf import PdfReader

@pytest.fixture(scope='session')
def app():return QApplication.instance() or QApplication([])

@pytest.fixture
def doc(app):return Document()

@pytest.mark.parametrize('ext',['png','jpg','bmp','tiff','svg','pdf'])
def test_export_formats(doc,tmp_path,ext):
    p=tmp_path/('Экспорт.'+ext);export_file(doc,doc.d,p);assert p.stat().st_size>100
    s=doc.d['style'];mm=s['board_mm']*(640+s['margin']*2)/640
    if ext in ('png','jpg','bmp','tiff'):
        im=Image.open(p);assert im.width==round(mm/25.4*s['dpi']);assert im.height==im.width
    if ext=='svg':
        text=p.read_text();assert f'width="{mm:.6f}mm"' in text;assert '<path' in text
    if ext=='pdf':
        page=PdfReader(p).pages[0];assert abs(float(page.mediabox.width)-mm/25.4*72)<.1
        assert b' m' in page.get_contents().get_data() # vector path operators

@pytest.mark.parametrize('flip',[False,True])
def test_pixel_board_colors(doc,flip):
    doc.set_fen(chess.Board(None).fen());s=doc.d['style'];s.update(margin=0,frame=False,coords='Нет',light='#ffffff',dark='#000000',flipped=flip,board_mm=25.4,dpi=640)
    im=raster(Renderer(doc),doc.d,640);assert im.size==(640,640)
    assert im.getpixel((40,600))[:3]==(0,0,0);assert im.getpixel((120,600))[:3]==(255,255,255)

def test_transparent(doc,tmp_path):
    doc.d['style']['transparent']=True;p=tmp_path/'x.png';export_file(doc,doc.d,p);im=Image.open(p);assert im.getpixel((0,0))[3]==0

def profile_path():
    candidates=[os.environ.get('TEST_CMYK_ICC',''),'/usr/share/color/icc/ghostscript/default_cmyk.icc']
    return next((Path(x) for x in candidates if x and Path(x).is_file()),None)

def test_cmyk_requires_profile(doc,tmp_path):
    with pytest.raises(ValueError,match='ICC'):export_file(doc,doc.d,tmp_path/'x.tiff',True)
    with pytest.raises(ValueError,match='TIFF'):export_file(doc,doc.d,tmp_path/'x.png',True)

def test_cmyk_tiff(doc,tmp_path):
    profile=profile_path()
    if profile is None:pytest.skip('CMYK profile unavailable')
    doc.d['style']['icc']=doc.add_resource(profile);p=tmp_path/'cmyk.tiff';export_file(doc,doc.d,p,True);im=Image.open(p)
    assert im.mode=='CMYK';assert im.info['icc_profile']==profile.read_bytes();assert im.info['dpi']==(300,300)
    rgb=Image.new('RGB',(1,1),'red');expected=ImageCms.profileToProfile(rgb,ImageCms.createProfile('sRGB'),ImageCms.getOpenProfile(str(profile)),outputMode='CMYK')
    assert convert_cmyk(rgb,profile.read_bytes()).getpixel((0,0))==expected.getpixel((0,0))
    assert softproof(rgb,profile.read_bytes()).mode=='RGB'

def test_cmyk_pdf(doc,tmp_path):
    profile=profile_path()
    if profile is None or not ghostscript():pytest.skip('Ghostscript / ICC unavailable')
    doc.d['style']['icc']=doc.add_resource(profile);p=tmp_path/'cmyk.pdf';export_file(doc,doc.d,p,True);pdf=PdfReader(p)
    intent=pdf.trailer['/Root']['/OutputIntents'][0].get_object();icc=intent['/DestOutputProfile'].get_object()
    assert icc['/N']==4;assert icc.get_data()==profile.read_bytes()
    assert b' k' in pdf.pages[0].get_contents().get_data() # CMYK vector fills

def test_contact_sheet(doc,tmp_path):
    doc.data['diagrams']=[copy.deepcopy(doc.d) for _ in range(7)]
    p=tmp_path/'pages.pdf';contact_sheet(doc,p,'A4',2,3,8);pdf=PdfReader(p);assert len(pdf.pages)==2
    assert abs(float(pdf.pages[0].mediabox.width)-210/25.4*72)<.1

def test_all_annotations(doc,tmp_path):
    for i,kind in enumerate(['arrow','curve','arc','knight','poly','line','rect','highlight','outline','ellipse','cross','check','text']):
        doc.d['objects'].append(dict(kind=kind,layer='Стрелки' if i<6 else 'Графика',points=[[40+i*10,100],[300+i*10,480]],color='#ff0000',width=4,opacity=.6,head='Треугольник',double=True,outline=True,text='Қазақша !?',font_size=24))
    export_file(doc,doc.d,tmp_path/'annotations.svg');assert (tmp_path/'annotations.svg').stat().st_size>10000

def test_gui_smoke(app,tmp_path):
    from chessdiagram.app import Window
    w=Window(recover=False);w.show();app.processEvents();w.canvas.fit();app.processEvents()
    w.doc.d['style']['dark']='#ff0000';w.commit('color');w.undo(-1);assert w.doc.d['style']['dark']!='#ff0000';w.undo(1);assert w.doc.d['style']['dark']=='#ff0000'
    w.duplicate_diagram();assert len(w.doc.data['diagrams'])==2
    w.doc.dirty=False;w.grab().save(str(tmp_path/'ui.png'));w.close()

def test_mouse_place_move_arrow_undo(app):
    from chessdiagram.app import Window
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt,QPointF
    w=Window(recover=False);w.show();app.processEvents();w.canvas.fit();app.processEvents()
    def at(sq):
        from chessdiagram.model import square_xy
        x,y=square_xy(sq,w.doc.d['style']['flipped']);return w.canvas.mapFromScene(QPointF(x+40,y+40))
    w.choose_piece('Q');QTest.mouseClick(w.canvas.viewport(),Qt.LeftButton,pos=at(chess.D4));assert chess.Board(w.doc.d['fen']).piece_at(chess.D4).symbol()=='Q'
    w.choose_tool('select');QTest.mousePress(w.canvas.viewport(),Qt.LeftButton,pos=at(chess.D4));QTest.mouseMove(w.canvas.viewport(),at(chess.E5));QTest.mouseRelease(w.canvas.viewport(),Qt.LeftButton,pos=at(chess.E5));assert chess.Board(w.doc.d['fen']).piece_at(chess.E5).symbol()=='Q'
    QTest.mousePress(w.canvas.viewport(),Qt.RightButton,pos=at(chess.E5));QTest.mouseMove(w.canvas.viewport(),at(chess.F7));QTest.mouseRelease(w.canvas.viewport(),Qt.RightButton,pos=at(chess.F7));assert len(w.doc.d['objects'])==1
    w.undo(-1);assert not w.doc.d['objects'];w.undo(1);assert len(w.doc.d['objects'])==1
    w.doc.dirty=False;w.close()

def test_locked_pieces(app):
    from chessdiagram.app import Window
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt,QPointF
    w=Window(recover=False);w.show();app.processEvents();w.canvas.fit()
    for layer in w.doc.d['layers']:
        if layer['name']=='Фигуры':layer['locked']=True
    before=w.doc.d['fen'];w.choose_piece('Q');QTest.mouseClick(w.canvas.viewport(),Qt.LeftButton,pos=w.canvas.mapFromScene(QPointF(280,360)))
    assert w.doc.d['fen']==before;w.doc.dirty=False;w.close()

def test_template_preserves_position(app,tmp_path):
    from chessdiagram.app import Window
    w=Window(recover=False);w.doc.d['style']['dark']='#123456';p=tmp_path/'template.chesstemplate';w.save_template(p)
    w.doc.place(chess.D4,'N');fen=w.doc.d['fen'];w.doc.d['style']['dark']='#ffffff';w.apply_template_file(p)
    assert w.doc.d['fen']==fen;assert w.doc.d['style']['dark']=='#123456';w.doc.dirty=False;w.close()

def test_failed_export_preserves_target(doc,tmp_path):
    p=tmp_path/'existing.tiff';p.write_bytes(b'original')
    with pytest.raises(ValueError):export_file(doc,doc.d,p,True)
    assert p.read_bytes()==b'original'

def test_svg_resource_portable(doc,tmp_path):
    from chessdiagram.render import builtin_svg
    p=tmp_path/'piece.svg';p.write_bytes(builtin_svg('P','Геометрический'));key=doc.add_resource(p)
    doc.d['sets']['Набор']={'P':key};doc.d['style']['piece_set']='Набор';project=tmp_path/'p.chessdiagram';doc.save(project);p.unlink()
    loaded=Document();loaded.load(project);export_file(loaded,loaded.d,tmp_path/'custom.svg')
    assert b'<image' not in (tmp_path/'custom.svg').read_bytes() # SVG pieces remain vector paths
