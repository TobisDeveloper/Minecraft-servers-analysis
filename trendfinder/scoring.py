"""Transparent heuristics, not forecasts. Unknown coverage never grants points."""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from dataclasses import asdict

from .models import Candidate, Observation

WEIGHTS = {"creators": .25, "search": .30, "mods": .15, "community": .20, "servers": .10}


def clip(x, low=0.0, high=100.0):
    return max(low, min(high, x))


def series_metrics(series: list[dict]) -> dict:
    """Weekly momentum with low-volume and isolated-spike protection."""
    ordered = sorted({p["date"]: float(p["value"]) for p in series}.items())
    vals = [max(0, v) for _, v in ordered]
    if len(vals) < 12:
        return {"usable": False, "reason": "Fewer than 12 complete observations"}
    recent, previous = statistics.mean(vals[-4:]), statistics.mean(vals[-8:-4])
    low = statistics.mean(vals) < 5 or sum(v == 0 for v in vals) / len(vals) > .60
    window = vals[-8:]
    median = statistics.median(window)
    spike = max(window) > max(10, median * 3) and recent < max(window) * .55
    xbar, ybar = 3.5, statistics.mean(window)
    slope = sum((i - xbar) * (v - ybar) for i, v in enumerate(window)) / 42
    growth = (recent - previous) / max(previous, 5) * 100
    rising_steps = sum(b >= a for a, b in zip(window, window[1:]))
    sustained = slope > .5 and growth > 10 and rising_steps >= 4 and not spike and not low
    signal = clip(growth * .7 + max(0, slope) * 3) if sustained else min(20, max(0, growth) * .2)
    if low or spike: signal *= .2
    return {"usable": True, "growth_percent": round(growth, 1), "slope_per_week": round(slope, 2),
            "recent_mean": round(recent, 1), "previous_mean": round(previous, 1), "low_volume": low,
            "spike": spike, "sustained": sustained, "signal": round(signal, 1), "points": len(vals)}


def _age(o: Observation) -> float | None:
    try:
        return max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(o.published_at.replace("Z", "+00:00"))).total_seconds() / 86400)
    except (ValueError, TypeError):
        return None


def _onset(o: Observation) -> str | None:
    vals = sorted(o.series, key=lambda p: p["date"])
    for i in range(8, len(vals) - 3):
        before = statistics.mean(p["value"] for p in vals[i - 8:i - 4])
        after = statistics.mean(p["value"] for p in vals[i - 4:i])
        maintained = statistics.mean(p["value"] for p in vals[i:i + 4])
        if before >= 5 and after >= before * 1.3 and maintained >= after * .9:
            return vals[i - 4]["date"]
    return None


