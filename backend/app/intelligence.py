import re
from collections import defaultdict

from app.schemas import CategoryScore, Intelligence, Provider

PROVIDER_RULES = [
    ("cloudflare", "Cloudflare", r"(?:^|\.)cloudflare\.com\.?$"),
    (
        "aws",
        "Amazon Web Services",
        r"(?:^|\.)awss?dns-[a-z0-9-]+\.(?:com|net|org|co\.uk)\.?$|(?:^|\.)cloudfront\.net\.?$",
    ),
    ("google", "Google Cloud", r"(?:^|\.)google(?:mail)?\.com\.?$|(?:^|\.)googledomains\.com\.?$"),
    ("akamai", "Akamai", r"(?:^|\.)(?:akam\.net|akamai\.net|akamaiedge\.net|akamaihd\.net)\.?$"),
    ("fastly", "Fastly", r"(?:^|\.)fastly(?:dns)?\.net\.?$"),
    ("azure", "Microsoft Azure", r"(?:^|\.)azure-dns\.(?:com|net|org|info)\.?$|(?:^|\.)azureedge\.net\.?$"),
]


def enrich(intel: Intelligence) -> Intelligence:
    providers: dict[str, Provider] = {}

    def add(key: str, name: str, role: str, evidence_id: str):
        if key not in providers:
            providers[key] = Provider(id=key, name=name, roles=[], evidence_ids=[])
        provider = providers[key]
        if role not in provider.roles:
            provider.roles.append(role)
        if evidence_id not in provider.evidence_ids:
            provider.evidence_ids.append(evidence_id)

    for record_type, role in (("NS", "DNS"), ("CNAME", "CDN"), ("MX", "Email")):
        for value in intel.dns.get(record_type, []):
            hostname = value.split()[-1].lower()
            for key, name, pattern in PROVIDER_RULES:
                if re.search(pattern, hostname):
                    add(key, name, role, f"dns-{record_type.lower()}")
    if intel.headers.get("cf-ray"):
        add("cloudflare", "Cloudflare", "Edge", "http-headers")
    if intel.headers.get("x-amz-cf-id"):
        add("aws", "Amazon Web Services", "CDN", "http-headers")
    if "fastly" in intel.headers.get("via", "").lower():
        add("fastly", "Fastly", "CDN", "http-headers")
    for item in intel.evidence:
        if item.category == "ownership":
            value = item.value.lower()
            for key, name, marker in [
                ("aws", "Amazon Web Services", "amazon"),
                ("google", "Google Cloud", "google"),
                ("cloudflare", "Cloudflare", "cloudflare"),
                ("azure", "Microsoft Azure", "microsoft"),
                ("akamai", "Akamai", "akamai"),
                ("fastly", "Fastly", "fastly"),
            ]:
                if marker in value:
                    add(key, name, "Network ownership", item.id)
    if intel.tls:
        issuer = intel.tls.issuer
        key = "ca-" + re.sub(r"[^a-z0-9]+", "-", issuer.lower()).strip("-")[:70]
        add(key, issuer, "Certificate authority", "tls-certificate")
    intel.providers = list(providers.values())
    scores = []

    def score(name: str, value: int | None, why: str, evidence_ids: list[str]):
        scores.append(CategoryScore(name=name, score=value, explanation=why, evidence_ids=evidence_ids))

    if intel.dnssec_validated is None:
        score("DNS security", None, "DNSSEC validation status was not obtained.", [])
    else:
        ns_count = len(set(intel.dns.get("NS", [])))
        value = (
            (70 if intel.dnssec_validated else 15) + (20 if ns_count >= 2 else 0) + (10 if intel.dns.get("CAA") else 0)
        )
        score(
            "DNS security",
            value,
            "Resolver AD flag (70), at least two NS names (20), CAA observed (10). NS names do not prove independent failure domains.",
            ["dns-a", "dns-ns", "dns-caa"],
        )
    if intel.tls:
        score(
            "TLS security",
            100 if intel.tls.protocol == "TLSv1.3" else 75,
            "Verified hostname/chain and negotiated protocol; not a full cipher-suite or legacy-protocol audit.",
            ["tls-certificate"],
        )
        days = intel.tls.days_remaining
        score(
            "Certificate health",
            100 if days > 30 else 65 if days > 7 else 20,
            f"Observed certificate expires in {days} days. Short-lived certificates may renew automatically.",
            ["tls-certificate"],
        )
    else:
        score("TLS security", None, "TLS handshake unavailable; unknown is not a proven vulnerability.", [])
        score("Certificate health", None, "No verified certificate was obtained.", [])
    infrastructure = [
        p for p in providers.values() if any(r in p.roles for r in ("DNS", "Edge", "CDN", "Network ownership"))
    ]
    if infrastructure:
        score(
            "Provider diversity",
            min(100, 25 + 25 * len(infrastructure)),
            f"{len(infrastructure)} provider identities inferred. Multiple vendors do not guarantee resilience.",
            [eid for p in infrastructure for eid in p.evidence_ids],
        )
    else:
        score("Provider diversity", None, "Provider ownership could not be inferred reliably.", [])
    if "TXT" in intel.dns and "DMARC" in intel.dns:
        spf = any("v=spf1" in value.lower() for value in intel.dns["TXT"])
        dmarc = " ".join(intel.dns["DMARC"]).lower()
        policy = bool(re.search(r"\bp\s*=\s*(?:reject|quarantine)\b", dmarc))
        value = (40 if spf else 0) + (60 if policy else 20 if "v=dmarc1" in dmarc else 0)
        score(
            "Email security",
            value,
            "SPF presence (40) and DMARC quarantine/reject (60). Policy syntax, alignment and DKIM are not fully audited.",
            ["dns-txt", "dns-dmarc"],
        )
    else:
        score("Email security", None, "Email policy lookups incomplete.", [])
    intel.scores = scores
    known = [s.score for s in scores if s.score is not None]
    intel.overall_score = round(sum(known) / len(known)) if known else None
    intel.coverage = round(100 * len(known) / 5)
    intel.warnings = list(
        dict.fromkeys(
            [
                *intel.warnings,
                "Provider relationships are heuristic inferences from public evidence, not proof of internal infrastructure.",
                "WAF enforcement, origin servers, routing paths, cloud lock-in and actual failover behavior are not verifiable from this scan.",
                "Score is an explainable observation index, not a penetration test, safety guarantee or compliance certification.",
            ]
        )
    )
    return intel


