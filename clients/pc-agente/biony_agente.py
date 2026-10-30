"""Agente do Biony no PC (Windows).

Roda como SYSTEM desde o boot (antes do login), para o Biony saber se o PC está ligado e
conseguir desligá-lo direito mesmo na tela de bloqueio. Só aceita comandos de uma lista fixa:

    GET  /status    → {"online": true, "usuario_logado": bool}
    POST /desligar  → {"segundos": 30}  desliga o Windows com aviso na tela
    POST /cancelar  → cancela um desligamento agendado

Todo pedido precisa de "Authorization: Bearer <token>" (o token fica em agente.json).
Só depende da biblioteca padrão do Python. Instale com instalar.ps1.
"""

from __future__ import annotations

from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import subprocess

HOME = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Biony"
CONFIG = HOME / "agente.json"
LOG = HOME / "agente.log"
MAX_BODY = 1024
MIN_SECONDS, MAX_SECONDS = 10, 300
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

log = logging.getLogger("biony-agente")


def run(*command: str) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, creationflags=NO_WINDOW, timeout=15)


def user_logged_in() -> bool:
    # "query user" lista as sessões de usuário; sem ninguém logado, retorna erro.
    try:
        return run("query", "user").returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "BionyAgente/1"
    token = ""

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path == "/status":
            self._reply(200, {"online": True, "usuario_logado": user_logged_in()})
        else:
            self._reply(404, {"erro": "caminho desconhecido"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        body = self._body()
        if body is None:
            return
        if self.path == "/desligar":
            seconds = body.get("segundos", 30)
            if not isinstance(seconds, int) or not MIN_SECONDS <= seconds <= MAX_SECONDS:
                self._reply(400, {"erro": f"segundos precisa ser inteiro de {MIN_SECONDS} a {MAX_SECONDS}"})
                return
            message = f"O Biony vai desligar o PC em {seconds} segundos. Para cancelar: shutdown /a"
            result = run("shutdown", "/s", "/t", str(seconds), "/c", message)
            log.info("Desligar em %d s pedido por %s (código %d)", seconds, self.client_address[0], result.returncode)
            if result.returncode != 0:
                self._reply(500, {"erro": (result.stderr or result.stdout).strip() or "shutdown falhou"})
                return
            self._reply(200, {"ok": True, "segundos": seconds})
        elif self.path == "/cancelar":
            result = run("shutdown", "/a")
            log.info("Cancelar desligamento pedido por %s (código %d)", self.client_address[0], result.returncode)
            self._reply(200, {"ok": result.returncode == 0})
        else:
            self._reply(404, {"erro": "caminho desconhecido"})

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer ") and compare_digest(header[7:].encode(), self.token.encode()):
            return True
        log.warning("Pedido recusado (token inválido) de %s", self.client_address[0])
        self._reply(401, {"erro": "token inválido"})
        return False

    def _body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._reply(413, {"erro": "corpo grande demais"})
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._reply(400, {"erro": "JSON inválido"})
            return None
        if not isinstance(data, dict):
            self._reply(400, {"erro": "esperava um objeto JSON"})
            return None
        return data

    def _reply(self, status: int, data: dict) -> None:
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # silencia o log padrão por requisição
        pass


def main() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if len(config.get("token", "")) < 24:
        raise SystemExit("agente.json precisa de um token com pelo menos 24 caracteres")
    Handler.token = config["token"]
    port = int(config.get("porta", 8421))
    log.info("Agente do Biony ouvindo na porta %d", port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
