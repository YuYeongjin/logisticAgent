from typing import TypedDict, Dict, Optional

# GlobalState와 호환되는 내부 State
class SafetyState(TypedDict):
    observation: Dict
    risk_level: str
    anomaly: bool
    result: Dict

def safety_check_logic(state: SafetyState):
    obs = state["observation"]
    print(f"SAFETY LOGIC CHECK : {obs}")
    if obs.get("voice") == None and obs.get("vision") == None:
        state["risk_level"] = "LOW"
        state["anomaly"] = False
        return state
    vision = obs.get("vision", {})
    objs = vision.get("objects", [])

    risk = "LOW"
    anomaly = False
    
    # 기존 코드의 로직 스타일 유지
    if vision and vision.get("worker") and vision.get("machine"):
        risk = "MEDIUM"
        if "knife" in objs or "saw" in objs: # 위험 도구 구체화
            risk = "HIGH"
            anomaly = True

    state["risk_level"] = risk
    state["anomaly"] = anomaly
    return state

def run_safety_agent(observation: Dict):
    # 기존 ProcessAgent의 Main Runner 방식 그대로 유지
    state: SafetyState = {
        "observation": observation,
        "risk_level": "LOW",
        "anomaly": False,
        "result": {}
    }
    
    state = safety_check_logic(state)
    
    state["result"] = {
        "risk_level": state["risk_level"],
        "anomaly": state["anomaly"]
    }
    return state["result"]