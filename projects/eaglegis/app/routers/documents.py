from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.data.csv_store import CSVStore
from app.dependencies import get_store
from app.models.schemas import Document, DocumentType

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/", response_model=list[Document], summary="List meeting documents")
def list_documents(
    meeting_id: Optional[int] = Query(None, description="Filter by meeting"),
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type"),
    store: CSVStore = Depends(get_store),
):
    return store.get_documents(meeting_id=meeting_id, document_type=document_type)


@router.get("/{document_id}", response_model=Document)
def get_document(document_id: int, store: CSVStore = Depends(get_store)):
    doc = store.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return doc