def score(candidate: Candidate, observations: list[Observation], cfg: dict) -> dict:
    # One URL/metric/market per candidate, even if imported and fetched directly.
    obs, seen = [], set()
    for o in observations:
        if o.candidate != candidate.id: continue
        key = (o.url, o.metric, o.market)
        if key not in seen:
            seen.add(key); obs.append(o)
    signals = {name: 0.0 for name in WEIGHTS}
    reasons, caveats, search = [], [], []
    family_set = set()
    for o in obs:
        if o.family in WEIGHTS and not (o.metric == "listing_count" and o.value == 0): family_set.add(o.family)

    creators = [o for o in obs if o.family == "creators" and _age(o) is not None and _age(o) <= cfg["days"]]
    channels = set()
    breakouts = 0
    creator_scores = []
    for o in creators:
        channels.add(o.attrs.get("channel_id") or o.attrs.get("channel") or o.url)
        subs = o.attrs.get("subscribers", 0)
        ratio = o.value / subs if subs and o.metric == "views" else 0
        mid = 50_000 <= subs <= 500_000
        age = _age(o)
        breakout = mid and ratio >= 1 and 1 <= age <= 30
        if breakout: breakouts += 1
        creator_scores.append((40 if breakout else 15 if ratio > .3 else 5) + (10 if o.market in {"CZ", "SK", "CZ/SK"} else 0))
    if creators:
        signals["creators"] = clip(sum(sorted(creator_scores, reverse=True)[:4]) + min(20, len(channels) * 5))
        reasons.append(f"{len(creators)} dated creator items across {len(channels)} channels; {breakouts} mid-size view/subscriber breakouts.")
    elif any(o.family == "creators" for o in obs):
        caveats.append("Creator items lack usable publication dates; no creator-growth points awarded.")
    if creators: caveats.append("Creator breakout uses views/subscribers, not a channel's usual view baseline; views are not buyer counts.")

    for o in obs:
        if o.family != "search": continue
        m = series_metrics(o.series)
        search.append({"market": o.market, **m, "evidence_id": o.id})
    local_search = [s for s in search if s["market"] in {"CZ", "SK"} and s.get("usable")]
    international = [s for s in search if s["market"] not in {"CZ", "SK"} and s.get("usable")]
    if local_search:
        # Divide by both target markets; missing one does not inflate confidence.
        signals["search"] = sum(s["signal"] for s in local_search) / 2
        for s in local_search:
            reasons.append(f'{s["market"]} search: {s["growth_percent"]:+.1f}% recent four weeks vs prior four; '
                           + ("sustained climb." if s["sustained"] else "not a sustained climb."))
    if not local_search:
        caveats.append("No usable CZ/SK search time series; local demand is unconfirmed.")
    lag = None
    if international and any(s.get("sustained") for s in international):
        signals["search"] = clip(signals["search"] + 5)
        globals_ = [o for o in obs if o.family == "search" and o.market not in {"CZ", "SK"}]
        locals_ = [o for o in obs if o.family == "search" and o.market in {"CZ", "SK"}]
        pairs = []
        for g in globals_:
            for loc in locals_:
                go, lo = _onset(g), _onset(loc)
                if go and lo:
                    weeks = (datetime.fromisoformat(lo) - datetime.fromisoformat(go)).days / 7
                    if 0 < weeks <= 26: pairs.append(weeks)
        if pairs:
            lag = round(statistics.median(pairs), 1)
            reasons.append(f"Observed search take-off lag: about {lag} weeks (heuristic, not a forecast).")

    mods = [o for o in obs if o.family == "mods"]
    velocity = [o for o in mods if "history" in o.attrs]
    if mods:
        # Cumulative totals indicate existence, not growth; at most 15/100 points.
        signals["mods"] = min(15, math.log10(max(o.value for o in mods) + 1) * 2)
        if velocity:
            rate = sum(max(0, o.attrs["history"]["per_day"]) for o in velocity)
            signals["mods"] = clip(math.log10(rate + 1) * 22)
            reasons.append(f"Observed modpack download velocity: {rate:,.1f}/day across {len(velocity)} matched projects.")
        else:
            caveats.append("Only one modpack snapshot; downloads/day and acceleration require repeat live scans at least 24 hours apart.")

    community = [o for o in obs if o.family == "community" and _age(o) is not None and _age(o) <= cfg["days"]]
    questions = [o for o in community if o.metric == "hosting_question"]
    recent_q = sum(_age(o) <= 14 for o in questions)
    prior_q = sum(14 < _age(o) <= 28 for o in questions)
    signals["community"] = clip(len(questions) * 10 + min(15, len(community) * 2))
    if questions:
        reasons.append(f"{len(questions)} unique hosting-intent discussions; {recent_q} in the last 14 days vs {prior_q} in the prior 14.")
    if any(o.family == "community" for o in obs):
        caveats.append("Community collection is a recent-post sample; repeated questions indicate intent, not total market size.")

    listings = [o for o in obs if o.family == "servers" and o.market in {"CZ", "SK", "CZ/SK"}]
    saturation = None
    if listings:
        total = sum(o.attrs.get("sample_size", 0) for o in listings)
        saturation = sum(o.value for o in listings) / max(1, total)
        increasing = [o for o in listings if o.attrs.get("history", {}).get("delta", 0) > 0]
        signals["servers"] = min(60, len(increasing) * 20)
        if not increasing: caveats.append("Server tags have no measured positive change yet; low observed supply alone is not an early signal.")
        reasons.append(f"Matched {sum(o.value for o in listings):.0f}/{total} sampled local listings ({saturation:.1%}); sample, not market share.")
    else:
        caveats.append("Local server supply is unknown; absence of evidence is not a hosting gap.")
    if any(o.family == "reports" for o in obs):
        caveats.append("General reports are context only and contribute no trend points.")

    local = [o for o in obs if o.market in {"CZ", "SK", "CZ/SK"} and o.family != "reports"
             and (any(p["value"] >= 5 for p in o.series) if o.family == "search" else o.value > 0)]
    temporal = any(s.get("sustained") for s in local_search) or bool(velocity) or recent_q >= max(3, prior_q * 1.5)
    covered = len(family_set)
    confidence = clip(covered * 12 + min(20, len(local) * 3) + (12 if temporal else 0) + (8 if len(local_search) == 2 else 0))
    raw = sum(signals[k] * weight for k, weight in WEIGHTS.items())
    penalty = min(18, (saturation or 0) * 45)
    risk_penalty = 8 if any(s.get("spike") for s in local_search) else 0
    total = clip((raw - penalty - risk_penalty) * (.45 + .55 * confidence / 100))
    local_demand = (any(s.get("sustained") for s in local_search)
                    or sum(o.market in {"CZ", "SK", "CZ/SK"} for o in questions) >= 2
                    or len({o.attrs.get("channel_id") or o.url for o in creators if o.market in {"CZ", "SK", "CZ/SK"}}) >= 2)
    early = total >= 45 and confidence >= 60 and covered >= 3 and local_demand and temporal
    if early: stage = "PILOT CANDIDATE"
    elif not obs or covered < 2 or not local: stage = "INSUFFICIENT EVIDENCE"
    elif saturation is not None and saturation >= .2: stage = "ESTABLISHED / CROWDED"
    else: stage = "WATCH / VALIDATE"
    e = cfg["economics"]
    price = float(e["price_per_month"])
    support = float(e["support_minutes_per_month"]) / 60 * float(e["support_cost_per_hour"])
    cost = candidate.ram_gb * float(e["ram_cost_per_gb"]) + float(e["cpu_storage_per_month"]) + support + price * float(e["payment_fee_percent"]) / 100 + float(e["fixed_fee"])
    return {"candidate": asdict(candidate), "score": round(total, 1), "raw_score": round(raw, 1),
            "confidence": round(confidence), "stage": stage, "signals": {k: round(v, 1) for k, v in signals.items()},
            "penalties": {"supply": round(penalty, 1), "spike": risk_penalty}, "search": search, "lag_weeks": lag,
            "reasons": reasons, "caveats": caveats, "evidence_ids": [o.id for o in obs], "families": sorted(family_set),
            "local_evidence": len(local), "temporal_evidence": temporal,
            "economics": {"price": price, "cost": round(cost, 2), "contribution": round(price - cost, 2),
                          "margin_percent": round((price - cost) / price * 100, 1) if price > 0 else 0,
                          "currency": e["currency"], "ram_gb": candidate.ram_gb}}


def rank(candidates, observations, cfg):
    return sorted([score(c, observations, cfg) for c in candidates], key=lambda r: (-r["score"], -r["confidence"], r["candidate"]["name"]))
