"""
Knowledge base API — CRUD for qa_pairs and handoff_triggers.

All routes are protected by the x-dashboard-key header.
After any qa_pair write (create/update/delete), the OpenAI vector store file is
regenerated from all active rows and re-uploaded so FileSearchTool stays in sync.
"""
from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import openai
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, field_validator

from integrations.supabase_client import get_supabase_client
from auth_utils import require_dashboard_key as _require_dashboard_key

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Vector store sync
# ─────────────────────────────────────────────────────────────────────────────

def _poll_vector_store_file(
    client: openai.OpenAI,
    vector_store_id: str,
    file_id: str,
    timeout: int = 30,
    interval: float = 1.0,
) -> None:
    """Poll until the vector store file status is 'completed' or raise on failure/timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        vf = client.vector_stores.files.retrieve(file_id, vector_store_id=vector_store_id)
        if vf.status == "completed":
            return
        if vf.status == "failed":
            detail = getattr(vf, "last_error", None)
            raise RuntimeError(f"Vector store file indexing failed: {detail}")
        time.sleep(interval)
    raise TimeoutError(f"Vector store file {file_id} did not complete indexing within {timeout}s")


def _sync_qa_vector_store() -> None:
    """
    Fetch all active qa_pairs from Supabase, build a single plain-text file,
    replace the existing file in the OpenAI vector store with it.
    Runs in the background — logs success or failure, does not raise.
    """
    vector_store_id = os.environ.get("OPENAI_VECTOR_STORE_ID", "")
    if not vector_store_id:
        logger.warning("[knowledge] OPENAI_VECTOR_STORE_ID not set — skipping vector store sync")
        return

    sb = get_supabase_client()
    rows = sb.table("qa_pairs").select("question,answer").eq("active", True).order("created_at").execute().data

    if not rows:
        logger.info("[knowledge] No active qa_pairs — vector store file will be empty")
        content = "No knowledge base entries available."
    else:
        lines = []
        for row in rows:
            lines.append(f"Q: {row['question']}")
            lines.append(f"A: {row['answer']}")
            lines.append("")
        content = "\n".join(lines).strip()

    client = openai.OpenAI()

    # Delete all files currently attached to the vector store
    try:
        existing = client.vector_stores.files.list(vector_store_id)
        for f in existing.data:
            client.vector_stores.files.delete(f.id, vector_store_id=vector_store_id)
            client.files.delete(f.id)
    except Exception as exc:
        logger.warning("[knowledge] Failed to delete old vector store files: %s", exc)

    # Upload new file, attach to vector store, and wait for indexing to complete
    try:
        file_bytes = content.encode("utf-8")
        uploaded = client.files.create(
            file=("knowledge_base.txt", io.BytesIO(file_bytes), "text/plain"),
            purpose="assistants",
        )
        client.vector_stores.files.create(vector_store_id, file_id=uploaded.id)
        _poll_vector_store_file(client, vector_store_id, uploaded.id)
        logger.info("[knowledge] Vector store %s synced — %d Q&A pairs, file %s", vector_store_id, len(rows), uploaded.id)
    except Exception as exc:
        logger.error("[knowledge] Vector store sync failed: %s", exc, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Request / response models
# ─────────────────────────────────────────────────────────────────────────────

class QAPairCreate(BaseModel):
    question: str
    answer: str


class QAPairUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    active: Optional[bool] = None


class HandoffTriggerCreate(BaseModel):
    scenario: str
    default_response: str


class HandoffTriggerUpdate(BaseModel):
    scenario: Optional[str] = None
    default_response: Optional[str] = None
    active: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/knowledge", dependencies=[Depends(_require_dashboard_key)])


# ── qa_pairs ─────────────────────────────────────────────────────────────────

@router.get("/qa", response_model=List[Dict[str, Any]])
def list_qa_pairs() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("qa_pairs").select("id,question,answer,active,created_at,updated_at").order("created_at", desc=True).execute()
    return res.data


@router.post("/qa", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_qa_pair(body: QAPairCreate, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("qa_pairs").insert({
        "question": body.question,
        "answer": body.answer,
    }).execute()
    background_tasks.add_task(_sync_qa_vector_store)
    return res.data[0]


@router.put("/qa/{row_id}", response_model=Dict[str, Any])
def update_qa_pair(row_id: UUID, body: QAPairUpdate, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {}

    if body.question is not None:
        updates["question"] = body.question
    if body.answer is not None:
        updates["answer"] = body.answer
    if body.active is not None:
        updates["active"] = body.active

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = sb.table("qa_pairs").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    background_tasks.add_task(_sync_qa_vector_store)
    return res.data[0]


@router.delete("/qa/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_qa_pair(row_id: UUID, background_tasks: BackgroundTasks) -> None:
    sb = get_supabase_client()
    sb.table("qa_pairs").delete().eq("id", str(row_id)).execute()
    background_tasks.add_task(_sync_qa_vector_store)


# ── handoff_triggers ─────────────────────────────────────────────────────────

@router.get("/handoff", response_model=List[Dict[str, Any]])
def list_handoff_triggers() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("handoff_triggers").select("id,scenario,default_response,active,created_at,updated_at").order("created_at", desc=True).execute()
    return res.data


@router.post("/handoff", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_handoff_trigger(body: HandoffTriggerCreate) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("handoff_triggers").insert({
        "scenario": body.scenario,
        "default_response": body.default_response,
    }).execute()
    return res.data[0]


@router.put("/handoff/{row_id}", response_model=Dict[str, Any])
def update_handoff_trigger(row_id: UUID, body: HandoffTriggerUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {}

    if body.scenario is not None:
        updates["scenario"] = body.scenario
    if body.default_response is not None:
        updates["default_response"] = body.default_response
    if body.active is not None:
        updates["active"] = body.active

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = sb.table("handoff_triggers").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/handoff/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_handoff_trigger(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("handoff_triggers").delete().eq("id", str(row_id)).execute()


# ── broker_assets ─────────────────────────────────────────────────────────────

class BrokerAssetCreate(BaseModel):
    broker: str
    purpose: str
    asset_type: str
    title: str
    url: str
    bot: Optional[str] = None
    sort_order: int = 0

    @field_validator("broker", "purpose", "asset_type", "title", "url")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field is required")
        return v.strip()


class BrokerAssetUpdate(BaseModel):
    broker: Optional[str] = None
    purpose: Optional[str] = None
    asset_type: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    bot: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


@router.get("/broker-assets", response_model=List[Dict[str, Any]])
def list_broker_assets() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("broker_assets").select("*").order("broker").order("purpose").order("sort_order").execute()
    return res.data


@router.post("/broker-assets", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_broker_asset(body: BrokerAssetCreate) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("broker_assets").insert({
        "broker": body.broker,
        "purpose": body.purpose,
        "asset_type": body.asset_type,
        "title": body.title,
        "url": body.url,
        "bot": body.bot or None,
        "sort_order": body.sort_order,
    }).execute()
    return res.data[0]


@router.put("/broker-assets/{row_id}", response_model=Dict[str, Any])
def update_broker_asset(row_id: UUID, body: BrokerAssetUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {
        k: v for k, v in body.model_dump().items() if v is not None
    }
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = sb.table("broker_assets").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/broker-assets/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_broker_asset(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("broker_assets").delete().eq("id", str(row_id)).execute()


# ── country_offers ────────────────────────────────────────────────────────────

class CountryOfferCreate(BaseModel):
    country_group: str
    broker_name: str
    bots: List[str] = []
    broker_notes: List[str] = []
    group_notes: List[str] = []
    sort_order: int = 0

    @field_validator("country_group", "broker_name")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field is required")
        return v.strip()

    @field_validator("bots")
    @classmethod
    def must_have_at_least_one_bot(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one bot must be selected")
        return v


class CountryOfferUpdate(BaseModel):
    country_group: Optional[str] = None
    broker_name: Optional[str] = None
    bots: Optional[List[str]] = None
    broker_notes: Optional[List[str]] = None
    group_notes: Optional[List[str]] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None


@router.get("/country-offers", response_model=List[Dict[str, Any]])
def list_country_offers() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("country_offers").select("*").order("country_group").order("sort_order").execute()
    return res.data


@router.post("/country-offers", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_country_offer(body: CountryOfferCreate) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("country_offers").insert({
        "country_group": body.country_group,
        "broker_name": body.broker_name,
        "bots": body.bots,
        "broker_notes": body.broker_notes,
        "group_notes": body.group_notes,
        "sort_order": body.sort_order,
    }).execute()
    return res.data[0]


@router.put("/country-offers/{row_id}", response_model=Dict[str, Any])
def update_country_offer(row_id: UUID, body: CountryOfferUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {
        k: v for k, v in body.model_dump().items() if v is not None
    }
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = sb.table("country_offers").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/country-offers/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_country_offer(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("country_offers").delete().eq("id", str(row_id)).execute()


# ── brokers ───────────────────────────────────────────────────────────────────

class BrokerCreate(BaseModel):
    broker_id: str
    display_name: str
    aliases: List[str] = []


class BrokerUpdate(BaseModel):
    display_name: Optional[str] = None
    aliases: Optional[List[str]] = None
    active: Optional[bool] = None


@router.get("/brokers", response_model=List[Dict[str, Any]])
def list_brokers() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    return sb.table("brokers").select("*").order("display_name").execute().data


@router.post("/brokers", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_broker(body: BrokerCreate) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("brokers").insert({
        "broker_id": body.broker_id.strip().lower(),
        "display_name": body.display_name,
        "aliases": body.aliases,
    }).execute()
    return res.data[0]


@router.put("/brokers/{row_id}", response_model=Dict[str, Any])
def update_broker(row_id: UUID, body: BrokerUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = sb.table("brokers").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/brokers/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_broker(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("brokers").delete().eq("id", str(row_id)).execute()


# ── country_groups ────────────────────────────────────────────────────────────

class CountryGroupCreate(BaseModel):
    name: str
    aliases: List[str] = []


class CountryGroupUpdate(BaseModel):
    name: Optional[str] = None
    aliases: Optional[List[str]] = None
    active: Optional[bool] = None


@router.get("/country-groups", response_model=List[Dict[str, Any]])
def list_country_groups() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    return sb.table("country_groups").select("*").order("name").execute().data


@router.post("/country-groups", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_country_group(body: CountryGroupCreate) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("country_groups").insert({
        "name": body.name.strip().upper(),
        "aliases": [a.strip().lower() for a in body.aliases],
    }).execute()
    return res.data[0]


@router.put("/country-groups/{row_id}", response_model=Dict[str, Any])
def update_country_group(row_id: UUID, body: CountryGroupUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    if "name" in updates:
        updates["name"] = updates["name"].strip().upper()
    if "aliases" in updates:
        updates["aliases"] = [a.strip().lower() for a in updates["aliases"]]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = sb.table("country_groups").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/country-groups/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_country_group(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("country_groups").delete().eq("id", str(row_id)).execute()


# ── bots ──────────────────────────────────────────────────────────────────────

class BotCreate(BaseModel):
    name: str


class BotUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None


@router.get("/bots", response_model=List[Dict[str, Any]])
def list_bots() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    return sb.table("bots").select("*").order("name").execute().data


@router.post("/bots", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_bot(body: BotCreate) -> Dict[str, Any]:
    sb = get_supabase_client()
    res = sb.table("bots").insert({"name": body.name.strip()}).execute()
    return res.data[0]


@router.put("/bots/{row_id}", response_model=Dict[str, Any])
def update_bot(row_id: UUID, body: BotUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = sb.table("bots").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/bots/{row_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_bot(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("bots").delete().eq("id", str(row_id)).execute()


# ── results_videos ────────────────────────────────────────────────────────────

RESULTS_BUCKET = "results-videos"


@router.get("/results-videos", response_model=List[Dict[str, Any]])
def list_results_videos() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    return sb.table("results_videos").select("*").order("market").execute().data


@router.post("/results-videos/upload", response_model=Dict[str, Any])
async def upload_results_video(
    market: str = Form(...),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    market = market.lower().strip()
    if not market:
        raise HTTPException(status_code=400, detail="market is required")

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "mp4"
    storage_path = f"{market}/{market}.{ext}"
    contents = await file.read()

    sb = get_supabase_client()
    sb.storage.from_(RESULTS_BUCKET).upload(
        storage_path,
        contents,
        file_options={"content-type": file.content_type or "video/mp4", "upsert": "true"},
    )

    public_url = sb.storage.from_(RESULTS_BUCKET).get_public_url(storage_path)

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    sb.table("results_videos").upsert({
        "market": market,
        "url": public_url,
        "updated_at": now_iso,
    }).execute()

    logger.info("[results_videos] Uploaded %s → %s", storage_path, public_url)
    return {"market": market, "url": public_url}


@router.delete("/results-videos/{market}", status_code=204)
def delete_results_video(market: str) -> None:
    market = market.lower().strip()
    sb = get_supabase_client()

    # Find the row so we know the file extension / storage path
    rows = sb.table("results_videos").select("url").eq("market", market).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail=f"No video found for market '{market}'")

    # Derive the storage path from the public URL (last two path segments: <market>/<filename>)
    url: str = rows[0]["url"]
    # URL pattern: .../results-videos/<market>/<market>.<ext>
    parts = url.rstrip("/").split("/")
    storage_path = "/".join(parts[-2:])  # e.g. "crypto/crypto.mp4"

    try:
        sb.storage.from_(RESULTS_BUCKET).remove([storage_path])
    except Exception as exc:
        logger.warning("[results_videos] Storage delete failed for %s: %s", storage_path, exc)
        # Continue to remove the DB row even if the storage object is already gone

    sb.table("results_videos").delete().eq("market", market).execute()
    logger.info("[results_videos] Deleted market=%s path=%s", market, storage_path)
