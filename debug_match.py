"""Test matching with multiple models and thresholds."""

import cv2
import numpy as np
from pathlib import Path
from deepface import DeepFace

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "debug_output"
DETECTOR = "retinaface"

MODELS = ["Facenet512", "ArcFace", "SFace"]


def upscale_if_small(img, min_dim=160):
    h, w = img.shape[:2]
    if h < min_dim or w < min_dim:
        scale = max(min_dim / h, min_dim / w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    return img


def normalize_lighting(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def preprocess(img):
    return normalize_lighting(upscale_if_small(img))


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    refs = {
        "bianca.jpeg": BASE_DIR / "alunos" / "bianca.jpeg",
    }

    turma_path = BASE_DIR / "turmas" / "foto_treino.jpg"
    print(turma_path)
    img_turma = cv2.imread(str(turma_path))
    h_img, w_img = img_turma.shape[:2]

    # Extract faces from group
    faces = DeepFace.extract_faces(
        img_path=str(turma_path), detector_backend=DETECTOR, enforce_detection=True,
    )
    print(f"{len(faces)} rostos na turma\n")

    # Save preprocessed crops
    crop_paths = []
    for i, f in enumerate(faces):
        a = f["facial_area"]
        margin = int(max(a["w"], a["h"]) * 0.3)
        x1, y1 = max(0, a["x"] - margin), max(0, a["y"] - margin)
        x2, y2 = min(w_img, a["x"] + a["w"] + margin), min(h_img, a["y"] + a["h"] + margin)
        crop = preprocess(img_turma[y1:y2, x1:x2])
        p = OUTPUT_DIR / f"crop_{i}.jpg"
        cv2.imwrite(str(p), crop)
        crop_paths.append(p)

    # Preprocess refs
    prep_refs = {}
    for name, path in refs.items():
        img = preprocess(cv2.imread(str(path)))
        p = OUTPUT_DIR / f"prep_{name}"
        cv2.imwrite(str(p), img)
        prep_refs[name] = p

    # Test each model
    for model in MODELS:
        print(f"{'='*50}")
        print(f"MODELO: {model}")
        print(f"{'='*50}")

        for ref_name, ref_path in prep_refs.items():
            print(f"\n  {ref_name}:")
            results = []
            for i, cp in enumerate(crop_paths):
                try:
                    r = DeepFace.verify(
                        img1_path=str(ref_path), img2_path=str(cp),
                        model_name=model, detector_backend=DETECTOR,
                        distance_metric="cosine", enforce_detection=False,
                    )
                    results.append((i, r["distance"], r["threshold"], r["verified"]))
                except Exception:
                    pass

            results.sort(key=lambda x: x[1])
            for rank, (i, dist, thr, ver) in enumerate(results[:5]):
                tag = " <<< MATCH" if ver else ""
                gap = dist - thr
                print(f"    {rank+1}. #{i:2d} dist={dist:.4f} (thr={thr:.4f}, gap={gap:+.4f}){tag}")

    # Also try with euclidean_l2 on Facenet512
    print(f"\n{'='*50}")
    print(f"MODELO: Facenet512 + euclidean_l2")
    print(f"{'='*50}")
    for ref_name, ref_path in prep_refs.items():
        print(f"\n  {ref_name}:")
        results = []
        for i, cp in enumerate(crop_paths):
            try:
                r = DeepFace.verify(
                    img1_path=str(ref_path), img2_path=str(cp),
                    model_name="Facenet512", detector_backend=DETECTOR,
                    distance_metric="euclidean_l2", enforce_detection=False,
                )
                results.append((i, r["distance"], r["threshold"], r["verified"]))
            except Exception:
                pass

        results.sort(key=lambda x: x[1])
        for rank, (i, dist, thr, ver) in enumerate(results[:5]):
            tag = " <<< MATCH" if ver else ""
            gap = dist - thr
            print(f"    {rank+1}. #{i:2d} dist={dist:.4f} (thr={thr:.4f}, gap={gap:+.4f}){tag}")


if __name__ == "__main__":
    main()
