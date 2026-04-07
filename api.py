import shutil
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import db
import face

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
FOTOS_ALUNOS_DIR = DATA_DIR / "alunos"
TREINOS_DIR = DATA_DIR / "treinos"

app = FastAPI(title="JiuFace", description="Presenca por reconhecimento facial")

db.init_db()

STATIC_DIR = BASE_DIR / "static"


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text()


# --- Alunos ---

@app.get("/alunos")
def listar_alunos():
    alunos = db.listar_alunos()
    for a in alunos:
        a["fotos"] = len(db.get_fotos_aluno(a["id"]))
    return alunos


@app.post("/alunos", status_code=201)
async def cadastrar_aluno(nome: str = Form(), foto: UploadFile = File()):
    aluno = db.get_aluno_por_nome(nome)
    if aluno:
        aluno_id = aluno["id"]
    else:
        aluno_id = db.criar_aluno(nome)

    aluno_dir = FOTOS_ALUNOS_DIR / str(aluno_id)
    aluno_dir.mkdir(parents=True, exist_ok=True)

    destino = aluno_dir / foto.filename
    with open(destino, "wb") as f:
        shutil.copyfileobj(foto.file, f)

    db.adicionar_foto(aluno_id, str(destino))

    return {"id": aluno_id, "nome": nome, "foto": str(destino)}


@app.delete("/alunos/{aluno_id}")
def deletar_aluno(aluno_id: int):
    aluno = _get_aluno_or_404(aluno_id)
    conn = db.get_conn()
    conn.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))
    conn.commit()
    conn.close()
    aluno_dir = FOTOS_ALUNOS_DIR / str(aluno_id)
    if aluno_dir.exists():
        shutil.rmtree(aluno_dir)
    return {"ok": True, "nome": aluno["nome"]}


@app.get("/alunos/{aluno_id}/historico")
def historico_aluno(aluno_id: int):
    aluno = _get_aluno_or_404(aluno_id)
    hist = db.get_historico_aluno(aluno["nome"])
    return {"aluno": aluno["nome"], "treinos": hist}


# --- Horários de treino ---

@app.get("/horarios")
def listar_horarios():
    return db.listar_horarios()


@app.post("/horarios", status_code=201)
def criar_horario(dia_semana: int = Form(), horario: str = Form(), local: str = Form()):
    if not (0 <= dia_semana <= 6):
        raise HTTPException(status_code=422, detail="dia_semana deve ser entre 0 (segunda) e 6 (domingo).")
    horario_id = db.criar_horario(dia_semana, horario, local)
    return {"id": horario_id, "dia_semana": dia_semana, "horario": horario, "local": local}


@app.delete("/horarios/{horario_id}")
def deletar_horario(horario_id: int):
    db.deletar_horario(horario_id)
    return {"ok": True}


# --- Aulas ---

@app.get("/aulas")
def listar_aulas(data: str | None = None):
    return db.listar_aulas(data)


@app.post("/aulas", status_code=201)
def criar_aula(
    data: str = Form(),
    horario: str = Form(),
    local: str = Form(),
    horario_id: int | None = Form(default=None),
):
    aula_id = db.criar_aula(data, horario, local, horario_id)
    return {"id": aula_id, "data": data, "horario": horario, "local": local}


@app.post("/aulas/gerar")
def gerar_aulas_do_dia(data: str = Form()):
    aulas = db.gerar_aulas_do_dia(data)
    return aulas


@app.get("/aulas/{aula_id}")
def detalhe_aula(aula_id: int):
    aula = db.get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada.")
    checkins = db.get_checkins_aula(aula_id)
    return {**aula, "checkins": checkins}


@app.get("/aulas/{aula_id}/checkins")
def listar_checkins(aula_id: int):
    aula = db.get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada.")
    return db.get_checkins_aula(aula_id)


