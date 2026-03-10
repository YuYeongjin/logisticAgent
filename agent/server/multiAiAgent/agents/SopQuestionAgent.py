import json
from typing import Dict

from langchain_ollama import ChatOllama


llm = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url="http://localhost:11434"
)
def generate_sop_questions(state):

    sop = state["sop_generation_result"]

    prompt = f"""
    다음은 새로 생성된 SOP 입니다.

    {json.dumps(sop, ensure_ascii=False, indent=2)}

    작업자에게 확인해야 할 질문을 만들어라.

    반드시 JSON 형식으로 답하라.

    {{
      "questions":[
        {{"question":"", "answer":""}}
      ]
    }}
    """

    res = llm.invoke(prompt)

    try:
        data = json.loads(res.content)
    except:
        data = {"questions": []}

    state["sop_questions"] = data.get("questions", [])

    return state