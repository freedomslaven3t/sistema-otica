"""Conexão com o banco. Offline = SQLite (um arquivo). Online = PostgreSQL via DATABASE_URL."""
import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

import util

BASE = Path(__file__).parent
DADOS = Path(os.getenv("DADOS_DIR", BASE / "dados"))


def _url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        for velho in ("postgres://", "postgresql://"):
            if url.startswith(velho):
                return "postgresql+psycopg2://" + url[len(velho):]
        return url
    DADOS.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DADOS / 'otica.db'}"


engine = create_engine(_url(), pool_pre_ping=True)
Sessao = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
SQLITE = engine.dialect.name == "sqlite"

if SQLITE:
    @event.listens_for(engine, "connect")
    def _ligar_chaves(conexao, _):
        conexao.execute("PRAGMA foreign_keys=ON")


def criar_tabelas():
    from modelos import Base
    Base.metadata.create_all(engine)


# ---------- backup automático (só SQLite) ----------
_dia_do_backup = None


def arquivo_banco() -> Path:
    return Path(engine.url.database)


def backup_diario(manter=30):
    """Uma cópia por dia em dados/backups. Chamado a cada requisição, mas só age uma vez ao dia."""
    global _dia_do_backup
    if not SQLITE or _dia_do_backup == util.hoje():
        return
    _dia_do_backup = util.hoje()
    origem = arquivo_banco()
    if not origem.exists():
        return
    pasta = DADOS / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"otica_{_dia_do_backup.isoformat()}.db"
    if not destino.exists():
        src, dst = sqlite3.connect(origem), sqlite3.connect(destino)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
    for velho in sorted(pasta.glob("otica_*.db"))[:-manter]:
        velho.unlink()


def listar_backups():
    pasta = DADOS / "backups"
    return sorted((p.name for p in pasta.glob("otica_*.db")), reverse=True) if pasta.exists() else []


def copia_do_banco() -> bytes:
    """Cópia consistente do banco SQLite, em memória, para download."""
    src = sqlite3.connect(arquivo_banco())
    dst = sqlite3.connect(":memory:")
    try:
        src.backup(dst)
        return dst.serialize()
    finally:
        dst.close(); src.close()