@app.post("/aulas/{aula_id}/checkins", status_code=201)
def fazer_checkin(aula_id: int, aluno_id: int = Form()):
    aula = db.get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula nao encontrada.")
    aluno = db.get_aluno_por_id(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    criado = db.fazer_checkin(aula_id, aluno_id)
    return {"ok": True, "novo": criado, "aluno": aluno["nome"]}


@app.delete("/aulas/{aula_id}/checkins/{aluno_id}")
def cancelar_checkin(aula_id: int, aluno_id: int):
    db.cancelar_checkin(aula_id, aluno_id)
    return {"ok": True}


# --- Treinos ---

@app.get("/treinos")
def listar_treinos():
    return db.listar_treinos()


@app.post("/treinos", status_code=201)
async def processar_presenca(
    foto: UploadFile = File(),
    data_treino: str = Form(default=""),
    aula_id: int | None = Form(default=None),
):
    # Determina data e valida aula
    aula = None
    if aula_id:
        aula = db.get_aula(aula_id)
        if not aula:
            raise HTTPException(status_code=404, detail="Aula nao encontrada.")
        data_str = aula["data"]
    else:
        data_str = data_treino or date.today().isoformat()

    # Salva foto
    treino_dir = TREINOS_DIR / data_str
    treino_dir.mkdir(parents=True, exist_ok=True)
    foto_path = treino_dir / foto.filename
    with open(foto_path, "wb") as f:
        shutil.copyfileobj(foto.file, f)

    # Extrai rostos
    faces = face.extract_faces(str(foto_path))
    if not faces:
        raise HTTPException(status_code=422, detail="Nenhum rosto detectado na foto.")

    treino_id = db.criar_treino(data_str, str(foto_path), len(faces), aula_id)

    # Salva crops temporários
    temp_dir = DATA_DIR / ".temp_faces"
    temp_dir.mkdir(exist_ok=True)

    crop_paths = {}
    for f_obj in faces:
        p = str(temp_dir / f"face_{f_obj['index']}.jpg")
        face.save_crop(f_obj["crop"], p)
        crop_paths[f_obj["index"]] = p

    # IDs de quem fez checkin (vazio se não há aula vinculada)
    ids_com_checkin: set[int] = set()
    if aula_id:
        ids_com_checkin = db.get_aluno_ids_com_checkin(aula_id)

    # Matching
    alunos = db.listar_alunos()
    matches: dict[int, tuple[str, float, int]] = {}  # face_idx → (nome, dist, aluno_id)
    matched_indices: set[int] = set()

    for aluno in alunos:
        fotos_aluno = db.get_fotos_aluno(aluno["id"])
        if not fotos_aluno:
            continue

        best_dist = float("inf")
        best_face = None

        for fa in fotos_aluno:
            for idx, cp in crop_paths.items():
                if idx in matched_indices:
                    continue
                matched, dist = face.match_face(fa, cp)
                if matched and dist < best_dist:
                    best_dist = dist
                    best_face = idx

        if best_face is not None:
            matches[best_face] = (aluno["nome"], best_dist, aluno["id"])
            matched_indices.add(best_face)

    # Categoriza resultados
    validados = []
    recusados = []
    pendentes = []
    alunos_na_foto: set[int] = set()

    for face_idx, (nome, dist, aluno_id) in matches.items():
        alunos_na_foto.add(aluno_id)
        if ids_com_checkin:
            if aluno_id in ids_com_checkin:
                presenca_id = db.registrar_presenca(treino_id, aluno_id, dist, "validada")
                validados.append({"presenca_id": presenca_id, "nome": nome, "distancia": round(dist, 4)})
            else:
                presenca_id = db.registrar_presenca(treino_id, aluno_id, dist, "pendente")
                pendentes.append({"presenca_id": presenca_id, "nome": nome, "distancia": round(dist, 4)})
        else:
            presenca_id = db.registrar_presenca(treino_id, aluno_id, dist, "validada")
            validados.append({"presenca_id": presenca_id, "nome": nome, "distancia": round(dist, 4)})

    # Alunos que fizeram checkin mas não estão na foto → presença recusada
    if ids_com_checkin:
        for aluno_id in ids_com_checkin - alunos_na_foto:
            aluno = db.get_aluno_por_id(aluno_id)
            if aluno:
                db.registrar_presenca(treino_id, aluno_id, 0.0, "recusada")
                recusados.append({"nome": aluno["nome"]})

    # Rostos não identificados
    nao_id_dir = treino_dir / "nao_identificados"
    nao_id_dir.mkdir(exist_ok=True)
    nao_identificados = []

    for f_obj in faces:
        if f_obj["index"] not in matched_indices:
            fp = nao_id_dir / f"rosto_{f_obj['index']}.jpg"
            face.save_crop(f_obj["crop"], str(fp))
            face_id = db.registrar_nao_identificado(treino_id, str(fp))
            nao_identificados.append({"face_id": face_id})

    # Imagem resultado
    match_display = {idx: (nome, dist) for idx, (nome, dist, _) in matches.items()}
    result_path = str(treino_dir / "resultado.jpg")
    face.generate_result_image(str(foto_path), faces, match_display, result_path)

    shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "treino_id": treino_id,
        "aula_id": aula_id,
        "data": data_str,
        "total_rostos": len(faces),
        "validados": validados,
        "recusados": recusados,
        "pendentes": pendentes,
        "nao_identificados": nao_identificados,
    }


