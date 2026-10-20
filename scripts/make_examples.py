import os,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from chessdiagram.model import Document
from chessdiagram.export import export_file,contact_sheet
app=QApplication([]);QFontDatabase.addApplicationFont('assets/DejaVuSans.ttf')
out=Path('examples');out.mkdir(exist_ok=True);doc=Document()
doc.d['name']='Задача № 1. Ход коня';doc.set_fen('4k3/8/8/3N4/8/8/8/4K3 w - - 0 1')
doc.d['objects']=[dict(kind='knight',layer='Стрелки',points=[[280,280],[360,120]],color='#d24d49',width=7,opacity=.8,head='Треугольник',head_size=22)]
for ext in ['png','svg','pdf']:export_file(doc,doc.d,out/('example_rgb.'+ext))
profile=os.environ.get('TEST_CMYK_ICC','/usr/share/color/icc/ghostscript/default_cmyk.icc')
if Path(profile).exists():
    doc.d['style']['icc']=doc.add_resource(profile)
    export_file(doc,doc.d,out/'example_cmyk.tiff',True);export_file(doc,doc.d,out/'example_cmyk.pdf',True)
doc.data['diagrams'].append(copy.deepcopy(doc.d));doc.data['diagrams'][1]['name']='Задача № 2. Ход коня';doc.data['diagrams'][1]['style']['piece_set']='Геометрический'
doc.save(out/'examples.chessdiagram');contact_sheet(doc,out/'worksheet_A4.pdf',cols=2,rows=3,gap=8)
