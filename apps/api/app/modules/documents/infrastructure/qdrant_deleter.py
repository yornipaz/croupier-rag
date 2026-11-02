from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from app.shared.errors import UpstreamError


class QdrantVectorDeleter:
    """Delete all chunks for a document without needing embedding adapters."""

    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self._client = client
        self._collection_name = collection_name

    async def delete_by_doc(self, document_id: str) -> None:
        try:
            if not await self._client.collection_exists(self._collection_name):
                return
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[
                            qm.FieldCondition(
                                key="doc_id",
                                match=qm.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:
            raise UpstreamError(
                "Could not delete document vectors",
                details={"errorType": type(exc).__name__},
            ) from exc
