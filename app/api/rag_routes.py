"""RAG API Routes for Knowledge Base."""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import StreamingResponse
import io

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.models import Document, DocumentChunk, RAGQuery, User
from app.services.document_parser import DocumentParser, get_demo_document_content, DEMO_DOCUMENTS
from app.services.rag_service import rag_service

router = APIRouter()

# Upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def require_sms_verified(request: Request) -> int:
    """Require user to be authenticated and SMS verified. Returns user_id."""
    user_id = require_sms_verified(request)
    if not request.session.get("sms_verified"):
        raise HTTPException(status_code=403, detail="Phone verification required")
    return user_id


# ==================== Document Endpoints ====================


@router.get("/documents")
async def list_documents(
    request: Request,
    db = Depends(get_db)
):
    """List all documents for current user."""
    user_id = require_sms_verified(request)
    
    documents = db.query(Document).filter(
        Document.user_id == user_id
    ).order_by(Document.created_at.desc()).all()
    
    return [
        {
            "id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "document_type": doc.document_type,
            "event_name": doc.event_name,
            "venue_name": doc.venue_name,
            "year": doc.year,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "file_size": doc.file_size,
            "created_at": doc.created_at.isoformat() if doc.created_at else None
        }
        for doc in documents
    ]


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(None),
    event_name: str = Form(None),
    venue_name: str = Form(None),
    year: int = Form(None),
    db = Depends(get_db)
):
    """Upload and index a document."""
    user_id = require_sms_verified(request)
    
    # Validate file type
    allowed_types = ['application/pdf', 'text/plain', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type not supported: {file.content_type}")
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    # Generate unique filename
    ext = file.filename.split('.')[-1].lower()
    stored_filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)
    
    # Save file
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Determine document type from filename if not provided
    if not document_type:
        document_type = DocumentParser.get_document_type(file.filename)
    
    # Create document record
    document = Document(
        user_id=user_id,
        title=title,
        filename=file.filename,
        document_type=document_type,
        event_name=event_name,
        venue_name=venue_name,
        year=year,
        file_size=file_size,
        file_path=stored_filename,
        status="processing"
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    
    # Process document in background (simplified - process now)
    try:
        # Parse document
        text = DocumentParser.parse_file(content, file.filename)
        
        # Chunk text
        chunks = DocumentParser.chunk_text(text)
        
        # Store chunks
        for idx, chunk_text in enumerate(chunks):
            chunk = DocumentChunk(
                user_id=user_id,
                document_id=document.id,
                chunk_index=idx,
                content=chunk_text,
                metadata_json=json.dumps({"char_count": len(chunk_text)})
            )
            db.add(chunk)
        
        # Update document status
        document.status = "indexed"
        document.chunk_count = len(chunks)
        db.commit()
        
    except Exception as e:
        document.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
    
    return {
        "success": True,
        "document_id": document.id,
        "filename": file.filename,
        "status": document.status,
        "chunk_count": document.chunk_count
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    request: Request,
    db = Depends(get_db)
):
    """Delete a document and its chunks."""
    user_id = require_sms_verified(request)
    
    document = db.query(Document).filter(
        Document.id == doc_id,
        Document.user_id == user_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file if exists
    if document.file_path:
        file_path = os.path.join(UPLOAD_DIR, document.file_path)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    # Delete chunks
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
    
    # Delete document
    db.delete(document)
    db.commit()
    
    return {"success": True, "message": "Document deleted"}


# ==================== RAG Query Endpoints ====================


@router.post("/ask")
async def ask_question(
    question: str = Form(...),
    request: Request = None,
    db = Depends(get_db)
):
    """Ask a question using RAG."""
    user_id = require_sms_verified(request)
    
    # Get user's document chunks
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.user_id == user_id
    ).all()
    
    # Convert to dict format
    chunk_dicts = [
        {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "document_title": None  # Will be populated below
        }
        for chunk in chunks
    ]
    
    # Get document titles
    doc_ids = set(c["document_id"] for c in chunk_dicts)
    doc_titles = {
        doc.id: doc.title
        for doc in db.query(Document).filter(Document.id.in_(doc_ids)).all()
    }
    
    for chunk in chunk_dicts:
        chunk["document_title"] = doc_titles.get(chunk["document_id"], "Unknown")
    
    # If no user documents, use demo content
    if not chunk_dicts:
        # Check if demo@example.com
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.email == "demo@example.com":
            # Add demo documents
            demo_chunks = [
                {
                    "id": 1,
                    "document_id": 0,
                    "chunk_index": 0,
                    "content": get_demo_document_content("ces_rules"),
                    "document_title": "CES Exhibitor Manual - Booth Rules"
                },
                {
                    "id": 2,
                    "document_id": 0,
                    "chunk_index": 1,
                    "content": get_demo_document_content("fire_safety"),
                    "document_title": "Fire Safety Regulations"
                },
                {
                    "id": 3,
                    "document_id": 0,
                    "chunk_index": 2,
                    "content": get_demo_document_content("electrical"),
                    "document_title": "Electrical Requirements"
                },
                {
                    "id": 4,
                    "document_id": 0,
                    "chunk_index": 3,
                    "content": get_demo_document_content("hanging_signs"),
                    "document_title": "Hanging Signs Guidelines"
                }
            ]
            chunk_dicts = demo_chunks
    
    # Process query
    result = await rag_service.query(question, chunk_dicts)
    
    # Save query to history
    rag_query = RAGQuery(
        user_id=user_id,
        question=question,
        answer=result["answer"],
        sources_json=json.dumps(result["sources"]),
        provider=result["provider"]
    )
    db.add(rag_query)
    db.commit()
    
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "provider": result["provider"],
        "provider_name": result["provider_name"],
        "query_id": rag_query.id
    }


