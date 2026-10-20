"""Shared painter export and ICC conversion. No CMYK fallback without a profile."""
import io, os, shutil, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageCms
from PySide6.QtCore import QSize, QSizeF, QRectF, QMarginsF, QBuffer, QIODevice
from PySide6.QtGui import QImage,QPainter,QPdfWriter,QPageSize,QPageLayout
from PySide6.QtSvg import QSvgGenerator
from .render import Renderer

def raster(renderer,d,dpi):
    rect=renderer.rect(d); scale=d['style']['board_mm']/640/25.4*dpi
    w,h=max(1,round(rect.width()*scale)),max(1,round(rect.height()*scale))
    if w*h>100_000_000: raise ValueError('Изображение превышает 100 мегапикселей. Уменьшите DPI или размер.')
    q=QImage(w,h,QImage.Format_RGBA8888); q.fill(0)
    p=QPainter(q); p.scale(w/rect.width(),h/rect.height()); p.translate(-rect.x(),-rect.y()); renderer.draw(p,d);p.end()
    buf=QBuffer();buf.open(QIODevice.WriteOnly);q.save(buf,'PNG')
    return Image.open(io.BytesIO(bytes(buf.data()))).copy()

def profile_bytes(doc,d):
    key=d['style']['icc']
    if not key or key not in doc.resources: raise ValueError('Для CMYK импортируйте ICC-профиль вашей типографии.')
    b=doc.resources[key]; profile=ImageCms.ImageCmsProfile(io.BytesIO(b))
    if profile.profile.xcolor_space.strip()!='CMYK':raise ValueError('Выбранный профиль не является CMYK-профилем.')
    return b

def convert_cmyk(im,profile,intent=0):
    rgb=Image.new('RGB',im.size,'white');rgb.paste(im,mask=im.getchannel('A') if im.mode=='RGBA' else None)
    return ImageCms.profileToProfile(rgb,ImageCms.createProfile('sRGB'),ImageCms.ImageCmsProfile(io.BytesIO(profile)),outputMode='CMYK',renderingIntent=intent)

def softproof(im,profile,intent=0):
    rgb=ImageCms.createProfile('sRGB'); target=ImageCms.ImageCmsProfile(io.BytesIO(profile))
    transform=ImageCms.buildProofTransformFromOpenProfiles(rgb,rgb,target,'RGB','RGB',renderingIntent=intent,proofRenderingIntent=intent,flags=ImageCms.Flags.SOFTPROOFING)
    return ImageCms.applyTransform(im.convert('RGB'),transform)

def exact_pdf_size(path,width_mm,height_mm):
    from pypdf import PdfReader,PdfWriter
    reader=PdfReader(path); writer=PdfWriter()
    for page in reader.pages:
        new_page=writer.add_page(page);new_page.scale_to(width_mm/25.4*72,height_mm/25.4*72)
    out=io.BytesIO();writer.write(out);Path(path).write_bytes(out.getvalue())

def pdf_rgb(renderer,d,path):
    rect=renderer.rect(d); mm=d['style']['board_mm']/640
    writer=QPdfWriter(str(path));writer.setResolution(1200)
    writer.setPageSize(QPageSize(QSizeF(rect.width()*mm,rect.height()*mm),QPageSize.Millimeter))
    writer.setPageMargins(QMarginsF(0,0,0,0));writer.setTitle(d['name']);writer.setCreator('Конструктор шахматных диаграмм')
    p=QPainter(writer);p.scale(writer.width()/rect.width(),writer.height()/rect.height());p.translate(-rect.x(),-rect.y());renderer.draw(p,d);p.end();del p;del writer
    exact_pdf_size(path,rect.width()*mm,rect.height()*mm)

def ghostscript():
    import sys
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    paths=list((root/'ghostscript').glob('**/gswin64c.exe'))
    return str(paths[0]) if paths else shutil.which('gs') or shutil.which('gswin64c')

