def compute_score(data: dict) -> int:
    """
    Compute automation score 0-100 from enrichment data.

    booking_system present        → +25
    manual_workflows signal       → +20
    appointment_heavy signal      → +25
    recruitment_active signal     → +10
    no phone AND no email         → +10
    automation_opportunities ≥ 1  → +20
    """
    score = 0
    contact = data.get("contact") or {}
    signals = data.get("signals") or {}
    opportunities = data.get("automation_opportunities") or []

    if contact.get("booking_system"):
        score += 25
    if signals.get("manual_workflows"):
        score += 20
    if signals.get("appointment_heavy"):
        score += 25
    if signals.get("recruitment_active"):
        score += 10
    if not contact.get("phone") and not contact.get("email"):
        score += 10
    if opportunities:
        score += 20

    return min(score, 100)
