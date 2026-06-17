def compute_score(data: dict) -> int:
    """
    Compute automation score 0-100 from enrichment data.

    booking_system present                         → -10  (already solved)
    booking_system absent AND appointment_heavy    → +35  (appointments + no system = high pain)
    booking_system absent AND NOT appointment_heavy → +15 (generic manual workflow pain)
    manual_workflows signal                        → +20
    recruitment_active signal                      → +10
    no phone AND no email                          → +10
    automation_opportunities ≥ 1                   → +20
    Cap at 100, floor at 0.
    """
    score = 0
    contact = data.get("contact") or {}
    signals = data.get("signals") or {}
    opportunities = data.get("automation_opportunities") or []

    has_booking = bool(contact.get("booking_system"))
    appointment_heavy = bool(signals.get("appointment_heavy"))

    if has_booking:
        score -= 10
    else:
        if appointment_heavy:
            score += 35
        else:
            score += 15

    if signals.get("manual_workflows"):
        score += 20
    if signals.get("recruitment_active"):
        score += 10
    if not contact.get("phone") and not contact.get("email"):
        score += 10
    if opportunities:
        score += 20

    return max(0, min(score, 100))
