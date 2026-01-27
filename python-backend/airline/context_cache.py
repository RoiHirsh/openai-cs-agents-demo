"""Module-level cache for lead information and onboarding state to persist across agent handoffs."""

# Global cache: thread_id -> lead_info dict
_lead_info_cache: dict[str, dict] = {}

# Global cache: thread_id -> onboarding_state dict
_onboarding_state_cache: dict[str, dict] = {}


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


def get_onboarding_state_cache() -> dict[str, dict]:
    """Get the global onboarding state cache."""
    return _onboarding_state_cache


def set_onboarding_state(thread_id: str, onboarding_state: dict) -> None:
    """Store onboarding state for a thread."""
    _onboarding_state_cache[thread_id] = onboarding_state.copy()


def get_onboarding_state(thread_id: str) -> dict | None:
    """Get cached onboarding state for a thread."""
    return _onboarding_state_cache.get(thread_id)


def restore_onboarding_state_to_context(thread_id: str, context) -> None:
    """Restore onboarding state from cache to a context object."""
    cached = get_onboarding_state(thread_id)
    if not cached:
        return
    
    # Restore onboarding_state if it's missing or empty
    if cached and (context.onboarding_state is None or not context.onboarding_state):
        context.onboarding_state = cached.copy()
        print(f"[DEBUG] Restored onboarding_state from cache for thread {thread_id}")
    elif cached and context.onboarding_state:
        # Merge cached state with existing state (cached takes precedence for non-None values)
        for key, value in cached.items():
            if value is not None:
                context.onboarding_state[key] = value
        print(f"[DEBUG] Merged onboarding_state from cache for thread {thread_id}")