@router.get("/queries")
async def list_queries(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db = Depends(get_db)
):
    """List RAG query history."""
    user_id = require_sms_verified(request)
    
    queries = db.query(RAGQuery).filter(
        RAGQuery.user_id == user_id
    ).order_by(RAGQuery.created_at.desc()).offset(skip).limit(limit).all()
    
    return [
        {
            "id": q.id,
            "question": q.question,
            "answer": q.answer,
            "sources": json.loads(q.sources_json) if q.sources_json else [],
            "provider": q.provider,
            "created_at": q.created_at.isoformat() if q.created_at else None
        }
        for q in queries
    ]


@router.get("/status")
async def get_rag_status(request: Request, db = Depends(get_db)):
    """Get RAG system status."""
    user_id = request.session.get("user_id")
    
    # Get provider status
    provider_status = rag_service.get_provider_status()
    active_provider, _ = rag_service.get_active_provider()
    
    # Count user documents
    doc_count = 0
    chunk_count = 0
    if user_id:
        doc_count = db.query(Document).filter(Document.user_id == user_id).count()
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.user_id == user_id).count()
    
    return {
        "mode": "mock" if active_provider == "mock" else "live",
        "active_provider": active_provider,
        "providers": provider_status,
        "document_count": doc_count,
        "chunk_count": chunk_count,
        "demo_available": True  # Demo content always available
    }


@router.post("/load-demo")
async def load_demo_content(
    request: Request,
    db = Depends(get_db)
):
    """Load demo content for demo@example.com users."""
    user_id = require_sms_verified(request)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.email != "demo@example.com":
        raise HTTPException(status_code=403, detail="Demo content only available for demo@example.com")
    
    # Check if demo documents already exist
    existing = db.query(Document).filter(
        Document.user_id == user_id,
        Document.title.like("Demo: %")
    ).first()
    
    if existing:
        return {"success": True, "message": "Demo content already loaded", "document_count": 0}
    
    # Create demo documents
    demo_files = [
        {
            "title": "Demo: CES Exhibitor Manual - Booth Rules",
            "filename": "ces_booth_rules.txt",
            "document_type": "exhibitor_manual",
            "event_name": "CES",
            "content": get_demo_document_content("ces_rules")
        },
        {
            "title": "Demo: Fire Safety Regulations",
            "filename": "fire_safety.txt",
            "document_type": "fire_safety",
            "event_name": "General",
            "content": get_demo_document_content("fire_safety")
        },
        {
            "title": "Demo: Electrical Requirements",
            "filename": "electrical_requirements.txt",
            "document_type": "electrical",
            "event_name": "General",
            "content": get_demo_document_content("electrical")
        },
        {
            "title": "Demo: Hanging Signs Guidelines",
            "filename": "hanging_signs.txt",
            "document_type": "hanging_signs",
            "event_name": "General",
            "content": get_demo_document_content("hanging_signs")
        }
    ]
    
    created_docs = 0
    for demo in demo_files:
        # Create document record
        document = Document(
            user_id=user_id,
            title=demo["title"],
            filename=demo["filename"],
            document_type=demo["document_type"],
            event_name=demo["event_name"],
            status="indexed"
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Chunk and store content
        chunks = DocumentParser.chunk_text(demo["content"])
        for idx, chunk_text in enumerate(chunks):
            chunk = DocumentChunk(
                user_id=user_id,
                document_id=document.id,
                chunk_index=idx,
                content=chunk_text
            )
            db.add(chunk)
        
        document.chunk_count = len(chunks)
        db.commit()
        created_docs += 1
    
    return {
        "success": True,
        "message": f"Loaded {created_docs} demo documents",
        "document_count": created_docs
    }
