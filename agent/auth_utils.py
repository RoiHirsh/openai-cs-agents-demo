"""Shared authentication dependency for admin/dashboard endpoints."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException


def require_dashboard_key(x_dashboard_key: Optional[str] = Header(default=None)) -> None:
    expected = os.environ.get("DASHBOARD_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="DASHBOARD_API_KEY not configured")
    if x_dashboard_key != expected:
        raise HTTPException(status_code=401, detail="Invalid dashboard key")
