"""The packaged app exercises its own CA store and optional real download TLS."""

import io
import ssl
import tomllib
from pathlib import Path

import pytest

from kuulas import local_models, selftest


def test_certificates_are_a_direct_production_dependency():
    config = tomllib.loads((Path(__file__).parents[1] / 'pyproject.toml').read_text())
    assert any(item.startswith('certifi') for item in config['project']['dependencies'])


def test_offline_selftest_checks_roots_without_network(monkeypatch):
    monkeypatch.delenv('KUULAS_SELFTEST_HTTPS', raising=False)
    def offline(*args, **kwargs):
        pytest.fail('normal selftests must not require internet access')
    monkeypatch.setattr(local_models, 'urlopen', offline)
    assert 'model_tls' in selftest.CHECKS
    assert 'trusted roots' in selftest.check_model_tls()


def test_build_probe_verifies_actual_weight_endpoint_with_bounded_read(monkeypatch):
    monkeypatch.setenv('KUULAS_SELFTEST_HTTPS', '1')
    reads = []
    class Probe(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert 0 < size <= 8
            return super().read(size)
    def open_url(request, **kwargs):
        assert request.full_url.endswith('/model.safetensors')
        assert local_models.REVISION in request.full_url
        assert request.get_header('Range') == 'bytes=0-7'
        context = kwargs['context']
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        return Probe(b'synthetic header')
    monkeypatch.setattr(local_models, 'urlopen', open_url)
    assert 'model HTTPS verified' in selftest.check_model_tls()
    assert reads == [8]