@app.post("/treinos/{treino_id}/confirmar/{presenca_id}")
def confirmar_presenca(treino_id: int, presenca_id: int):
    treino = db.get_treino(treino_id)
    if not treino:
        raise HTTPException(status_code=404, detail="Treino nao encontrado.")
    db.atualizar_status_presenca(presenca_id, "validada")
    return {"ok": True}


@app.post("/treinos/{treino_id}/nao-identificados/{face_id}/nomear")
async def nomear_nao_identificado(treino_id: int, face_id: int, nome: str = Form()):
    treino = db.get_treino(treino_id)
    if not treino:
        raise HTTPException(status_code=404, detail="Treino nao encontrado.")

    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM nao_identificados WHERE id = ? AND treino_id = ?",
        (face_id, treino_id),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Rosto nao encontrado.")

    face_caminho = row["face_caminho"]

    # Cria ou reutiliza o aluno
    aluno = db.get_aluno_por_nome(nome)
    if aluno:
        aluno_id = aluno["id"]
    else:
        aluno_id = db.criar_aluno(nome)

    # Copia o crop como foto do aluno
    aluno_dir = FOTOS_ALUNOS_DIR / str(aluno_id)
    aluno_dir.mkdir(parents=True, exist_ok=True)
    dest = aluno_dir / Path(face_caminho).name
    shutil.copy2(face_caminho, dest)
    db.adicionar_foto(aluno_id, str(dest))

    # Registra presença como validada
    try:
        db.registrar_presenca(treino_id, aluno_id, 0.0, "validada")
    except Exception:
        pass  # já tem presença

    # Remove da lista de não identificados
    conn = db.get_conn()
    conn.execute("DELETE FROM nao_identificados WHERE id = ?", (face_id,))
    conn.commit()
    conn.close()

    return {"ok": True, "aluno_id": aluno_id, "nome": nome}


@app.get("/treinos/{treino_id}")
def detalhe_treino(treino_id: int):
    treino = db.get_treino(treino_id)
    if not treino:
        raise HTTPException(status_code=404, detail="Treino nao encontrado.")

    presencas = db.get_presencas_treino(treino_id)
    nao_ids = db.get_nao_identificados_treino(treino_id)

    return {
        **treino,
        "presencas": presencas,
        "nao_identificados": [{"id": n["id"], "face_caminho": n["face_caminho"]} for n in nao_ids],
    }


@app.get("/treinos/{treino_id}/resultado")
def imagem_resultado(treino_id: int):
    treino = db.get_treino(treino_id)
    if not treino:
        raise HTTPException(status_code=404, detail="Treino nao encontrado.")

    treino_dir = Path(treino["foto_caminho"]).parent
    resultado = treino_dir / "resultado.jpg"
    if not resultado.exists():
        raise HTTPException(status_code=404, detail="Imagem resultado nao encontrada.")

    return FileResponse(str(resultado), media_type="image/jpeg")


@app.get("/treinos/{treino_id}/nao-identificados/{face_id}")
def imagem_nao_identificado(treino_id: int, face_id: int):
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM nao_identificados WHERE id = ? AND treino_id = ?",
        (face_id, treino_id),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Rosto nao encontrado.")

    path = Path(row["face_caminho"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")

    return FileResponse(str(path), media_type="image/jpeg")


# --- Helpers ---

def _get_aluno_or_404(aluno_id: int) -> dict:
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Aluno nao encontrado.")
    return dict(row)
