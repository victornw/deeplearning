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
    # Remove fotos
    aluno_dir = FOTOS_ALUNOS_DIR / str(aluno_id)
    if aluno_dir.exists():
        shutil.rmtree(aluno_dir)
    return {"ok": True, "nome": aluno["nome"]}


@app.get("/alunos/{aluno_id}/historico")
def historico_aluno(aluno_id: int):
    aluno = _get_aluno_or_404(aluno_id)
    hist = db.get_historico_aluno(aluno["nome"])
    return {"aluno": aluno["nome"], "treinos": hist}


# --- Treinos ---


@app.get("/treinos")
def listar_treinos():
    return db.listar_treinos()


@app.post("/treinos", status_code=201)
async def processar_presenca(
    foto: UploadFile = File(),
    data_treino: str = Form(default=""),
):
    data_str = data_treino or date.today().isoformat()

    # Save uploaded photo
    treino_dir = TREINOS_DIR / data_str
    treino_dir.mkdir(parents=True, exist_ok=True)
    foto_path = treino_dir / foto.filename
    with open(foto_path, "wb") as f:
        shutil.copyfileobj(foto.file, f)

    # Extract faces
    faces = face.extract_faces(str(foto_path))
    if not faces:
        raise HTTPException(status_code=422, detail="Nenhum rosto detectado na foto.")

    treino_id = db.criar_treino(data_str, str(foto_path), len(faces))

    # Save crops to temp
    temp_dir = DATA_DIR / ".temp_faces"
    temp_dir.mkdir(exist_ok=True)

    crop_paths = {}
    for f_obj in faces:
        p = str(temp_dir / f"face_{f_obj['index']}.jpg")
        face.save_crop(f_obj["crop"], p)
        crop_paths[f_obj["index"]] = p

    # Match
    alunos = db.listar_alunos()
    matches = {}
    matched_indices = set()
    presentes = []

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
            db.registrar_presenca(treino_id, aluno["id"], best_dist)
            presentes.append({"nome": aluno["nome"], "distancia": round(best_dist, 4)})

    # Save unidentified
    nao_id_dir = treino_dir / "nao_identificados"
    nao_id_dir.mkdir(exist_ok=True)
    nao_identificados = []

    for f_obj in faces:
        if f_obj["index"] not in matched_indices:
            fp = nao_id_dir / f"rosto_{f_obj['index']}.jpg"
            face.save_crop(f_obj["crop"], str(fp))
            db.registrar_nao_identificado(treino_id, str(fp))
            nao_identificados.append(f_obj["index"])

    # Result image
    match_display = {idx: (nome, dist) for idx, (nome, dist, _) in matches.items()}
    result_path = str(treino_dir / "resultado.jpg")
    face.generate_result_image(str(foto_path), faces, match_display, result_path)

    shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "treino_id": treino_id,
        "data": data_str,
        "total_rostos": len(faces),
        "presentes": presentes,
        "nao_identificados": len(nao_identificados),
    }


@app.get("/treinos/{treino_id}")
def detalhe_treino(treino_id: int):
    treino = db.get_treino(treino_id)
    if not treino:
        raise HTTPException(status_code=404, detail="Treino nao encontrado.")

    presencas = db.get_presencas_treino(treino_id)
    nao_ids = db.get_nao_identificados_treino(treino_id)

    return {
        **treino,
        "presentes": presencas,
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
