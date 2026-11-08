"""Decision card: the verdict JSON as a few short lines for a person, with no numbers of its own."""


def _health_issue(v: dict) -> str:
    h = v.get("health") or {}
    if h.get("dead_arm"):
        return f"dead arm {h['dead_arm']}"
    if h.get("srm"):
        return f"sample ratio mismatch, srm_p {h.get('srm_p')}"
    return "test is unhealthy"


def _status(v: dict) -> str:
    action = v.get("next_action")
    if action == "fix_test":
        return f"FIX TEST · {_health_issue(v)}"
    if action == "ship_leader":
        return f"SHIP {v.get('leader')}"
    if action == "ship_either":
        return "SHIP EITHER"
    return f"WAIT until {v.get('come_back_on')}" if v.get("come_back_on") else "WAIT"


def _headline(v: dict) -> str:
    parts = [_status(v)]
    if v.get("verdict"):
        parts.append(v["verdict"] + (f" ({v['reason']})" if v.get("reason") else ""))
    if v.get("next_action_basis"):
        parts.append(f"basis {v['next_action_basis']}")
    return " · ".join(parts)


def _confidence(v: dict) -> str | None:
    if v.get("p2bb_expected") is None:
        return None
    line = f"p2bb_expected {v['p2bb_expected']}"
    if v.get("p2bb_raw") is not None:
        line += f" (raw {v['p2bb_raw']})"
    if v.get("horizon_days") is not None:
        line += f" at a {v['horizon_days']}-day horizon"
    if v.get("maturity") is not None:
        line += f" · maturity {v['maturity']} ({round(v['maturity'] * 100)}% of expected revenue received)"
    return line


def _leader_revenue(v: dict) -> str | None:
    arm = next((a for a in v.get("arms") or [] if a.get("title") == v.get("leader")), None)
    if arm is None:
        return None
    return (f"{arm.get('title')} per user: received ${arm.get('revenue_received')}, "
            f"from trials ${arm.get('revenue_expected_trials')}, from renewals ${arm.get('revenue_expected_renewals')}, "
            f"expected ${arm.get('revenue_expected_total')}")


def _money(v: dict) -> str | None:
    m = v.get("money")
    if not m:
        return None
    parts = []
    if m.get("cost_per_day") is not None:
        parts.append(f"each more test day costs ${m['cost_per_day']}")
    if m.get("loss_if_ship_leader_now") is not None:
        parts.append(f"shipping {v.get('leader')} now: expected loss ${m['loss_if_ship_leader_now']}")
    if m.get("cost_until_come_back") is not None and v.get("come_back_on"):
        parts.append(f"waiting until {v['come_back_on']}: ${m['cost_until_come_back']}")
    if m.get("chance_leader_is_wrong") is not None:
        parts.append(f"chance the leader is wrong {m['chance_leader_is_wrong']}")
    return " · ".join(parts) or None


def render_card(v: dict) -> str:
    if "error" in v:
        return f"ERROR: {v.get('error')}"
    lines = [_headline(v), _confidence(v), _leader_revenue(v), _money(v)]
    return "\n".join(line for line in lines if line)
