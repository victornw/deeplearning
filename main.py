import argparse
import shutil
from datetime import date
from pathlib import Path

import db
import face

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
FOTOS_ALUNOS_DIR = DATA_DIR / "alunos"
TREINOS_DIR = DATA_DIR / "treinos"


def cmd_cadastrar(args):
    foto_path = Path(args.foto)
    if not foto_path.exists():
        print(f"Erro: foto '{args.foto}' nao encontrada.")
        return

    aluno = db.get_aluno_por_nome(args.nome)
    if aluno:
        aluno_id = aluno["id"]
        print(f"Aluno '{args.nome}' ja existe, adicionando foto.")
    else:
        aluno_id = db.criar_aluno(args.nome)
        print(f"Aluno '{args.nome}' criado.")

    aluno_dir = FOTOS_ALUNOS_DIR / str(aluno_id)
    aluno_dir.mkdir(parents=True, exist_ok=True)

    destino = aluno_dir / foto_path.name
    shutil.copy2(foto_path, destino)
    db.adicionar_foto(aluno_id, str(destino))
    print(f"Foto salva em {destino}")


def cmd_presenca(args):
    foto_path = Path(args.foto)
    if not foto_path.exists():
        print(f"Erro: foto '{args.foto}' nao encontrada.")
        return

    alunos = db.listar_alunos()
    if not alunos:
        print("Nenhum aluno cadastrado.")
        return

    data = args.data or date.today().isoformat()

    # Extract faces
    print("Extraindo rostos da foto...")
    faces = face.extract_faces(str(foto_path))
    if not faces:
        print("Nenhum rosto detectado.")
        return
    print(f"{len(faces)} rosto(s) detectado(s).")

    # Create treino
    treino_foto = TREINOS_DIR / data
    treino_foto.mkdir(parents=True, exist_ok=True)
    foto_destino = treino_foto / foto_path.name
    shutil.copy2(foto_path, foto_destino)

    treino_id = db.criar_treino(data, str(foto_destino), len(faces))

    # Save crops to temp for matching
    temp_dir = DATA_DIR / ".temp_faces"
    temp_dir.mkdir(exist_ok=True)

    crop_paths = {}
    for f in faces:
        p = str(temp_dir / f"face_{f['index']}.jpg")
        face.save_crop(f["crop"], p)
        crop_paths[f["index"]] = p

    # Match each student
    matches = {}  # face_index -> (nome, distancia, aluno_id)
    matched_face_indices = set()

    for aluno in alunos:
        fotos = db.get_fotos_aluno(aluno["id"])
        if not fotos:
            continue

        best_dist = float("inf")
        best_face = None

        for foto_aluno in fotos:
            for idx, crop_path in crop_paths.items():
                if idx in matched_face_indices:
                    continue
                matched, dist = face.match_face(foto_aluno, crop_path)
                if matched and dist < best_dist:
                    best_dist = dist
                    best_face = idx

        if best_face is not None:
            matches[best_face] = (aluno["nome"], best_dist, aluno["id"])
            matched_face_indices.add(best_face)
            db.registrar_presenca(treino_id, aluno["id"], best_dist)
            print(f"  {aluno['nome']}: presente (dist={best_dist:.4f})")
        else:
            print(f"  {aluno['nome']}: ausente")

    # Save unidentified faces
    nao_id_dir = treino_foto / "nao_identificados"
    nao_id_dir.mkdir(exist_ok=True)
    nao_id_count = 0

    for f in faces:
        if f["index"] not in matched_face_indices:
            face_path = nao_id_dir / f"rosto_{f['index']}.jpg"
            face.save_crop(f["crop"], str(face_path))
            db.registrar_nao_identificado(treino_id, str(face_path))
            nao_id_count += 1

    # Generate result image
    match_display = {idx: (nome, dist) for idx, (nome, dist, _) in matches.items()}
    result_img = str(treino_foto / "resultado.jpg")
    face.generate_result_image(str(foto_destino), faces, match_display, result_img)

    # Cleanup temp
    shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"\n  Presentes: {len(matches)}")
    print(f"  Nao identificados: {nao_id_count}")
    print(f"  Imagem resultado: {result_img}")
    print(f"  Treino #{treino_id} salvo.")


def cmd_alunos(args):
    alunos = db.listar_alunos()
    if not alunos:
        print("Nenhum aluno cadastrado.")
        return
    for a in alunos:
        fotos = db.get_fotos_aluno(a["id"])
        print(f"  {a['nome']} ({len(fotos)} foto(s))")


def cmd_treinos(args):
    treinos = db.listar_treinos()
    if not treinos:
        print("Nenhum treino registrado.")
        return
    for t in treinos:
        print(f"  #{t['id']} | {t['data']} | {t['presentes']} presentes | {t['nao_identificados']} nao identificados | {t['total_rostos']} rostos")


def cmd_treino(args):
    treino = db.get_treino(args.id)
    if not treino:
        print(f"Treino #{args.id} nao encontrado.")
        return

    print(f"Treino #{treino['id']} - {treino['data']}")
    print(f"Foto: {treino['foto_caminho']}")
    print(f"Total rostos: {treino['total_rostos']}")

    presencas = db.get_presencas_treino(args.id)
    if presencas:
        print(f"\nPresentes ({len(presencas)}):")
        for p in presencas:
            print(f"  {p['nome']} (dist={p['distancia']:.4f})")

    nao_ids = db.get_nao_identificados_treino(args.id)
    if nao_ids:
        print(f"\nNao identificados ({len(nao_ids)}):")
        for n in nao_ids:
            print(f"  {n['face_caminho']}")


def cmd_historico(args):
    if args.nome:
        aluno = db.get_aluno_por_nome(args.nome)
        if not aluno:
            print(f"Aluno '{args.nome}' nao encontrado.")
            return
        hist = db.get_historico_aluno(args.nome)
        if not hist:
            print(f"Nenhum registro para '{args.nome}'.")
            return
        print(f"Historico de {args.nome} ({len(hist)} treino(s)):")
        for h in hist:
            print(f"  {h['data']} (treino #{h['treino_id']}, dist={h['distancia']:.4f})")
    else:
        alunos = db.listar_alunos()
        for a in alunos:
            hist = db.get_historico_aluno(a["nome"])
            print(f"  {a['nome']}: {len(hist)} treino(s)")


def main():
    parser = argparse.ArgumentParser(description="JiuFace - Presenca por reconhecimento facial")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("cadastrar", help="Cadastrar aluno com foto")
    p.add_argument("--nome", required=True)
    p.add_argument("--foto", required=True)

    p = sub.add_parser("presenca", help="Processar presenca de um treino")
    p.add_argument("--foto", required=True, help="Foto da turma")
    p.add_argument("--data", help="Data do treino (YYYY-MM-DD, default=hoje)")

    sub.add_parser("alunos", help="Listar alunos cadastrados")
    sub.add_parser("treinos", help="Listar treinos registrados")

    p = sub.add_parser("treino", help="Detalhes de um treino")
    p.add_argument("id", type=int, help="ID do treino")

    p = sub.add_parser("historico", help="Historico de presenca")
    p.add_argument("--nome", help="Filtrar por aluno")

    args = parser.parse_args()
    db.init_db()

    cmds = {
        "cadastrar": cmd_cadastrar,
        "presenca": cmd_presenca,
        "alunos": cmd_alunos,
        "treinos": cmd_treinos,
        "treino": cmd_treino,
        "historico": cmd_historico,
    }
    cmds[args.comando](args)


if __name__ == "__main__":
    main()
