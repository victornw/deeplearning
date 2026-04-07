"""Gera imagem da turma com box verde no match e vermelha nos demais."""

import cv2
import numpy as np
from pathlib import Path
from deepface import DeepFace

BASE_DIR = Path(__file__).parent
ALUNOS_DIR = BASE_DIR / "alunos"
OUTPUT_DIR = BASE_DIR / "debug_output"

MODEL_NAME = "ArcFace"
DETECTOR = "retinaface"


def preprocess_face(img, min_dim=160):
    h, w = img.shape[:2]
    if h < min_dim or w < min_dim:
        scale = max(min_dim / h, min_dim / w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    foto_turma_path = BASE_DIR / "turmas" / "foto_treino.jpg"
    img_turma = cv2.imread(str(foto_turma_path))
    h_img, w_img = img_turma.shape[:2]

    # Detect faces
    faces = DeepFace.extract_faces(
        img_path=str(foto_turma_path), detector_backend=DETECTOR, enforce_detection=True,
    )
    print(f"{len(faces)} rostos detectados")

    # Prepare crops
    crops = []
    for i, f in enumerate(faces):
        a = f["facial_area"]
        margin = int(max(a["w"], a["h"]) * 0.3)
        x1, y1 = max(0, a["x"] - margin), max(0, a["y"] - margin)
        x2, y2 = min(w_img, a["x"] + a["w"] + margin), min(h_img, a["y"] + a["h"] + margin)
        crop = preprocess_face(img_turma[y1:y2, x1:x2])
        crop_path = OUTPUT_DIR / f"crop_{i}.jpg"
        cv2.imwrite(str(crop_path), crop)
        crops.append((i, crop_path, a))

    # For each aluno, find matches
    alunos = sorted([d for d in ALUNOS_DIR.iterdir() if d.is_dir()])
    matched_faces = {}  # face_index -> aluno_name

    for aluno_dir in alunos:
        nome = aluno_dir.name
        fotos = [f for f in aluno_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]

        best_dist = float("inf")
        best_face = None

        for foto in fotos:
            for i, crop_path, _ in crops:
                try:
                    r = DeepFace.verify(
                        img1_path=str(foto), img2_path=str(crop_path),
                        model_name=MODEL_NAME, detector_backend=DETECTOR,
                        distance_metric="cosine", enforce_detection=False,
                    )
                    if r["verified"] and r["distance"] < best_dist:
                        best_dist = r["distance"]
                        best_face = i
                except Exception:
                    continue

        if best_face is not None:
            matched_faces[best_face] = (nome, best_dist)
            print(f"  {nome}: MATCH rosto #{best_face} (dist={best_dist:.4f})")
        else:
            print(f"  {nome}: ausente")

    # Draw annotated image
    img_out = img_turma.copy()
    for i, _, area in crops:
        x, y, w, h = area["x"], area["y"], area["w"], area["h"]

        if i in matched_faces:
            nome, dist = matched_faces[i]
            color = (0, 255, 0)  # verde
            label = f"{nome} ({dist:.2f})"
            thickness = 3
        else:
            color = (0, 0, 255)  # vermelho
            label = f"#{i}"
            thickness = 1

        cv2.rectangle(img_out, (x, y), (x + w, y + h), color, thickness)

        # Background for text
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6 if i in matched_faces else 0.4
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
        cv2.rectangle(img_out, (x, y - th - 8), (x + tw + 4, y), color, -1)
        cv2.putText(img_out, label, (x + 2, y - 5), font, font_scale, (255, 255, 255), 1)

    out_path = OUTPUT_DIR / "resultado_match.jpg"
    cv2.imwrite(str(out_path), img_out)
    print(f"\nImagem salva em: {out_path}")


if __name__ == "__main__":
    main()
