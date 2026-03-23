import os
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_ollama import ChatOllama

# ==============================
# LLM 인스턴스 (전체 에이전트 공유)
# ==============================

llm_json = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

llm_chat = ChatOllama(
    model="llama3.1",
    temperature=0.7,
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

# ==============================
# DB 설정
# ==============================

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "database": os.getenv("DB_NAME",     "factory_db"),
    "user":     os.getenv("DB_USER",     "admin"),
    "password": os.getenv("DB_PASSWORD", "Abcd1234"),
    "port":     os.getenv("DB_PORT",     "5432"),
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
