import copy, json, os, subprocess, sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import chess, pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from pypdf import PdfReader
from chessdiagram.model import Document
from chessdiagram.publishing import DEFAULT_LAYOUT, geometry, preview_page, export_publication
from chessdiagram.jobs import execute_job

@pytest.fixture(scope='session')
def app():return QApplication.instance() or QApplication([])

def test_multi_pgn_transaction():
    d=Document();count=d.import_games('[White "А"]\n[Black "Б"]\n\n1. e4 e5 *\n\n[White "В"]\n[Black "Г"]\n\n1. d4 d5 *')
    assert count==2 and len(d.data['diagrams'])==3
    d.goto_ply(2);assert chess.Board(d.d['fen']).piece_at(chess.E5)
    before=copy.deepcopy(d.data)
    with pytest.raises(ValueError):d.import_games('[Event "Broken"]\n\n1. e4 e5 2. Bh6 *')
    assert d.data==before

@pytest.mark.parametrize('paper,landscape',[('A4',False),('A5',True)])
def test_publication_geometry_and_pages(app,tmp_path,paper,landscape):
    d=Document();d.data['diagrams']=[copy.deepcopy(d.d) for _ in range(7)]
    opts={**DEFAULT_LAYOUT,'paper':paper,'landscape':landscape,'rows':2,'cols':2,'answer_lines':1}
    out=tmp_path/'Лист.pdf';export_publication(d,out,opts)
    pdf=PdfReader(out);assert len(pdf.pages)==2
    _,w,h,*_=geometry(opts);assert abs(float(pdf.pages[0].mediabox.width)-w/25.4*72)<.1
    assert abs(float(pdf.pages[0].mediabox.height)-h/25.4*72)<.1
    assert b' m' in pdf.pages[0].get_contents().get_data()
    im=preview_page(d,opts,0);assert not im.isNull();assert abs(im.height()/im.width()-h/w)<.002

def test_reject_overfull_page_preserves_file(app,tmp_path):
    p=tmp_path/'keep.pdf';p.write_bytes(b'existing')
    with pytest.raises(ValueError):export_publication(Document(),p,{**DEFAULT_LAYOUT,'cols':4,'rows':6,'margin':40})
    assert p.read_bytes()==b'existing'

def test_cmyk_publication(app,tmp_path):
    from chessdiagram.export import ghostscript
    icc=Path(os.environ.get('TEST_CMYK_ICC','/usr/share/color/icc/ghostscript/default_cmyk.icc'))
    if not icc.is_file() or not ghostscript():pytest.skip('ICC / Ghostscript unavailable')
    d=Document();d.d['style']['icc']=d.add_resource(icc);p=tmp_path/'cmyk.pdf';export_publication(d,p,DEFAULT_LAYOUT,True)
    pdf=PdfReader(p);profile=pdf.trailer['/Root']['/OutputIntents'][0].get_object()['/DestOutputProfile'].get_object();assert profile['/N']==4;assert profile.get_data()==icc.read_bytes()

def make_job(tmp_path,kind='diagrams'):
    doc=Document();doc.save(tmp_path/'project.chessdiagram');target=tmp_path/'result.svg'
    spec={'kind':kind,'outputs':[{'path':str(target),'index':0}]};(tmp_path/'job.json').write_text(json.dumps(spec),encoding='utf-8');return target

def test_cancel_does_not_overwrite(app,tmp_path):
    target=make_job(tmp_path);target.write_bytes(b'keep');(tmp_path/'cancel').touch();assert execute_job(tmp_path)==0
    assert target.read_bytes()==b'keep';result=json.loads((tmp_path/'result.json').read_text());assert result['cancelled'] and result['done']==0

def test_worker_cli_without_editor(tmp_path):
    target=make_job(tmp_path);main=Path(__file__).resolve().parents[1]/'main.py'
    result=subprocess.run([sys.executable,str(main),'--export-job',str(tmp_path)],capture_output=True,timeout=45)
    assert result.returncode==0,result.stderr.decode(errors='replace');assert target.stat().st_size>100;assert json.loads((tmp_path/'result.json').read_text())['done']==1

def test_studio_cancel_keeps_project(app):
    from chessdiagram.app import Window
    from chessdiagram.studio import ExportStudio
    w=Window(recover=False);before=copy.deepcopy(w.doc.data)
    for pages in (False,True):
        dlg=ExportStudio(w,pages=pages);dlg.show();app.processEvents();assert dlg.savebutton.isEnabled()
        if not pages:dlg.controls['board_mm'].setValue(70)
        dlg.update_preview();dlg.reject();assert w.doc.data==before
    w.doc.dirty=False;w.close()

@pytest.mark.parametrize('flipped',[False,True])
def test_drag_annotation_handle_and_undo(app,flipped):
    from chessdiagram.app import Window
    w=Window(recover=False);w.doc.d['style']['flipped']=flipped;w.doc.d['objects']=[dict(kind='arrow',layer='Стрелки',points=[[120,120],[280,280]],color='#ff0000')];w.commit('arrow');w.show();app.processEvents();w.canvas.fit();app.processEvents();w.canvas.selected=('object',0)
    def at(x,y):return w.canvas.mapFromScene(QPointF(640-x,640-y) if flipped else QPointF(x,y))
    QTest.mousePress(w.canvas.viewport(),Qt.LeftButton,pos=at(120,120));QTest.mouseMove(w.canvas.viewport(),at(200,120));QTest.mouseRelease(w.canvas.viewport(),Qt.LeftButton,pos=at(200,120))
    assert w.doc.d['objects'][0]['points'][0]==[200,120];w.undo(-1);assert w.doc.d['objects'][0]['points'][0]==[120,120];w.doc.dirty=False;w.close()

def test_recovery_paths_unique(app):
    from chessdiagram.app import Window
    a=Window(recover=False);b=Window(recover=False);assert a.recovery!=b.recovery;a.close();b.close()
