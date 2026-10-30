"""Quem pode usar a API: o token mestre (terminal, ESP32) ou um token de login da PWA."""

from __future__ import annotations

from hmac import compare_digest
import time
from typing import Callable, Protocol

MAX_FAILURES = 5
LOCK_SECONDS = 60.0


class LoginTokens(Protocol):
    def create(self, label: str) -> str: ...
    def is_valid(self, token: str) -> bool: ...
    def revoke(self, token: str) -> bool: ...


class LoginLocked(Exception):
    def __init__(self, seconds: float) -> None:
        super().__init__(f"Muitas tentativas erradas. Tente de novo em {seconds:.0f} s.")
        self.seconds = seconds


class Auth:
    def __init__(
        self,
        api_token: str,
        tokens: LoginTokens | None = None,
        password: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_token = api_token
        self._tokens = tokens
        self._password = password
        self._clock = clock
        self._failures = 0
        self._locked_until = 0.0

    @property
    def login_enabled(self) -> bool:
        return self._tokens is not None and bool(self._password)

    def check(self, token: str) -> bool:
        if compare_digest(token.encode(), self._api_token.encode()):
            return True
        return self._tokens is not None and self._tokens.is_valid(token)

    def login(self, password: str, label: str) -> str | None:
        """Devolve um token novo, ou None se a senha estiver errada."""
        if not self.login_enabled:
            raise RuntimeError("login desativado")
        now = self._clock()
        if now < self._locked_until:
            raise LoginLocked(self._locked_until - now)
        if not compare_digest(password.encode(), self._password.encode()):
            # Um bloqueio global basta: só existe um usuário, e quem erra 5 vezes não é ele.
            self._failures += 1
            if self._failures >= MAX_FAILURES:
                self._failures = 0
                self._locked_until = now + LOCK_SECONDS
            return None
        self._failures = 0
        return self._tokens.create(label)

    def logout(self, token: str) -> None:
        if self._tokens is not None:
            self._tokens.revoke(token)
