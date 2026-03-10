import chromadb
from sentence_transformers import SentenceTransformer

class VectorStore:

    def __init__(self):

        self.client = chromadb.Client()
        self.collection = self.client.get_or_create_collection(
            name="sensor_events"
        )

        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

    def search(self, query):

        embedding = self.embedder.encode(query).tolist()

        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=3
        )

        return result["documents"]