def cmyk_pdf(source,dest,profile,intent):
    gs=ghostscript()
    if not gs:raise ValueError('Для векторного CMYK PDF нужен включённый в сборку Ghostscript. Доступен CMYK TIFF.')
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject,ArrayObject,TextStringObject
    with tempfile.TemporaryDirectory() as td:
        icc=Path(td)/'output.icc';icc.write_bytes(profile); converted=Path(td)/'converted.pdf'
        args=[gs,'-dSAFER',f'--permit-file-read={icc}','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite','-dCompatibilityLevel=1.6',
              '-sColorConversionStrategy=CMYK','-dProcessColorModel=/DeviceCMYK',f'-dRenderIntent={intent}',
              '-dOverrideICC',f'-sOutputICCProfile={icc}',f'-sOutputFile={converted}',str(source)]
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,creationflags=0x08000000 if os.name=='nt' else 0)
        if result.returncode:raise RuntimeError('Ошибка преобразования PDF: '+result.stdout.decode(errors='replace')[-1500:])
        reader=PdfReader(converted); writer=PdfWriter();writer.append_pages_from_reader(reader)
        stream=DecodedStreamObject();stream.set_data(profile);stream[NameObject('/N')]=NumberObject(4)
        prof=writer._add_object(stream)
        intent_obj=DictionaryObject({NameObject('/Type'):NameObject('/OutputIntent'),NameObject('/S'):NameObject('/GTS_PDFX'),
          NameObject('/OutputConditionIdentifier'):TextStringObject('User CMYK ICC'),NameObject('/DestOutputProfile'):prof})
        writer._root_object[NameObject('/OutputIntents')]=ArrayObject([writer._add_object(intent_obj)])
        with open(dest,'wb') as f:writer.write(f)

def export_file(doc,d,path,cmyk=False):
    path=Path(path);ext=path.suffix.lower();renderer=Renderer(doc); s=d['style'];dpi=s['dpi']
    if cmyk and ext not in ('.tiff','.tif','.pdf'):raise ValueError('CMYK поддерживается только для TIFF и PDF.')
    profile=profile_bytes(doc,d) if cmyk else None
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(suffix=ext,dir=path.parent);os.close(fd)
    try:
        if ext=='.svg':
            rect=renderer.rect(d);mm=s['board_mm']/640
            g=QSvgGenerator();g.setFileName(tmp);g.setResolution(96)
            g.setSize(QSize(round(rect.width()*mm/25.4*96),round(rect.height()*mm/25.4*96)));g.setViewBox(rect);g.setTitle(d['name'])
            p=QPainter(g);renderer.draw(p,d);p.end();del p;del g
            # Physical dimensions must not be rounded to screen pixels.
            import re
            txt=Path(tmp).read_text(encoding='utf-8');txt=re.sub(r'width="[^"]+" height="[^"]+"',f'width="{rect.width()*mm:.6f}mm" height="{rect.height()*mm:.6f}mm"',txt,count=1)
            Path(tmp).write_text(txt,encoding='utf-8')
        elif ext=='.pdf':
            if cmyk:
                with tempfile.TemporaryDirectory() as td:
                    source=Path(td)/'rgb.pdf';pdf_rgb(renderer,d,source);cmyk_pdf(source,tmp,profile,s['intent'])
            else:pdf_rgb(renderer,d,tmp)
        elif ext in ('.png','.jpg','.jpeg','.tif','.tiff','.bmp'):
            im=raster(renderer,d,dpi);kw={'dpi':(dpi,dpi)}
            if cmyk:im=convert_cmyk(im,profile,s['intent']);kw['icc_profile']=profile
            elif ext in ('.jpg','.jpeg','.bmp'):
                bg=Image.new('RGB',im.size,'white');bg.paste(im,mask=im.getchannel('A'));im=bg
            if ext in ('.jpg','.jpeg'):kw['quality']=95
            if ext in ('.tif','.tiff'):kw['compression']='tiff_lzw'
            im.save(tmp,**kw)
        else:raise ValueError('Неподдерживаемый формат экспорта')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def contact_sheet(doc,path,paper='A4',cols=2,rows=3,gap=10):
    renderer=Renderer(doc);writer=QPdfWriter(str(path));writer.setResolution(300)
    writer.setPageSize(QPageSize(QPageSize.A4 if paper=='A4' else QPageSize.A5));writer.setPageMargins(QMarginsF(10,10,10,10))
    p=QPainter(writer);mm=300/25.4; w,h=writer.width(),writer.height();cw=(w-(cols-1)*gap*mm)/cols;ch=(h-(rows-1)*gap*mm)/rows
    from PySide6.QtGui import QFont
    for i,d in enumerate(doc.data['diagrams']):
        slot=i%(cols*rows)
        if i and slot==0:writer.newPage()
        x=(slot%cols)*(cw+gap*mm);y=(slot//cols)*(ch+gap*mm)
        p.save();p.translate(x,y);f=QFont('DejaVu Sans');f.setPointSize(10);p.setFont(f)
        p.drawText(QRectF(0,0,cw,8*mm),0,d['name'])
        rect=renderer.rect(d);scale=min(cw/rect.width(),(ch-10*mm)/rect.height())
        p.translate((cw-rect.width()*scale)/2,10*mm);p.scale(scale,scale);p.translate(-rect.x(),-rect.y());renderer.draw(p,d);p.restore()
    p.end();del p;del writer
    exact_pdf_size(path,210 if paper=='A4' else 148,297 if paper=='A4' else 210)
