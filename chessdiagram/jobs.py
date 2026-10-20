"""Export isolation keeps the editor responsive and cancellation safe."""
import json, os, sys, tempfile
from pathlib import Path
from PySide6.QtCore import QProcess, QTimer, QByteArray
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QProgressDialog
from .model import Document
from .export import export_file
from .publishing import export_publication

def execute_job(folder):
    root=Path(folder);spec=json.loads((root/'job.json').read_text(encoding='utf-8'));doc=Document();doc.load(root/'project.chessdiagram')
    for key in doc.data['fonts']:
        if key in doc.resources:QFontDatabase.addApplicationFontFromData(QByteArray(doc.resources[key]))
    result={'done':0,'total':len(spec['outputs']),'cancelled':False,'error':''}
    try:
        for item in spec['outputs']:
            if (root/'cancel').exists():result['cancelled']=True;break
            target=Path(item['path']);target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.chess-export-',dir=target.parent) as stage:
                output=Path(stage)/('output'+target.suffix)
                if spec['kind']=='pages':export_publication(doc,output,spec['layout'],item.get('cmyk',False))
                else:export_file(doc,doc.data['diagrams'][item['index']],output,item.get('cmyk',False))
                if (root/'cancel').exists():result['cancelled']=True;break
                os.replace(output,target)
            result['done']+=1;(root/'progress.json').write_text(json.dumps(result),encoding='utf-8')
    except Exception as e:result['error']=str(e)
    (root/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');return 1 if result['error'] else 0

class ExportJob:
    def __init__(self,window,spec):
        self.window=window;self.temp=tempfile.TemporaryDirectory(prefix='chess-job-');self.root=Path(self.temp.name)
        window.doc.save(self.root/'project.chessdiagram',autosave=True);(self.root/'job.json').write_text(json.dumps(spec,ensure_ascii=False),encoding='utf-8')
        self.dialog=QProgressDialog('Подготовка экспорта…','Отмена',0,len(spec['outputs']),window);self.dialog.setWindowTitle('Экспорт');self.dialog.setAutoClose(False);self.dialog.setMinimumDuration(0);self.dialog.canceled.connect(self.cancel);self.dialog.show()
        self.process=QProcess(window);self.process.setProcessChannelMode(QProcess.MergedChannels);self.process.finished.connect(self.finished);self.process.errorOccurred.connect(self.failed)
        self.timer=QTimer(window);self.timer.timeout.connect(self.progress);self.timer.start(200)
        args=['--export-job',str(self.root)]
        if not getattr(sys,'frozen',False):args.insert(0,str(Path(__file__).resolve().parent.parent/'main.py'))
        self.process.start(sys.executable,args)
    def cancel(self):
        (self.root/'cancel').touch();self.window.statusBar().showMessage('Отмена: завершение текущей операции…')
    def progress(self):
        try:
            data=json.loads((self.root/'progress.json').read_text(encoding='utf-8'));self.dialog.setValue(data['done']);self.dialog.setLabelText(f"Готово {data['done']} из {data['total']}")
        except (OSError,ValueError):pass
    def failed(self,error):
        if error==QProcess.FailedToStart:self.finished(-1,QProcess.CrashExit)
    def finished(self,code,status):
        if getattr(self,'ended',False):return
        self.ended=True;self.timer.stop();self.timer.deleteLater();self.dialog.close();self.dialog.deleteLater()
        try:result=json.loads((self.root/'result.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):result={'error':'Процесс экспорта завершился неожиданно. '+bytes(self.process.readAllStandardOutput()).decode(errors='replace')[-1000:]}
        if result.get('error'):self.window.error(result['error'])
        else:self.window.statusBar().showMessage(f"Сохранено {result['done']} из {result['total']}."+(' Экспорт отменён.' if result['cancelled'] else ''),12000)
        self.window.export_job=None;self.process.deleteLater();self.temp.cleanup()
