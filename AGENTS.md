# Biony — guia para agentes

Biony é o assistente pessoal do Lucas: controla o quarto (Home Assistant), guarda lembretes e
memória, responde dúvidas, e funciona por voz ou texto em todas as interfaces. Ele roda num
servidor Debian com Docker e é acessado de fora de casa via Tailscale.

A versão anterior (feita como teste) está em `legacy/`: serve só de consulta. Não
importe nada dela.

## Stack

- Servidor: Python 3.12, FastAPI, SQLite. Container Docker no Debian (8 GB RAM, CPU AMD
  antiga, **sem GPU**). O Home Assistant roda em outro container.
- LLM: API no formato OpenAI (OpenRouter), com tool calling. O modelo é definido no `.env`.
- STT: faster-whisper local (CPU, int8) · TTS: Piper local, voz PT-BR.
- Agendador: APScheduler. A tabela de lembretes é a fonte da verdade; os jobs são
  recriados a partir dela.
- Notificações: Telegram.
- Clientes: terminal (testes de voz), PWA (celular e PC), ESP32-S3 (depois).
- **Rosto/expressões: fora do escopo por enquanto.**

## Estrutura

    protocol/PROTOCOL.md    contrato HTTP/WS com os clientes; mantenha-o atualizado
    server/biony/core/      domínio: conversa, ferramentas, permissões. Sem FastAPI/HTTP/SQL
    server/biony/adapters/  implementações das portas (LLM, SQLite, ...)
    server/biony/api/       rotas FastAPI, login e bot do Telegram; só traduzem ↔ core
    server/biony/web/       PWA (HTML/CSS/JS puro, sem build), servida em /
    server/biony/main.py    composição: o único lugar que liga tudo
    server/tests/           pytest; LLM e ferramentas falsos ficam em conftest.py
    config/casa.toml        aparelhos e rotinas da casa (montado em /config no Docker)
    clients/pc/             cliente de terminal (voz e texto) para o PC
    deploy/                 docker-compose
    legacy/                 versão antiga, só leitura

## Regras

1. `core/` depende apenas de `core/`. Integrações entram como `Tool` (em
   `server/biony/tools/`) ou como adaptador de uma porta em `core/ports.py`.
2. Toda ação que apaga, desliga ou altera algo de forma difícil de desfazer usa
   `requires_confirmation=True`. Nunca execute uma ação destrutiva a partir de uma
   resposta ambígua (`core/confirmation.py`: o "sim" só vale em respostas feitas apenas de
   palavras de confirmação; "pode ligar a luz" é um pedido novo, não um sim).
3. Comandos no servidor: só por uma whitelist de nomes, nunca com uma string de shell
   montada pelo LLM, sempre por um usuário não-root e sempre com log.
4. Erros não são engolidos: ou viram `ToolResult(ok=False, ...)` (o LLM conta ao
   usuário), ou propagam com log.
5. Segredos ficam só no `.env` (ignorado pelo Git). Novas variáveis vão para o
   `.env.example` e para `config.py`.
6. Mudanças no banco: acrescente uma migração no fim de `_MIGRATIONS`; nunca edite uma
   que já foi aplicada.
7. Mudou a API? Atualize `protocol/PROTOCOL.md`.
8. Não puxe funcionalidades de fases futuras. Faça mudanças incrementais com testes.

## Fases

1. **F1** base do servidor (`/texto`, histórico, SQLite, Docker) ✅
2. **F2** Home Assistant: ferramentas e rotinas ✅ (`config/casa.toml` é a lista de permissão;
   rotinas ficam no Biony; suporta IR de botão único com estado presumido)
3. **F3** voz: faster-whisper, Piper, `/voz`, cliente de terminal (`clients/pc`) ✅
   (pin `av<19`: o faster-whisper 1.2 quebra com o PyAV 19)
4. **F4** lembretes, tarefas e memória + APScheduler + Telegram ✅
   (avisos padrão 3/1/0 dias antes às 9h; silêncio 22:30–07:00 só para avisos automáticos;
   o bot do Telegram só atende TELEGRAM_CHAT_ID; logs do httpx ficam em WARNING porque a URL
   da Bot API contém o token)
5. **F5** PWA + login + Tailscale ✅ (PWA em `server/biony/web/`, servida pelo próprio servidor;
   HTTPS via `tailscale serve`; WebSocket adiado para a F7, quando o ESP32 precisar de áudio em tempo real)
6. **F6** comandos no servidor (whitelist, usuário restrito por SSH)
7. **F7** ESP32-S3 + WebSocket (wake word do colega: `keyword_spotting_int8.tflite`, fora do Git)

## Comandos

    cd server && pip install -e ".[voz,dev]"   # instalar (sem voz: ".[dev]" e VOICE_ENABLED=false)
    cd server && pytest                     # testes
    cd server && uvicorn biony.main:app --reload --port 8000
    cd deploy && docker compose up -d --build
