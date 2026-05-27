"""
Announcements endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    title: str
    message: str
    expiry_date: datetime
    start_date: Optional[datetime] = None


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    expiry_date: Optional[datetime] = None
    start_date: Optional[datetime] = None


def _serialize(doc: dict) -> dict:
    """Convert a MongoDB document to a JSON-serializable dict."""
    doc["id"] = str(doc.pop("_id"))
    # Serialize datetime fields
    for field in ("expiry_date", "start_date", "created_at"):
        if field in doc and doc[field] is not None:
            doc[field] = doc[field].isoformat()
    return doc


def _require_teacher(teacher_username: str) -> dict:
    """Raise 401 if the given username is not a valid teacher/admin."""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Autenticação inválida")
    return teacher


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements that are currently active (not expired and past start date)."""
    now = datetime.now(timezone.utc)
    query = {
        "expiry_date": {"$gte": now},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": now}}
        ]
    }
    results = []
    for doc in announcements_collection.find(query).sort("created_at", -1):
        results.append(_serialize(doc))
    return results


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: str = Query(...)
) -> List[Dict[str, Any]]:
    """Return all announcements (active and expired). Requires authentication."""
    _require_teacher(teacher_username)
    results = []
    for doc in announcements_collection.find().sort("expiry_date", -1):
        results.append(_serialize(doc))
    return results


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_announcement(
    data: AnnouncementCreate,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Create a new announcement. Requires authentication."""
    _require_teacher(teacher_username)

    if data.expiry_date <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=422,
            detail="A data de expiração deve ser no futuro"
        )

    if data.start_date and data.start_date >= data.expiry_date:
        raise HTTPException(
            status_code=422,
            detail="A data de início deve ser anterior à data de expiração"
        )

    doc = {
        "title": data.title.strip(),
        "message": data.message.strip(),
        "expiry_date": data.expiry_date,
        "start_date": data.start_date,
        "created_at": datetime.now(timezone.utc),
        "created_by": teacher_username
    }
    result = announcements_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    data: AnnouncementUpdate,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Update an existing announcement. Requires authentication."""
    _require_teacher(teacher_username)

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")

    existing = announcements_collection.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")

    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}

    # Validate dates if being changed
    expiry = update_fields.get("expiry_date", existing.get("expiry_date"))
    start = update_fields.get("start_date", existing.get("start_date"))
    if start and expiry and start >= expiry:
        raise HTTPException(
            status_code=422,
            detail="A data de início deve ser anterior à data de expiração"
        )

    if update_fields:
        announcements_collection.update_one({"_id": oid}, {"$set": update_fields})

    updated = announcements_collection.find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{announcement_id}", status_code=204)
def delete_announcement(
    announcement_id: str,
    teacher_username: str = Query(...)
) -> None:
    """Delete an announcement. Requires authentication."""
    _require_teacher(teacher_username)

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")

    result = announcements_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
