import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EXTRACTION_MODEL = "claude-haiku-4-5-20251001"
QUERY_MODEL = "claude-sonnet-4-6"

# Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]

# Embedding
EMBEDDING_MODEL = "nlpai-lab/KURE-v1"
EMBEDDING_DIM = 1024

# Chunking
MAX_CHUNK_CHARS = 500   # 문단이 이 길이를 초과하면 추가 분할
CHUNK_OVERLAP_CHARS = 50

# Entity / Relation ontology
ENTITY_TYPES = ["Company", "Person", "Product", "Technology", "Event", "Document"]
RELATION_TYPES = ["WORKS_AT", "LAUNCHED", "PARTNERED_WITH", "INVESTED_IN", "RELATED_TO"]
