import hashlib
import http.client
import ipaddress
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from cryptography import x509
from cryptography.x509.oid import NameOID

from app.schemas import Evidence, Intelligence, Location, TLSDetails, normalize_domain

DNS_TYPES = ("A", "AAAA", "NS", "MX", "TXT", "CAA", "CNAME")
SAFE_HEADERS = ("server", "via", "cf-ray", "x-amz-cf-id", "x-served-by", "x-cache", "strict-transport-security")


class CollectionError(Exception):
    pass


def require_public_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast or getattr(address, "ipv4_mapped", None):
        raise CollectionError("Target resolves to a non-public or mapped address; connection blocked")
    return str(address)


def pinned_probe(domain: str, addresses: list[str]) -> tuple[dict[str, str], TLSDetails | None, list[str]]:
    if not addresses:
        return {}, None, ["HTTPS/TLS not observed: no public addresses"]
    for address in addresses:
        require_public_ip(address)
    warnings = []
    for address in addresses[:2]:
        try:
            with socket.create_connection((address, 443), timeout=5) as raw:
                context = ssl.create_default_context()
                with context.wrap_socket(raw, server_hostname=domain) as secure:
                    secure.settimeout(5)
                    der = secure.getpeercert(binary_form=True)
                    if der is None:
                        raise CollectionError("TLS peer certificate unavailable")
                    cert = x509.load_der_x509_certificate(der)
                    issuer_parts = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
                    issuer = issuer_parts[0].value if issuer_parts else cert.issuer.rfc4514_string()
                    expires = cert.not_valid_after_utc
                    tls = TLSDetails(
                        issuer=str(issuer),
                        subject=cert.subject.rfc4514_string(),
                        not_after=expires,
                        days_remaining=(expires - datetime.now(timezone.utc)).days,
                        protocol=secure.version() or "unknown",
                        fingerprint=hashlib.sha256(der).hexdigest(),
                        verified=True,
                    )
                    secure.sendall(
                        f"HEAD / HTTP/1.1\r\nHost: {domain}\r\nUser-Agent: ShadowInternet/0.1 (public infrastructure observation)\r\nConnection: close\r\n\r\n".encode(
                            "ascii"
                        )
                    )
                    response = http.client.HTTPResponse(secure)
                    response.begin()
                    headers = {
                        key: (response.getheader(key) or "")[:500] for key in SAFE_HEADERS if response.getheader(key)
                    }
                    # The socket is pinned to the checked public address. Redirects and bodies are never followed.
                    return headers, tls, [*warnings, f"HTTPS HEAD returned {response.status}; redirects not followed"]
        except (OSError, ssl.SSLError, http.client.HTTPException, CollectionError) as exc:
            warnings.append(f"HTTPS/TLS probe unavailable: {type(exc).__name__}")
    return {}, None, warnings


