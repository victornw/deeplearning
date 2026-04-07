import sqlite3
from datetime import date
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

        CREATE TABLE IF NOT EXISTS horarios_treino (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dia_semana INTEGER NOT NULL,
            horario TEXT NOT NULL,
            local TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS aulas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            horario TEXT NOT NULL,
            local TEXT NOT NULL,
            horario_id INTEGER REFERENCES horarios_treino(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aula_id INTEGER NOT NULL REFERENCES aulas(id) ON DELETE CASCADE,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(aula_id, aluno_id)
        );

        CREATE TABLE IF NOT EXISTS treinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            foto_caminho TEXT NOT NULL,
            total_rostos INTEGER,
            aula_id INTEGER REFERENCES aulas(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS presencas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL REFERENCES treinos(id) ON DELETE CASCADE,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            distancia REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'validada',
            UNIQUE(treino_id, aluno_id)
        );

        CREATE TABLE IF NOT EXISTS nao_identificados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            treino_id INTEGER NOT NULL REFERENCES treinos(id) ON DELETE CASCADE,
            face_caminho TEXT NOT NULL
        );
    """)
    conn.commit()

    # Migrations para bancos existentes
    for sql in [
        "ALTER TABLE treinos ADD COLUMN aula_id INTEGER REFERENCES aulas(id)",
        "ALTER TABLE presencas ADD COLUMN status TEXT NOT NULL DEFAULT 'validada'",
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass

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


def get_aluno_por_id(aluno_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
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


# --- Horarios de treino ---

def criar_horario(dia_semana: int, horario: str, local: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO horarios_treino (dia_semana, horario, local) VALUES (?, ?, ?)",
        (dia_semana, horario, local),
    )
    horario_id = cur.lastrowid
    conn.commit()
    conn.close()
    return horario_id


def listar_horarios() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM horarios_treino WHERE ativo = 1 ORDER BY dia_semana, horario"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deletar_horario(horario_id: int):
    conn = get_conn()
    conn.execute("UPDATE horarios_treino SET ativo = 0 WHERE id = ?", (horario_id,))
    conn.commit()
    conn.close()


# --- Aulas ---

def criar_aula(data: str, horario: str, local: str, horario_id: int | None = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO aulas (data, horario, local, horario_id) VALUES (?, ?, ?, ?)",
        (data, horario, local, horario_id),
    )
    aula_id = cur.lastrowid
    conn.commit()
    conn.close()
    return aula_id


def get_aula(aula_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM aulas WHERE id = ?", (aula_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_aulas(data: str | None = None) -> list[dict]:
    conn = get_conn()
    if data:
        rows = conn.execute("""
            SELECT a.*,
                COUNT(DISTINCT c.id) as total_checkins,
                COUNT(DISTINCT t.id) as treino_processado
            FROM aulas a
            LEFT JOIN checkins c ON c.aula_id = a.id
            LEFT JOIN treinos t ON t.aula_id = a.id
            WHERE a.data = ?
            GROUP BY a.id
            ORDER BY a.horario ASC
        """, (data,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT a.*,
                COUNT(DISTINCT c.id) as total_checkins,
                COUNT(DISTINCT t.id) as treino_processado
            FROM aulas a
            LEFT JOIN checkins c ON c.aula_id = a.id
            LEFT JOIN treinos t ON t.aula_id = a.id
            GROUP BY a.id
            ORDER BY a.data DESC, a.horario ASC
        """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def gerar_aulas_do_dia(data_str: str) -> list[dict]:
    """Cria aulas a partir da grade de horários para um dia, se ainda não existirem."""
    d = date.fromisoformat(data_str)
    dia_semana = d.weekday()  # 0=segunda, 6=domingo

    conn = get_conn()
    horarios = conn.execute(
        "SELECT * FROM horarios_treino WHERE dia_semana = ? AND ativo = 1",
        (dia_semana,)
    ).fetchall()

    aulas_criadas = []
    for h in horarios:
        existing = conn.execute(
            "SELECT * FROM aulas WHERE data = ? AND horario_id = ?",
            (data_str, h["id"])
        ).fetchone()
        if existing:
            aulas_criadas.append(dict(existing))
        else:
            cur = conn.execute(
                "INSERT INTO aulas (data, horario, local, horario_id) VALUES (?, ?, ?, ?)",
                (data_str, h["horario"], h["local"], h["id"]),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM aulas WHERE id = ?", (cur.lastrowid,)).fetchone()
            aulas_criadas.append(dict(row))

    conn.close()
    return aulas_criadas


# --- Checkins ---

def fazer_checkin(aula_id: int, aluno_id: int) -> bool:
    """Retorna True se criado, False se já existia."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO checkins (aula_id, aluno_id) VALUES (?, ?)",
            (aula_id, aluno_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def cancelar_checkin(aula_id: int, aluno_id: int):
    conn = get_conn()
    conn.execute(
        "DELETE FROM checkins WHERE aula_id = ? AND aluno_id = ?",
        (aula_id, aluno_id),
    )
    conn.commit()
    conn.close()


def get_checkins_aula(aula_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.aluno_id, c.created_at, a.nome
        FROM checkins c
        JOIN alunos a ON a.id = c.aluno_id
        WHERE c.aula_id = ?
        ORDER BY a.nome
    """, (aula_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_aluno_ids_com_checkin(aula_id: int) -> set[int]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT aluno_id FROM checkins WHERE aula_id = ?", (aula_id,)
    ).fetchall()
    conn.close()
    return {r["aluno_id"] for r in rows}


# --- Treinos ---

def criar_treino(data: str, foto_caminho: str, total_rostos: int, aula_id: int | None = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO treinos (data, foto_caminho, total_rostos, aula_id) VALUES (?, ?, ?, ?)",
        (data, foto_caminho, total_rostos, aula_id),
    )
    treino_id = cur.lastrowid
    conn.commit()
    conn.close()
    return treino_id


def registrar_presenca(treino_id: int, aluno_id: int, distancia: float, status: str = "validada") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO presencas (treino_id, aluno_id, distancia, status) VALUES (?, ?, ?, ?)",
        (treino_id, aluno_id, distancia, status),
    )
    presenca_id = cur.lastrowid
    conn.commit()
    conn.close()
    return presenca_id


def atualizar_status_presenca(presenca_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE presencas SET status = ? WHERE id = ?", (status, presenca_id))
    conn.commit()
    conn.close()


def registrar_nao_identificado(treino_id: int, face_caminho: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO nao_identificados (treino_id, face_caminho) VALUES (?, ?)",
        (treino_id, face_caminho),
    )
    face_id = cur.lastrowid
    conn.commit()
    conn.close()
    return face_id


def get_treino(treino_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_treinos() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*,
            COUNT(DISTINCT CASE WHEN p.status = 'validada' THEN p.aluno_id END) as presentes,
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
        SELECT p.id, p.distancia, p.status, a.nome, a.id as aluno_id
        FROM presencas p
        JOIN alunos a ON a.id = p.aluno_id
        WHERE p.treino_id = ?
        ORDER BY p.status, a.nome
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
        SELECT t.data, t.id as treino_id, p.distancia, p.status
        FROM presencas p
        JOIN treinos t ON t.id = p.treino_id
        JOIN alunos a ON a.id = p.aluno_id
        WHERE a.nome = ?
        ORDER BY t.data DESC
    """, (nome,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
