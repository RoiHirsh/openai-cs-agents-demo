"""
Knowledge base API — CRUD for qa_pairs and handoff_triggers.

All routes are protected by the x-dashboard-key header.
Embeddings are generated using OpenAI text-embedding-3-small and stored in Supabase.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from supabase_client import get_supabase_client

# ─────────────────────────────────────────────────────────────────────────────
# Auth dependency
# ─────────────────────────────────────────────────────────────────────────────

def _require_dashboard_key(x_dashboard_key: Optional[str] = Header(default=None)) -> None:
    expected = os.environ.get("DASHBOARD_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="DASHBOARD_API_KEY not configured on server")
    if x_dashboard_key != expected:
        raise HTTPException(status_code=401, detail="Invalid dashboard key")


# ─────────────────────────────────────────────────────────────────────────────
# Embedding helper
# ─────────────────────────────────────────────────────────────────────────────

def _embed(text: str) -> List[float]:
    """Generate a 1536-dimension embedding using OpenAI text-embedding-3-small."""
    import openai
    client = openai.OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


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
def create_qa_pair(body: QAPairCreate) -> Dict[str, Any]:
    embedding = _embed(body.question)
    sb = get_supabase_client()
    res = sb.table("qa_pairs").insert({
        "question": body.question,
        "answer": body.answer,
        "embedding": embedding,
    }).execute()
    return res.data[0]


@router.put("/qa/{row_id}", response_model=Dict[str, Any])
def update_qa_pair(row_id: UUID, body: QAPairUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {}

    if body.question is not None:
        updates["question"] = body.question
        updates["embedding"] = _embed(body.question)  # regenerate when question changes
    if body.answer is not None:
        updates["answer"] = body.answer
    if body.active is not None:
        updates["active"] = body.active

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = sb.table("qa_pairs").update(updates).eq("id", str(row_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Row not found")
    return res.data[0]


@router.delete("/qa/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_qa_pair(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("qa_pairs").delete().eq("id", str(row_id)).execute()


# ── handoff_triggers ─────────────────────────────────────────────────────────

@router.get("/handoff", response_model=List[Dict[str, Any]])
def list_handoff_triggers() -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    res = sb.table("handoff_triggers").select("id,scenario,default_response,active,created_at,updated_at").order("created_at", desc=True).execute()
    return res.data


@router.post("/handoff", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_handoff_trigger(body: HandoffTriggerCreate) -> Dict[str, Any]:
    embedding = _embed(body.scenario)
    sb = get_supabase_client()
    res = sb.table("handoff_triggers").insert({
        "scenario": body.scenario,
        "default_response": body.default_response,
        "embedding": embedding,
    }).execute()
    return res.data[0]


@router.put("/handoff/{row_id}", response_model=Dict[str, Any])
def update_handoff_trigger(row_id: UUID, body: HandoffTriggerUpdate) -> Dict[str, Any]:
    sb = get_supabase_client()
    updates: Dict[str, Any] = {}

    if body.scenario is not None:
        updates["scenario"] = body.scenario
        updates["embedding"] = _embed(body.scenario)  # regenerate when scenario changes
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


@router.delete("/handoff/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_handoff_trigger(row_id: UUID) -> None:
    sb = get_supabase_client()
    sb.table("handoff_triggers").delete().eq("id", str(row_id)).execute()
