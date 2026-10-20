# Windows-only build. Qt and Python runtime are bundled in an onedir distribution.
from pathlib import Path
root=Path(SPECPATH)
datas=[(str(root/'assets'),'assets'),(str(root/'LICENSES'),'LICENSES'),(str(root/'LICENSE'),'.'),(str(root/'RELEASE_0.2.md'),'.'),(str(root/'РУКОВОДСТВО.md'),'.')]
if (root/'ghostscript').exists():datas.append((str(root/'ghostscript'),'ghostscript'))
a=Analysis([str(root/'main.py')],pathex=[str(root)],binaries=[],datas=datas,
           hiddenimports=['PIL.ImageCms','PIL.TiffImagePlugin','PIL.JpegImagePlugin','PySide6.QtSvg'],
           excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtWebEngineQuick','PySide6.QtPdf','PySide6.QtMultimedia'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ChessDiagramConstructor',debug=False,strip=False,upx=False,console=False,icon=str(root/'assets'/'app.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ChessDiagramConstructor')
