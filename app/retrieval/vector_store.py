import os
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings
from app.verification.models import EvidenceSource, CredibilityTier

logger = logging.getLogger(__name__)

class VectorEvidenceStore:
    def __init__(self, collection_name: str = "reel_evidence"):
        self.chroma_dir = str(settings.CHROMA_DIR)
        os.makedirs(self.chroma_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.chroma_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_evidence(self, video_id: str, claim_id: str, sources: List[EvidenceSource]):
        """Index evidence sources for a given reel and claim."""
        if not sources:
            return

        documents = []
        metadatas = []
        ids = []

        for idx, src in enumerate(sources):
            doc_id = f"{video_id}_{claim_id}_src_{idx}"
            text = f"Title: {src.title}\nDomain: {src.domain}\nContent: {src.relevant_quote or src.snippet}"
            
            documents.append(text)
            metadatas.append({
                "video_id": video_id,
                "claim_id": claim_id,
                "url": src.url,
                "title": src.title,
                "domain": src.domain,
                "credibility_tier": src.credibility_tier.value,
                "credibility_score": float(src.credibility_score),
                "is_fact_check": bool(src.is_fact_check_article)
            })
            ids.append(doc_id)

        try:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            logger.error(f"Error upserting into ChromaDB: {e}")

    def query_evidence(self, video_id: str, query: str, top_k: int = 4) -> List[Dict[str, Any]]:
        """Query evidence relevant to a user's question or specific claim for a given reel."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"video_id": video_id}
            )
            
            output = []
            if results and results.get("documents") and results["documents"][0]:
                for doc, meta, doc_id in zip(results["documents"][0], results["metadatas"][0], results["ids"][0]):
                    output.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": meta
                    })
            return output
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            return []