class PublicCollector:
    def collect(self, domain: str) -> Intelligence:
        domain = normalize_domain(domain)
        collected = datetime.now(timezone.utc)
        evidence: list[Evidence] = []
        warnings: list[str] = []
        dns: dict[str, list[str]] = {}
        validated: bool | None = None
        timeout = httpx.Timeout(6, connect=3)
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:

            def query(record_type: str):
                try:
                    response = client.get(
                        "https://cloudflare-dns.com/dns-query",
                        params={"name": domain, "type": record_type, "do": "true"},
                        headers={"Accept": "application/dns-json"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("Status") not in (0, 3):
                        raise CollectionError(f"DNS resolver returned status {payload.get('Status')}")
                    if payload.get("Status") == 3:
                        raise CollectionError("Domain does not exist (NXDOMAIN)")
                    return record_type, payload, None
                except (httpx.HTTPError, ValueError, CollectionError) as exc:
                    return record_type, None, f"{record_type} lookup unavailable: {str(exc)[:160]}"

            with ThreadPoolExecutor(max_workers=7) as executor:
                results = list(executor.map(query, DNS_TYPES))
            for record_type, payload, error in results:
                if error:
                    warnings.append(error)
                    continue
                if record_type == "A":
                    validated = payload.get("AD") if isinstance(payload.get("AD"), bool) else None
                expected_type = {"A": 1, "AAAA": 28, "NS": 2, "MX": 15, "TXT": 16, "CAA": 257, "CNAME": 5}[record_type]
                dns[record_type] = [
                    str(item["data"])[:2000]
                    for item in payload.get("Answer", [])
                    if item.get("type") == expected_type and "data" in item
                ][:30]
                evidence.append(
                    Evidence(
                        id=f"dns-{record_type.lower()}",
                        category="dns",
                        source=f"Cloudflare DNS-over-HTTPS, {record_type}",
                        observed_at=collected,
                        value=f"{record_type}: {', '.join(dns[record_type]) or 'No records returned'}",
                    )
                )
            if not dns:
                raise CollectionError("DNS intelligence unavailable; no successful record queries")
            addresses = list(dict.fromkeys(dns.get("A", []) + dns.get("AAAA", [])))
            for address in addresses:
                require_public_ip(address)
            if not addresses:
                warnings.append("No direct A/AAAA addresses observed; alias/origin dependencies may be incomplete")
            headers, tls, probe_warnings = pinned_probe(domain, addresses)
            warnings.extend(probe_warnings)
            if headers:
                evidence.append(
                    Evidence(
                        id="http-headers",
                        category="http",
                        source="Pinned public IP HTTPS HEAD /",
                        observed_at=collected,
                        value=str(headers),
                    )
                )
            if tls:
                evidence.append(
                    Evidence(
                        id="tls-certificate",
                        category="tls",
                        source="Verified TLS handshake on port 443",
                        observed_at=collected,
                        value=f"Issuer: {tls.issuer}; protocol: {tls.protocol}; expires: {tls.not_after.isoformat()}",
                    )
                )
            try:
                response = client.get(
                    "https://cloudflare-dns.com/dns-query",
                    params={"name": f"_dmarc.{domain}", "type": "TXT"},
                    headers={"Accept": "application/dns-json"},
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("Status") not in (0, 3):
                    raise CollectionError("DMARC DNS query failed")
                dns["DMARC"] = [
                    str(item["data"])[:2000] for item in payload.get("Answer", []) if item.get("type") == 16
                ]
                evidence.append(
                    Evidence(
                        id="dns-dmarc",
                        category="email",
                        source="Cloudflare DNS-over-HTTPS, _dmarc TXT",
                        observed_at=collected,
                        value=f"DMARC: {', '.join(dns['DMARC']) or 'No policy observed'}",
                    )
                )
            except (httpx.HTTPError, ValueError, CollectionError) as exc:
                warnings.append(f"DMARC unavailable: {type(exc).__name__}")
            locations = []
            for index, address in enumerate(addresses[:2]):
                try:
                    response = client.get(
                        "https://stat.ripe.net/data/prefix-overview/data.json", params={"resource": address}
                    )
                    response.raise_for_status()
                    data = response.json()["data"]
                    asns = data.get("asns", [])
                    if asns:
                        value = "; ".join(f"AS{item['asn']} {item.get('holder', 'unknown holder')}" for item in asns)
                        evidence.append(
                            Evidence(
                                id=f"asn-{index}",
                                category="ownership",
                                source=f"RIPEstat prefix overview for {address}",
                                observed_at=collected,
                                value=value,
                            )
                        )
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    warnings.append(f"ASN/ownership lookup unavailable: {type(exc).__name__}")
                try:
                    response = client.get(f"https://ipwho.is/{address}")
                    response.raise_for_status()
                    data = response.json()
                    if data.get("success") is not True:
                        raise CollectionError("Geolocation provider returned no result")
                    locations.append(
                        Location(
                            ip=address,
                            country=data["country"],
                            latitude=data["latitude"],
                            longitude=data["longitude"],
                            source="ipwho.is approximate IP geolocation",
                        )
                    )
                except (httpx.HTTPError, ValueError, KeyError, CollectionError) as exc:
                    warnings.append(f"IP geolocation unavailable: {type(exc).__name__}")
        return Intelligence(
            domain=domain,
            collected_at=collected,
            mode="live",
            dns=dns,
            dnssec_validated=validated,
            addresses=addresses,
            headers=headers,
            tls=tls,
            providers=[],
            locations=locations,
            evidence=evidence,
            warnings=warnings,
        )
