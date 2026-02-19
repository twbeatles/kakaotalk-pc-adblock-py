import importlib.util
import logging
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "카카오톡 광고제거 v10.0.py"
    spec = importlib.util.spec_from_file_location("kakao_adblock", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeHostsManager:
    def __init__(self, should_succeed: bool):
        self.should_succeed = should_succeed
        self.calls = 0
        self.last_domains = []

    def block(self, domains):
        self.calls += 1
        self.last_domains = list(domains)
        return self.should_succeed


def test_run_smart_optimize_failed_stops_after_hosts(monkeypatch):
    m = load_module()
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    hosts = FakeHostsManager(False)
    counters = {"dns": 0, "restart": 0}

    def fake_dns():
        counters["dns"] += 1
        return True

    def fake_restart(_name):
        counters["restart"] += 1
        return True

    monkeypatch.setattr(m.SystemManager, "flush_dns", staticmethod(fake_dns))
    monkeypatch.setattr(m.SystemManager, "restart_process", staticmethod(fake_restart))

    result = m.run_smart_optimize(logger, hosts, ["Example.com", "example.com", "bad domain"])
    assert result.overall_status == "failed"
    assert result.hosts_blocked is False
    assert result.dns_flushed is False
    assert result.process_restarted is False
    assert counters["dns"] == 0
    assert counters["restart"] == 0
    assert hosts.calls == 1
    assert hosts.last_domains == ["example.com"]


def test_run_smart_optimize_partial_when_dns_fails(monkeypatch):
    m = load_module()
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    hosts = FakeHostsManager(True)

    monkeypatch.setattr(m.SystemManager, "flush_dns", staticmethod(lambda: False))
    monkeypatch.setattr(m.SystemManager, "restart_process", staticmethod(lambda _name: True))

    result = m.run_smart_optimize(logger, hosts, ["ad.kakao.com"])
    assert result.overall_status == "partial"
    assert result.hosts_blocked is True
    assert result.dns_flushed is False
    assert result.process_restarted is True
    assert result.blocked_domain_count == 1


def test_run_smart_optimize_success(monkeypatch):
    m = load_module()
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    hosts = FakeHostsManager(True)

    monkeypatch.setattr(m.SystemManager, "flush_dns", staticmethod(lambda: True))
    monkeypatch.setattr(m.SystemManager, "restart_process", staticmethod(lambda _name: True))

    result = m.run_smart_optimize(logger, hosts, ["ad.kakao.com", "display.ad.daum.net"])
    assert result.overall_status == "success"
    assert result.hosts_blocked is True
    assert result.dns_flushed is True
    assert result.process_restarted is True
    assert result.blocked_domain_count == 2
    assert result.errors == []
