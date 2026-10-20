"""Versioned document model; no GUI objects are persisted."""
from __future__ import annotations
import copy, hashlib, io, json, os, tempfile, zipfile
from pathlib import Path
import chess, chess.pgn

LAYERS = ['Фон','Рамка','Клетки','Координаты','Подсветка','Фигуры','Стрелки','Графика','Текст']
STYLE = dict(board_mm=120.0, margin=42.0, canvas_extra_x=0.0, canvas_extra_y=0.0,
    light='#f1eedf', dark='#608275', background='#ffffff', board_opacity=1.0,
    light_texture='', dark_texture='', board_image='', gradient=False, gradient_end='#c8cfbd',
    grid=False, grid_color='#34463f', grid_width=1.0, flipped=False,
    frame=True, frame_width=8.0, frame_color='#233b32', frame_kind='Одинарная',
    frame_radius=0.0, frame_gap=0.0, frame_opacity=1.0, frame_shadow=False, frame_texture='',
    coords='Снаружи', sides='Четыре', letters=True, numbers=True, font='DejaVu Sans',
    font_size=18.0, font_bold=False, font_italic=False, coord_color='#263d34', coord_offset=18.0,
    piece_scale=0.85, white_scale=1.0, black_scale=1.0, piece_dx=0.0, piece_dy=0.0,
    piece_opacity=1.0, piece_set='Классический', dpi=300, icc='', intent=0, transparent=False)

def diagram(name='Диаграмма 1'):
    return dict(name=name, fen=chess.STARTING_FEN, style=copy.deepcopy(STYLE), objects=[],
        piece_overrides={}, sets={}, layers=[dict(name=n,visible=True,locked=False) for n in LAYERS],
        pgn='', ply=0, legal=False)

def project():
    return dict(format='ChessDiagramConstructor', version=1, diagrams=[diagram()], active=0,
                resources={}, fonts=[])

