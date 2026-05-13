from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from main import verify_token  # noqa: E402
from storage import init_db, list_hives, create_hive, delete_hive  # noqa: E402


router = APIRouter()
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class HiveCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    loc: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=128)
    node: str = Field(min_length=1, max_length=64)


@router.get("/hives")
def get_hives(username: str = Depends(verify_token)):
    init_db()
    return list_hives()


@router.post("/hives")
def add_hive(body: HiveCreate, username: str = Depends(verify_token)):
    if not _NODE_RE.match(body.node):
        raise HTTPException(status_code=400, detail="Invalid node id format")
    init_db()
    return create_hive(body.name.strip(), body.loc.strip(), body.topic.strip(), body.node.strip())


@router.delete("/hives/{hive_id}")
def remove_hive(hive_id: str, username: str = Depends(verify_token)):
    init_db()
    ok = delete_hive(hive_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Hive not found")
    return {"deleted": True}
