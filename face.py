import cv2
import numpy as np
from pathlib import Path
from deepface import DeepFace

MODEL_NAME = "ArcFace"
DETECTOR_BACKEND = "retinaface"
DISTANCE_METRIC = "cosine"


def preprocess_face(img: np.ndarray, min_dim: int = 160) -> np.ndarray:
    """Upscale small faces and normalize lighting for better embeddings."""
    h, w = img.shape[:2]
    if h < min_dim or w < min_dim:
        scale = max(min_dim / h, min_dim / w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def extract_faces(foto_turma: str) -> list[dict]:
    """Extract all faces from a group photo. Returns list of {index, area, crop_path}."""
    img = cv2.imread(foto_turma)
    h_img, w_img = img.shape[:2]

    try:
        faces = DeepFace.extract_faces(
            img_path=foto_turma, detector_backend=DETECTOR_BACKEND, enforce_detection=True,
        )
    except ValueError:
        return []

    results = []
    for i, face_obj in enumerate(faces):
        area = face_obj["facial_area"]
        x, y, w, h = area["x"], area["y"], area["w"], area["h"]

        margin = int(max(w, h) * 0.3)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(w_img, x + w + margin)
        y2 = min(h_img, y + h + margin)

        crop = preprocess_face(img[y1:y2, x1:x2])
        results.append({"index": i, "area": area, "crop": crop})

    return results


def save_crop(crop: np.ndarray, path: str):
    cv2.imwrite(path, crop)


def match_face(foto_aluno: str, crop_path: str) -> tuple[bool, float]:
    """Compare a student photo against a face crop. Returns (matched, distance)."""
    try:
        result = DeepFace.verify(
            img1_path=foto_aluno,
            img2_path=crop_path,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR_BACKEND,
            distance_metric=DISTANCE_METRIC,
            enforce_detection=False,
        )
        return result["verified"], result["distance"]
    except Exception:
        return False, float("inf")


def generate_result_image(foto_turma: str, faces: list[dict], matches: dict, output_path: str):
    """Draw boxes on group photo: green for matches, red for unidentified."""
    img = cv2.imread(foto_turma)

    for face in faces:
        i = face["index"]
        a = face["area"]
        x, y, w, h = a["x"], a["y"], a["w"], a["h"]

        if i in matches:
            nome, dist = matches[i]
            color = (0, 255, 0)
            label = f"{nome} ({dist:.2f})"
            thickness = 3
            font_scale = 0.6
        else:
            color = (0, 0, 255)
            label = "?"
            thickness = 1
            font_scale = 0.4

        cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
        cv2.rectangle(img, (x, y - th - 8), (x + tw + 4, y), color, -1)
        cv2.putText(img, label, (x + 2, y - 5), font, font_scale, (255, 255, 255), 1)

    cv2.imwrite(output_path, img)
