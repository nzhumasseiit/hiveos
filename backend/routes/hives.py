from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import re
from typing import Optional

from security import verify_token
from storage import create_hive, delete_hive, init_db, list_devices, list_hives


router = APIRouter()
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class HiveCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    loc: Optional[str] = Field(default=None, min_length=1, max_length=128)
    location: Optional[str] = Field(default=None, min_length=1, max_length=128)
    client_id: str = Field(default="default", min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=128)
    node: str = Field(min_length=1, max_length=64)


@router.get("/hives")
def get_hives(username: str = Depends(verify_token)):
    init_db()
    return list_hives(owner_username=username)


@router.post("/hives")
def add_hive(body: HiveCreate, username: str = Depends(verify_token)):
    if not _NODE_RE.match(body.node):
        raise HTTPException(status_code=400, detail="Invalid node id format")
    location = (body.location or body.loc or "").strip()
    if not location:
        raise HTTPException(status_code=400, detail="Location is required")
    init_db()
    return create_hive(
        name=body.name.strip(),
        location=location,
        topic=body.topic.strip(),
        node=body.node.strip(),
        owner_username=username,
        client_id=body.client_id.strip(),
    )


@router.delete("/hives/{hive_id}")
def remove_hive(hive_id: str, username: str = Depends(verify_token)):
    init_db()
    owned_hive_ids = {h["id"] for h in list_hives(owner_username=username)}
    if hive_id not in owned_hive_ids:
        raise HTTPException(status_code=404, detail="Hive not found")
    ok = delete_hive(hive_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Hive not found")
    return {"deleted": True}


@router.get("/hives/{hive_id}/devices")
def get_hive_devices(hive_id: str, username: str = Depends(verify_token)):
    init_db()
    owned_hive_ids = {h["id"] for h in list_hives(owner_username=username)}
    if hive_id not in owned_hive_ids:
        raise HTTPException(status_code=404, detail="Hive not found")
    return list_devices(hive_id=hive_id)