def changes_between(previous: Intelligence | None, current: Intelligence) -> list[str]:
    if previous is None:
        return ["Baseline snapshot recorded"]
    changes = []
    for record_type in sorted(set(previous.dns) | set(current.dns)):
        if set(previous.dns.get(record_type, [])) != set(current.dns.get(record_type, [])):
            changes.append(f"{record_type} records changed")
    if (previous.tls.fingerprint if previous.tls else None) != (current.tls.fingerprint if current.tls else None):
        changes.append("Certificate changed or certificate observation became unavailable")
    if {p.id for p in previous.providers} != {p.id for p in current.providers}:
        changes.append("Inferred provider set changed")
    if previous.headers != current.headers:
        changes.append("Observed server headers changed")
    return changes or ["No changes in compared DNS, certificate, providers or headers"]


def latest_assets(snapshots: list[dict]) -> list[dict]:
    result = {}
    for snapshot in snapshots:
        if snapshot["domain"] not in result:
            result[snapshot["domain"]] = snapshot
    return list(result.values())


def portfolio(snapshots: list[dict]) -> dict:
    assets = latest_assets(snapshots)
    groups: dict[str, dict] = {}
    for asset in assets:
        for provider in asset["intelligence"]["providers"]:
            group = groups.setdefault(
                provider["id"],
                {
                    "id": provider["id"],
                    "name": provider["name"],
                    "assets": [],
                    "roles": [],
                },
            )
            group["assets"].append(asset["domain"])
            group["roles"] = sorted(set(group["roles"] + provider["roles"]))
    for group in groups.values():
        group["concentration"] = round(100 * len(set(group["assets"])) / len(assets)) if assets else 0
    leaderboard = [
        {
            "domain": a["domain"],
            "score": a["intelligence"]["overall_score"],
            "coverage": a["intelligence"]["coverage"],
            "providers": len(a["intelligence"]["providers"]),
            "mode": a["intelligence"]["mode"],
        }
        for a in assets
    ]
    return {
        "asset_count": len(assets),
        "providers": sorted(groups.values(), key=lambda p: (-p["concentration"], p["id"])),
        "leaderboard": sorted(
            leaderboard, key=lambda a: (-(a["score"] if a["score"] is not None else -1), a["domain"])
        ),
        "scope": "Latest observed snapshot per domain in this workspace only; not an internet-wide ranking",
    }


