import copy,io,json,os,zipfile
from pathlib import Path
import pytest,chess
from chessdiagram.model import Document,diagram,square_at,square_xy,is_dark

@pytest.mark.parametrize('flipped',[False,True])
def test_geometry(flipped):
    assert sum(is_dark(s) for s in chess.SQUARES)==32
    assert is_dark(chess.A1)
    cells=set()
    for sq in chess.SQUARES:
        x,y=square_xy(sq,flipped);cells.add((x,y))
        assert square_at(x+40,y+40,flipped)==sq
        f,r=chess.square_file(sq),chess.square_rank(sq)
        if f<7:assert is_dark(sq)!=is_dark(sq+1)
        if r<7:assert is_dark(sq)!=is_dark(sq+8)
    assert len(cells)==64
    assert square_at(-1,0,flipped) is None
    assert square_at(640,0,flipped) is None

def test_start_position():
    b=chess.Board(Document().d['fen'])
    assert b.piece_at(chess.D1).symbol()=='Q';assert b.piece_at(chess.D8).symbol()=='q'
    assert b.piece_at(chess.E1).symbol()=='K';assert b.piece_at(chess.E8).symbol()=='k'
    assert all(b.piece_at(s).symbol()=='P' for s in range(8,16))
    assert all(b.piece_at(s).symbol()=='p' for s in range(48,56))
    assert b.is_valid()

@pytest.mark.parametrize('fen',[chess.STARTING_FEN,'8/8/8/8/8/8/8/8 w - - 0 1','r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'])
def test_fen(fen):
    d=Document();d.set_fen(fen);assert d.d['fen']==fen

def test_invalid_fen_transaction():
    d=Document();before=copy.deepcopy(d.data)
    with pytest.raises(ValueError):d.set_fen('garbage')
    assert d.data==before

def test_history_branch():
    d=Document();d.place(chess.A3,'Q');d.checkpoint('1');d.d['style']['dark']='#111111';d.checkpoint('2')
    d.restore(0);assert d.d['fen']==chess.STARTING_FEN
    d.restore(2);assert d.d['style']['dark']=='#111111'
    d.restore(1);d.place(chess.A4,'p');d.checkpoint('3');assert d.labels==['Новый проект','1','3']

def test_thousand_history():
    d=Document()
    for i in range(1010):d.d['name']=str(i);d.checkpoint(str(i))
    assert len(d.states)==1001;assert len(d.labels)==1001
    d.restore(0);assert d.d['name']=='9'

def test_save_resources_unicode(tmp_path):
    d=Document();p=tmp_path/'қазақша.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    key=d.add_resource(p);d.d['sets']['Набор']={'P':key};d.d['style']['piece_set']='Набор';d.checkpoint('Импорт')
    path=tmp_path/'Шахмат.chessdiagram';d.save(path);p.unlink();e=Document();e.load(path)
    assert e.data==d.data;assert e.resources==d.resources
    d.restore(0);d.save(path);e.load(path);assert e.data['resources']=={}

def test_corrupt_load_keeps_document(tmp_path):
    d=Document();before=copy.deepcopy(d.data);p=tmp_path/'bad.chessdiagram';p.write_text('bad')
    with pytest.raises(zipfile.BadZipFile):d.load(p)
    assert d.data==before

def test_version_rejected(tmp_path):
    p=tmp_path/'v.chessdiagram';data=Document().data;data['version']=99
    with zipfile.ZipFile(p,'w') as z:z.writestr('document.json',json.dumps(data))
    with pytest.raises(ValueError):Document().load(p)

def test_legal_moves():
    d=Document();d.d['legal']=True
    with pytest.raises(ValueError):d.move(chess.E2,chess.E5)
    d.move(chess.E2,chess.E4);b=chess.Board(d.d['fen']);assert b.piece_at(chess.E4).symbol()=='P';assert b.turn==chess.BLACK

def test_arbitrary_move_override():
    d=Document();d.d['piece_overrides'][str(chess.A1)]={'scale':1.1};d.move(chess.A1,chess.D4)
    assert chess.Board(d.d['fen']).piece_at(chess.D4).symbol()=='R'
    assert d.d['piece_overrides'][str(chess.D4)]['scale']==1.1

def test_pgn():
    d=Document();d.import_pgn('[Event "Тест"]\n\n1. e4 e5 2. Nf3 Nc6 *');d.goto_ply(4)
    b=chess.Board(d.d['fen']);assert b.piece_at(chess.C6).symbol()=='n'
    d.goto_ply(0);assert d.d['fen']==chess.STARTING_FEN
    d.place(chess.A3,'Q');assert d.d['pgn']==''
