# -*- coding: utf-8 -*-
"""自动建库脚本测试。"""
import pytest


def test_create_database_sql_valid():
    from scripts.ensure_database import create_database_sql

    sql = create_database_sql('FactoryManagementSystem')
    assert 'CREATE DATABASE IF NOT EXISTS `FactoryManagementSystem`' in sql
    assert 'utf8mb4_unicode_ci' in sql


def test_create_database_sql_rejects_invalid_identifier():
    from scripts.ensure_database import create_database_sql

    with pytest.raises(ValueError):
        create_database_sql('bad-name; DROP DATABASE test')


def test_ensure_database_skips_sqlite(monkeypatch, capsys):
    from config import Config
    from scripts.ensure_database import ensure_database

    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///factory_mgmt.db')
    ensure_database()
    assert 'SQLite' in capsys.readouterr().out
