import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "jiuface.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS aluno_fotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            caminho TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS treinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            foto_caminho TEXT NOT NULL,
            total_rostos INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS presencas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL REFERENCES treinos(id) ON DELETE CASCADE,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            distancia REAL NOT NULL,
            UNIQUE(treino_id, aluno_id)
        );

        CREATE TABLE IF NOT EXISTS nao_identificados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL REFERENCES treinos(id) ON DELETE CASCADE,
            face_caminho TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# --- Alunos ---

def criar_aluno(nome: str) -> int:
    conn = get_conn()
    cur = conn.execute("INSERT INTO alunos (nome) VALUES (?)", (nome,))
    aluno_id = cur.lastrowid
    conn.commit()
    conn.close()
    return aluno_id


def get_aluno_por_nome(nome: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM alunos WHERE nome = ?", (nome,)).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_alunos() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM alunos ORDER BY nome").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def adicionar_foto(aluno_id: int, caminho: str):
    conn = get_conn()
    conn.execute("INSERT INTO aluno_fotos (aluno_id, caminho) VALUES (?, ?)", (aluno_id, caminho))
    conn.commit()
    conn.close()


def get_fotos_aluno(aluno_id: int) -> list[str]:
    conn = get_conn()
    rows = conn.execute("SELECT caminho FROM aluno_fotos WHERE aluno_id = ?", (aluno_id,)).fetchall()
    conn.close()
    return [r["caminho"] for r in rows]


# --- Treinos ---

def criar_treino(data: str, foto_caminho: str, total_rostos: int) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO treinos (data, foto_caminho, total_rostos) VALUES (?, ?, ?)",
        (data, foto_caminho, total_rostos),
    )
    treino_id = cur.lastrowid
    conn.commit()
    conn.close()
    return treino_id


def registrar_presenca(treino_id: int, aluno_id: int, distancia: float):
    conn = get_conn()
    conn.execute(
        "INSERT INTO presencas (treino_id, aluno_id, distancia) VALUES (?, ?, ?)",
        (treino_id, aluno_id, distancia),
    )
    conn.commit()
    conn.close()


def registrar_nao_identificado(treino_id: int, face_caminho: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO nao_identificados (treino_id, face_caminho) VALUES (?, ?)",
        (treino_id, face_caminho),
    )
    conn.commit()
    conn.close()


def get_treino(treino_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_treinos() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*,
            COUNT(DISTINCT p.aluno_id) as presentes,
            COUNT(DISTINCT n.id) as nao_identificados
        FROM treinos t
        LEFT JOIN presencas p ON p.treino_id = t.id
        LEFT JOIN nao_identificados n ON n.treino_id = t.id
        GROUP BY t.id
        ORDER BY t.data DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_presencas_treino(treino_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.nome, p.distancia
        FROM presencas p
        JOIN alunos a ON a.id = p.aluno_id
        WHERE p.treino_id = ?
        ORDER BY a.nome
    """, (treino_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_nao_identificados_treino(treino_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM nao_identificados WHERE treino_id = ?", (treino_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_historico_aluno(nome: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.data, t.id as treino_id, p.distancia
        FROM presencas p
        JOIN treinos t ON t.id = p.treino_id
        JOIN alunos a ON a.id = p.aluno_id
        WHERE a.nome = ?
        ORDER BY t.data DESC
    """, (nome,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
