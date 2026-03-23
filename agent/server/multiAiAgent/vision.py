import json
import numpy as np
import cv2
from ultralytics import YOLO
from faster_whisper import WhisperModel
from agents.config import llm_json

# ==============================
# 모델 초기화
# ==============================

detector   = YOLO("yolov8m.pt")
segmentor  = YOLO("yolov8m-seg.pt")
pose_model = YOLO("yolov8m-pose.pt")
ppe_model  = YOLO("yolov8m.pt")  # 전용 PPE 모델로 교체 가능

stt_model = WhisperModel("base", device="cpu", compute_type="int8")


# ==============================
# 이미지 전처리
# ==============================

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"이미지 로드 실패: {path}")
    return cv2.resize(img, (1280, 720))


# ==============================
# 객체 탐지
# ==============================

def detect_objects(img: np.ndarray) -> list:
    objects = []
    for r in detector(img):
        for box in r.boxes:
            conf = float(box.conf)
            if conf < 0.4:
                continue
            cls = int(box.cls)
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            objects.append({
                "label":      detector.names[cls],
                "confidence": round(conf, 3),
                "bbox":       [int(x1), int(y1), int(x2), int(y2)],
                "center":     [int((x1 + x2) / 2), int((y1 + y2) / 2)],
            })
    return objects


# ==============================
# PPE 탐지
# ==============================

def detect_ppe(img: np.ndarray) -> list:
    ppe_items = []
    for r in ppe_model(img):
        for box in r.boxes:
            conf = float(box.conf)
            if conf < 0.4:
                continue
            cls = int(box.cls)
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            ppe_items.append({
                "label":      ppe_model.names[cls],
                "confidence": round(conf, 3),
                "bbox":       [int(x1), int(y1), int(x2), int(y2)],
            })
    return ppe_items


def check_ppe_compliance(objects: list, poses: list, ppe_items: list) -> dict:
    result = {"helmet": False, "gloves": False, "vest": False}
    if not poses:
        return result

    keypoints = poses[0]["keypoints"]
    head       = keypoints[0]
    left_hand  = keypoints[9]
    right_hand = keypoints[10]

    for p in ppe_items:
        x1, y1, x2, y2 = p["bbox"]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

        if p["label"] == "helmet":
            if abs(cx - head[0]) < 100 and abs(cy - head[1]) < 100:
                result["helmet"] = True
        elif p["label"] == "gloves":
            if abs(cx - left_hand[0]) < 120 or abs(cx - right_hand[0]) < 120:
                result["gloves"] = True
        elif p["label"] == "safety_vest":
            result["vest"] = True

    return result


# ==============================
# 세그멘테이션
# ==============================

def segment_objects(img: np.ndarray) -> list:
    segments = []
    for r in segmentor(img):
        if r.masks is None:
            continue
        for i, mask in enumerate(r.masks.xy):
            cls = int(r.boxes.cls[i])
            segments.append({
                "label":   segmentor.names[cls],
                "polygon": mask.tolist(),
            })
    return segments


# ==============================
# 포즈 탐지
# ==============================

def detect_pose(img: np.ndarray) -> list:
    poses = []
    for r in pose_model(img):
        if r.keypoints is None:
            continue
        for k in r.keypoints.xy:
            poses.append({"keypoints": k.tolist()})
    return poses


# ==============================
# 객체 관계 분석
# ==============================

def analyze_relations(objects: list) -> list:
    relations = []
    for i in range(len(objects)):
        for j in range(i + 1, len(objects)):
            o1, o2 = objects[i], objects[j]
            x1, y1 = o1["center"]
            x2, y2 = o2["center"]
            dist = float(np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2))
            if dist < 150:
                relations.append({
                    "object1":  o1["label"],
                    "object2":  o2["label"],
                    "distance": int(dist),
                    "relation": "near",
                })
    return relations


# ==============================
# Scene Graph 생성
# ==============================

def build_scene_graph(objects: list, relations: list) -> dict:
    return {"nodes": objects, "edges": relations}


# ==============================
# LLM 장면 이해
# ==============================

def scene_reasoning(objects: list, segments: list, poses: list, relations: list) -> dict:
    prompt = f"""
다음은 제조 현장 이미지 분석 데이터이다.

objects:
{json.dumps(objects, ensure_ascii=False)}

segmentation:
{json.dumps(segments, ensure_ascii=False)}

human_pose:
{json.dumps(poses, ensure_ascii=False)}

relations:
{json.dumps(relations, ensure_ascii=False)}

이 데이터를 기반으로 장면을 분석하고 작업자의 활동과 위험 요소를 파악하라.

반드시 JSON으로만 응답:
{{
    "scene": "장면 설명",
    "human_activity": "작업자 활동",
    "tools": ["도구1", "도구2"],
    "environment": "환경 설명",
    "risk": "위험 요소"
}}
"""
    try:
        res = llm_json.invoke(prompt)
        return json.loads(res.content)
    except Exception:
        return {"scene": "unknown", "human_activity": "", "tools": [], "environment": "", "risk": ""}