def graph_for(snapshots: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges = []
    for asset in latest_assets(snapshots):
        intel = asset["intelligence"]
        domain_id = f"domain:{asset['domain']}"
        nodes[domain_id] = {
            "id": domain_id,
            "label": asset["domain"],
            "kind": "domain",
            "detail": f"{intel['overall_score'] if intel['overall_score'] is not None else '?'} / 100",
        }
        for provider in intel["providers"]:
            provider_id = f"provider:{provider['id']}"
            nodes[provider_id] = {
                "id": provider_id,
                "label": provider["name"],
                "kind": "provider",
                "provider_id": provider["id"],
                "detail": " / ".join(provider["roles"]),
            }
            edges.append(
                {
                    "id": f"{domain_id}>{provider_id}",
                    "source": domain_id,
                    "target": provider_id,
                    "label": " / ".join(provider["roles"]),
                    "confidence": "inferred",
                    "evidence_ids": provider["evidence_ids"],
                }
            )
        for address in intel["addresses"][:4]:
            ip_id = f"ip:{address}"
            nodes[ip_id] = {"id": ip_id, "label": address, "kind": "ip", "detail": "Observed DNS address"}
            edges.append(
                {
                    "id": f"{domain_id}>{ip_id}",
                    "source": domain_id,
                    "target": ip_id,
                    "label": "resolves to",
                    "confidence": "observed",
                    "evidence_ids": ["dns-a", "dns-aaaa"],
                }
            )
        for evidence in intel["evidence"]:
            if evidence["category"] == "ownership":
                for asn in re.findall(r"\bAS\d+\b", evidence["value"]):
                    asn_id = f"asn:{asn}"
                    nodes[asn_id] = {"id": asn_id, "label": asn, "kind": "asn", "detail": evidence["value"][:80]}
                    edges.append(
                        {
                            "id": f"{domain_id}>{asn_id}",
                            "source": domain_id,
                            "target": asn_id,
                            "label": "announced network",
                            "confidence": "observed",
                            "evidence_ids": [evidence["id"]],
                        }
                    )
    return {"nodes": list(nodes.values()), "edges": edges}


def simulate(snapshots: list[dict], provider_id: str) -> dict:
    data = portfolio(snapshots)
    provider = next((p for p in data["providers"] if p["id"] == provider_id), None)
    if not provider:
        raise ValueError("Provider not present in the observed workspace")
    graph = graph_for(snapshots)
    start = f"provider:{provider_id}"
    reverse = defaultdict(list)
    for edge in graph["edges"]:
        reverse[edge["target"]].append(edge["source"])
    affected = {start}
    pending = [start]
    while pending:
        for parent in reverse[pending.pop()]:
            if parent not in affected:
                affected.add(parent)
                pending.append(parent)
    return {
        "provider": provider["name"],
        "provider_id": provider_id,
        "affected_assets": sorted(set(provider["assets"])),
        "affected_node_ids": sorted(affected),
        "concentration": provider["concentration"],
        "interpretation": "Observed dependency exposure under a hypothetical provider outage. Not a forecast; failover and actual downtime are unknown.",
    }
