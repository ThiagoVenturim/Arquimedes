"""Shared fixtures. The whole suite runs offline."""

from __future__ import annotations

import socket

import pytest

from arquimedes.problema import BinPackingOnline


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """Fail loudly if anything in the test process tries to open a socket."""

    def bloqueado(*args, **kwargs):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(socket, "socket", bloqueado)
    monkeypatch.setattr(socket, "create_connection", bloqueado)


class ProblemaPequeno(BinPackingOnline):
    """One hand-checked instance: first-fit needs 3 bins, best-fit needs 2."""

    def instancias(self):
        return [{"capacidade": 100, "itens": [50, 60, 40, 50]}]


@pytest.fixture
def problema_pequeno():
    return ProblemaPequeno()