def square_at(x,y,flipped=False):
    if not (0 <= x < 640 and 0 <= y < 640): return None
    col,row=int(x//80),int(y//80)
    return chess.square(7-col if flipped else col, row if flipped else 7-row)

def square_xy(sq,flipped=False):
    f,r=chess.square_file(sq),chess.square_rank(sq)
    return ((7-f if flipped else f)*80,(r if flipped else 7-r)*80)

def is_dark(sq): return (chess.square_file(sq)+chess.square_rank(sq))%2==0

def validate(data):
    if data.get('format')!='ChessDiagramConstructor' or data.get('version')!=1:
        raise ValueError('Неподдерживаемый формат или версия проекта')
    ds=data.get('diagrams')
    if not isinstance(ds,list) or not 1<=len(ds)<=10000: raise ValueError('Некорректный список диаграмм')
    if not isinstance(data.get('active'),int) or not 0<=data['active']<len(ds): raise ValueError('Неверная активная диаграмма')
    for d in ds:
        chess.Board(d['fen'])
        s=d['style']
        for key,value in STYLE.items(): s.setdefault(key,copy.deepcopy(value))
        for key in ['board_mm','margin','canvas_extra_x','canvas_extra_y']:
            if not isinstance(s[key],(float,int)) or not 0<=s[key]<=10000: raise ValueError('Недопустимые размеры')
        if s['board_mm']<1: raise ValueError('Слишком маленькая доска')
        if not isinstance(d['objects'],list) or len(d['objects'])>100000: raise ValueError('Слишком много объектов')
    return data

class Document:
    def __init__(self):
        self.data=project(); self.resources={}; self.path=None; self.dirty=False
        self.states=[copy.deepcopy(self.data)]; self.labels=['Новый проект']; self.cursor=0
    @property
    def d(self): return self.data['diagrams'][self.data['active']]
    def checkpoint(self,label):
        if self.data==self.states[self.cursor]: return False
        self.states=self.states[:self.cursor+1]; self.labels=self.labels[:self.cursor+1]
        self.states.append(copy.deepcopy(self.data)); self.labels.append(label)
        if len(self.states)>1001: self.states.pop(0); self.labels.pop(0)
        self.cursor=len(self.states)-1; self.dirty=True; return True
    def restore(self,index):
        if 0<=index<len(self.states):
            self.cursor=index; self.data=copy.deepcopy(self.states[index]); self.dirty=True
    def add_resource(self,path):
        p=Path(path); b=p.read_bytes()
        if len(b)>64*1024*1024: raise ValueError('Ресурс больше 64 МБ')
        key=hashlib.sha256(b).hexdigest()+p.suffix.lower()
        self.resources[key]=b; self.data['resources'][key]=p.name
        return key
    def save(self,path,autosave=False):
        path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        validate(copy.deepcopy(self.data))
        fd,tmp=tempfile.mkstemp(prefix='.chess-',suffix='.tmp',dir=path.parent); os.close(fd)
        try:
            with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('document.json',json.dumps(self.data,ensure_ascii=False))
                for key in self.data['resources']:
                    z.writestr('resources/'+key,self.resources[key])
            with open(tmp,'rb+') as f: os.fsync(f.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        if not autosave: self.path=str(path); self.dirty=False
    def load(self,path):
        with zipfile.ZipFile(path) as z:
            if sum(x.file_size for x in z.infolist())>512*1024*1024: raise ValueError('Проект превышает 512 МБ')
            if z.getinfo('document.json').file_size>32*1024*1024: raise ValueError('Слишком большой документ')
            data=validate(json.loads(z.read('document.json')))
            resources={key:z.read('resources/'+key) for key in data['resources']}
        self.data=data; self.resources=resources; self.path=str(path); self.dirty=False
        self.states=[copy.deepcopy(data)]; self.labels=['Открытие проекта']; self.cursor=0
    def set_fen(self,fen):
        board=chess.Board(fen.strip()); self.d['fen']=board.fen(en_passant='fen')
        self.d['pgn']=''; self.d['ply']=0; self.d['piece_overrides']={}
    def move(self,source,target,promotion=chess.QUEEN):
        if source==target: return
        b=chess.Board(self.d['fen']); p=b.piece_at(source)
        if not p: return
        if self.d['legal']:
            m=chess.Move(source,target,promotion=promotion if p.piece_type==chess.PAWN and chess.square_rank(target) in (0,7) else None)
            if m not in b.legal_moves: raise ValueError('Недопустимый ход')
            if self.d['pgn']:
                game=chess.pgn.read_game(io.StringIO(self.d['pgn']));node=game
                for _ in range(self.d['ply']):node=node.variation(0)
                node.variations.clear();node.add_variation(m)
            else:
                game=chess.pgn.Game.from_board(b);game.add_variation(m);self.d['ply']=0
            self.d['pgn']=str(game);self.d['ply']+=1;b.push(m)
        else:
            b.remove_piece_at(source); b.set_piece_at(target,p)
        self.d['fen']=b.fen(en_passant='fen')
        if not self.d['legal']:self.d['pgn']='';self.d['ply']=0
        overrides=self.d['piece_overrides']; overrides.pop(str(target),None)
        if str(source) in overrides: overrides[str(target)]=overrides.pop(str(source))
    def place(self,sq,symbol):
        b=chess.Board(self.d['fen']); b.set_piece_at(sq,chess.Piece.from_symbol(symbol) if symbol else None)
        self.d['fen']=b.fen(en_passant='fen'); self.d['pgn']=''; self.d['ply']=0
        self.d['piece_overrides'].pop(str(sq),None)
    def import_games(self,text):
        stream=io.StringIO(text);games=[]
        while True:
            game=chess.pgn.read_game(stream)
            if game is None:break
            if game.errors:raise ValueError('Ошибка в партии № '+str(len(games)+1))
            if len(games)>=1000:raise ValueError('За один импорт допускается не более 1000 партий')
            d=diagram(f"{game.headers.get('White','?')} — {game.headers.get('Black','?')}")
            d['pgn']=str(game);d['fen']=game.board().fen();d['style']=copy.deepcopy(self.d['style']);d['sets']=copy.deepcopy(self.d['sets']);games.append(d)
        if not games:raise ValueError('В файле не найдено партий')
        if len(games)+len(self.data['diagrams'])>10000:raise ValueError('Слишком много диаграмм в проекте')
        self.data['active']=len(self.data['diagrams']);self.data['diagrams'].extend(games)
        return len(games)
    def import_pgn(self,text):
        g=chess.pgn.read_game(io.StringIO(text))
        if g is None or g.errors: raise ValueError('Не удалось прочитать корректную партию PGN')
        self.d['pgn']=str(g); self.d['ply']=0; self.d['fen']=g.board().fen()
    def goto_ply(self,ply):
        if not self.d['pgn']: return
        g=chess.pgn.read_game(io.StringIO(self.d['pgn'])); moves=list(g.mainline_moves())
        ply=max(0,min(ply,len(moves))); b=g.board()
        for m in moves[:ply]: b.push(m)
        self.d['fen']=b.fen(en_passant='fen'); self.d['ply']=ply; self.d['piece_overrides']={}
