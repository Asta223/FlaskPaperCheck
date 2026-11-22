# -*- coding: utf-8 -*-
"""启动入口配置解析测试。"""
import pytest


@pytest.fixture
def clean_server_env(monkeypatch):
    for key in ('SERVER_HOST', 'SERVER_PORT', 'SERVER_THREADS', 'OPEN_BROWSER'):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_resolve_server_config_defaults(clean_server_env):
    from start_server import resolve_server_config

    assert resolve_server_config() == ('0.0.0.0', 5000, 8, True)


def test_resolve_server_config_custom_values(clean_server_env):
    clean_server_env.setenv('SERVER_HOST', '127.0.0.1')
    clean_server_env.setenv('SERVER_PORT', '6001')
    clean_server_env.setenv('SERVER_THREADS', '3')
    clean_server_env.setenv('OPEN_BROWSER', '0')

    from start_server import resolve_server_config

    assert resolve_server_config() == ('127.0.0.1', 6001, 3, False)


def test_resolve_server_config_invalid_values_fallback(clean_server_env):
    clean_server_env.setenv('SERVER_PORT', 'not-a-number')
    clean_server_env.setenv('SERVER_THREADS', '0')
    clean_server_env.setenv('OPEN_BROWSER', 'off')

    from start_server import resolve_server_config

    host, port, threads, open_browser = resolve_server_config()
    assert host == '0.0.0.0'
    assert port == 5000
    assert threads == 1
    assert open_browser is False


def test_browser_url_uses_loopback_for_wildcard_bind():
    from start_server import browser_url

    assert browser_url('0.0.0.0', 5000) == 'http://127.0.0.1:5000'
    assert browser_url('127.0.0.1', 5000) == 'http://127.0.0.1:5000'
    assert browser_url('192.168.1.10', 8080) == 'http://192.168.1.10:8080'
