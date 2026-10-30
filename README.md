# Biony

Assistente pessoal por voz e texto: controla o quarto pelo Home Assistant, guarda lembretes
e memória, e responde dúvidas. Funciona pelo terminal, pela PWA e, no futuro, por um ESP32.

**Estado atual: F3.** Conversa por texto (`/texto`) ou voz (`/voz`), com histórico salvo e controle
do quarto pelo Home Assistant. Aparelhos e rotinas ficam em [config/casa.toml](config/casa.toml). Veja o
[protocolo](protocol/PROTOCOL.md) e as fases no [AGENTS.md](AGENTS.md).

## Configurar

```bash
cp .env.example .env    # preencha LLM_API_KEY e BIONY_API_TOKEN
```

## Rodar no servidor (Docker)

```bash
cd deploy
docker compose up -d --build
```

O Biony fica na porta **8420** do servidor (para trocar: `BIONY_PORT=9000 docker compose up -d`).
O banco fica no volume `biony-data`. Para ver os logs: `docker compose logs -f biony`.

## Rodar no PC (desenvolvimento)

```bash
cd server
pip install -e ".[voz,dev]"
pytest
uvicorn biony.main:app --reload --port 8000
```

## Testar

```bash
curl -X POST http://localhost:8000/texto \
  -H "Authorization: Bearer SEU_TOKEN" -H "Content-Type: application/json" \
  -d '{"texto": "Oi Biony!"}'
```

Copie o `sessao` da resposta e mande-o nas próximas mensagens para continuar a mesma conversa.

## Falar com o Biony pelo PC

```bash
pip install -r clients/pc/requirements.txt
python clients/pc/biony_voz.py
```

Precisa de `BIONY_URL` (ex.: `http://IP_TAILSCALE:8420`) e `BIONY_API_TOKEN` no `.env` da raiz.
Aperte Enter para começar a gravar e Enter de novo para enviar, ou digite para mandar texto.
