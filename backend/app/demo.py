from datetime import datetime, timedelta, timezone

from app.intelligence import changes_between, enrich
from app.schemas import Evidence, Intelligence, Location, TLSDetails

DEMO_TIME = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def demo_snapshots() -> list[dict]:
    snapshots = []
    fixtures = [
        ("atlas.example", "cloudflare", "Cloudflare", "AS13335 CLOUDFLARENET", "United States", 37.77, -122.42),
        ("stream.example", "aws", "Amazon", "AS16509 AMAZON-02", "Ireland", 53.35, -6.26),
        ("orbit.example", "cloudflare", "Cloudflare", "AS13335 CLOUDFLARENET", "Singapore", 1.35, 103.82),
        ("forge.example", "google", "Google", "AS15169 GOOGLE", "Germany", 50.11, 8.68),
        ("relay.example", "aws", "Amazon", "AS16509 AMAZON-02", "United Kingdom", 51.51, -0.13),
        ("pulse.example", "fastly", "Fastly", "AS54113 FASTLY", "Australia", -33.87, 151.21),
    ]
    for index, (domain, provider, name, asn, country, lat, lng) in enumerate(fixtures):
        time = DEMO_TIME + timedelta(hours=index)
        ns = {
            "cloudflare": ["nova.ns.cloudflare.com.", "kai.ns.cloudflare.com."],
            "aws": ["ns-122.awsdns-15.com.", "ns-45.awsdns-20.net."],
            "google": ["ns1.googledomains.com.", "ns2.googledomains.com."],
            "fastly": ["a.ns.fastlydns.net.", "b.ns.fastlydns.net."],
        }[provider]
        headers = {"server": name.lower(), "strict-transport-security": "max-age=31536000"}
        if provider == "cloudflare":
            headers["cf-ray"] = "synthetic-demo-signal"
        if provider == "aws":
            headers["x-amz-cf-id"] = "synthetic-demo-signal"
        if provider == "fastly":
            headers["via"] = "1.1 varnish (Fastly)"
        dns = {
            "A": [f"203.0.113.{index + 10}"],
            "AAAA": [],
            "NS": ns,
            "MX": ["10 mail.example."],
            "TXT": ['"v=spf1 -all"'],
            "DMARC": ['"v=DMARC1; p=reject"'] if index != 2 else [],
            "CAA": ['0 issue "letsencrypt.org"'] if index != 2 else [],
            "CNAME": [],
        }
        evidence = [
            Evidence(
                id=f"dns-{kind.lower()}",
                category="dns",
                source="Synthetic demo fixture",
                observed_at=time,
                value=f"{kind}: {', '.join(values) or 'No records'}",
            )
            for kind, values in dns.items()
        ]
        evidence += [
            Evidence(id="asn-0", category="ownership", source="Synthetic demo fixture", observed_at=time, value=asn),
            Evidence(
                id="http-headers",
                category="http",
                source="Synthetic demo fixture",
                observed_at=time,
                value=str(headers),
            ),
            Evidence(
                id="tls-certificate",
                category="tls",
                source="Synthetic demo fixture",
                observed_at=time,
                value="Demo certificate; issuer R13",
            ),
        ]
        intel = enrich(
            Intelligence(
                domain=domain,
                collected_at=time,
                mode="demo",
                dns=dns,
                addresses=dns["A"],
                dnssec_validated=index != 2,
                headers=headers,
                tls=TLSDetails(
                    issuer="R13",
                    subject=f"CN={domain}",
                    not_after=time + timedelta(days=60 - index * 8),
                    days_remaining=60 - index * 8,
                    protocol="TLSv1.3",
                    fingerprint=f"demo-{index}",
                    verified=True,
                ),
                providers=[],
                locations=[
                    Location(
                        ip=dns["A"][0],
                        country=country,
                        latitude=lat,
                        longitude=lng,
                        source="Synthetic coordinates for demonstration",
                    )
                ],
                evidence=evidence,
                warnings=["Synthetic fixture. No claims are made about a real organization."],
            )
        )
        snapshots.append(
            {
                "id": f"demo-{index}",
                "domain": domain,
                "created_at": time.isoformat(),
                "intelligence": intel.model_dump(mode="json"),
                "changes": changes_between(None, intel),
            }
        )
    previous = dict(snapshots[0])
    previous["id"] = "demo-baseline"
    previous["created_at"] = (DEMO_TIME - timedelta(days=7)).isoformat()
    previous_intel = Intelligence.model_validate(snapshots[0]["intelligence"]).model_copy(deep=True)
    previous_intel.dns["A"] = ["203.0.113.99"]
    previous_intel.tls.fingerprint = "older-demo-certificate"
    previous["intelligence"] = previous_intel.model_dump(mode="json")
    snapshots[0]["changes"] = changes_between(previous_intel, Intelligence.model_validate(snapshots[0]["intelligence"]))
    return sorted([*snapshots, previous], key=lambda s: s["created_at"], reverse=True)
