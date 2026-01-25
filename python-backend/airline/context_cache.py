"""Module-level cache for lead information to persist across agent handoffs."""

# Global cache: thread_id -> lead_info dict
_lead_info_cache: dict[str, dict] = {}


def get_lead_info_cache() -> dict[str, dict]:
    """Get the global lead info cache."""
    return _lead_info_cache


def set_lead_info(thread_id: str, lead_info: dict) -> None:
    """Store lead info for a thread."""
    _lead_info_cache[thread_id] = lead_info.copy()


def get_lead_info(thread_id: str) -> dict | None:
    """Get cached lead info for a thread."""
    return _lead_info_cache.get(thread_id)


def restore_lead_info_to_context(thread_id: str, context) -> None:
    """Restore lead info from cache to a context object."""
    cached = get_lead_info(thread_id)
    if not cached:
        return
    
    # Restore all lead info fields if they're missing
    if cached.get("country") and (not context.country or context.country == "Unknown"):
        context.country = cached["country"]
    if cached.get("first_name") and not context.first_name:
        context.first_name = cached["first_name"]
    if cached.get("email") and not context.email:
        context.email = cached["email"]
    if cached.get("phone") and not context.phone:
        context.phone = cached["phone"]
    if cached.get("new_lead") is not None and context.new_lead is False:
        context.new_lead = cached["new_lead"]
