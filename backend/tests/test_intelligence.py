import pytest
from pydantic import ValidationError

from app.collector import CollectionError, require_public_ip
from app.demo import demo_snapshots
from app.intelligence import changes_between, enrich, graph_for, portfolio, simulate
from app.schemas import Intelligence, ScanRequest


@pytest.mark.parametrize(
    "value",
    [
        "https://github.com",
        "127.0.0.1",
        "localhost",
        "a.internal",
        "foo.local",
        "domain.com:443",
        "user@domain.com",
        "domain.com/path",
        "example.com%0d%0aevil",
        "a..com",
        "-x.com",
        "x-.com",
        "foo.example",
        "a" * 64 + ".com",
    ],
)
def test_invalid_or_private_domains_rejected(value):
    with pytest.raises(ValidationError):
        ScanRequest(domain=value)


def test_domain_normalization():
    assert ScanRequest(domain=" GitHub.COM. ").domain == "github.com"
    assert ScanRequest(domain="bücher.de").domain == "xn--bcher-kva.de"


@pytest.mark.parametrize(
    "value",
    [
        "127.0.0.1",
        "10.1.1.1",
        "169.254.169.254",
        "192.168.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:8.8.8.8",
        "203.0.113.1",
        "0.0.0.0",
        "224.0.0.1",
    ],
)
def test_ssrf_addresses_rejected(value):
    with pytest.raises(CollectionError):
        require_public_ip(value)


def test_global_addresses_allowed():
    assert require_public_ip("8.8.8.8") == "8.8.8.8"
    assert require_public_ip("2606:4700:4700::1111") == "2606:4700:4700::1111"


def test_demo_is_explicit_and_graph_is_well_formed():
    snapshots = demo_snapshots()
    assert all(s["intelligence"]["mode"] == "demo" and s["domain"].endswith(".example") for s in snapshots)
    graph = graph_for(snapshots)
    ids = {n["id"] for n in graph["nodes"]}
    assert len(ids) == len(graph["nodes"])
    assert all(edge["source"] in ids and edge["target"] in ids for edge in graph["edges"])
    assert len({edge["id"] for edge in graph["edges"]}) == len(graph["edges"])
    assert any(node["kind"] == "asn" for node in graph["nodes"])


def test_portfolio_uses_latest_per_domain_not_snapshot_count():
    snapshots = demo_snapshots()
    assert len(snapshots) == 7
    result = portfolio(snapshots)
    assert result["asset_count"] == 6
    cloudflare = next(p for p in result["providers"] if p["id"] == "cloudflare")
    assert sorted(cloudflare["assets"]) == ["atlas.example", "orbit.example"]
    assert cloudflare["concentration"] == 33


def test_simulation_is_scoped_observed_exposure():
    result = simulate(demo_snapshots(), "aws")
    assert result["affected_assets"] == ["relay.example", "stream.example"]
    assert "domain:stream.example" in result["affected_node_ids"]
    assert "not a forecast" in result["interpretation"].lower()
    with pytest.raises(ValueError):
        simulate(demo_snapshots(), "invented-provider")


def test_unknown_evidence_not_reported_as_proven_unsafe():
    intel = Intelligence.model_validate(demo_snapshots()[0]["intelligence"])
    intel.tls = None
    intel.dnssec_validated = None
    intel.dns = {}
    intel.evidence = []
    intel.headers = {}
    result = enrich(intel)
    assert result.overall_score is None
    assert result.coverage == 0
    assert all(score.score is None for score in result.scores)


def test_provider_hostname_suffix_not_substring():
    intel = Intelligence.model_validate(demo_snapshots()[0]["intelligence"])
    intel.tls = None
    intel.dns = {"NS": ["notcloudflare.com.attacker.net.", "cloudflare.com.evil.net."]}
    intel.evidence = []
    intel.headers = {}
    assert enrich(intel).providers == []


def test_snapshot_diff_detects_cert_and_dns_changes():
    intel = Intelligence.model_validate(demo_snapshots()[0]["intelligence"])
    changed = intel.model_copy(deep=True)
    changed.dns["A"] = ["1.1.1.1"]
    changed.tls.fingerprint = "different"
    changes = changes_between(intel, changed)
    assert "A records changed" in changes
    assert any("Certificate" in item for item in changes)
    assert changes_between(intel, intel)[0].startswith("No changes")
