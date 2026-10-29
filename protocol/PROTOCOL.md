# Protocolo do Biony

Contrato entre o servidor e os clientes (terminal, PWA, ESP32). Qualquer cliente que siga
este documento funciona com qualquer servidor que o implemente.

Versão: **0.1** (F1 — só texto). Voz e WebSocket entram nas próximas fases.

## Autenticação

Todas as rotas, exceto `/health`, exigem:

    Authorization: Bearer <BIONY_API_TOKEN>

Sem token, ou com token errado: `401`.

## `GET /health`

Público. `200 {"status": "ok"}`.

## `POST /texto`

Requisição:

```json
{ "texto": "liga a luz", "sessao": "opcional" }
```

- `texto`: 1 a 8000 caracteres.
- `sessao`: identifica a conversa (até 128 caracteres). Se for omitida, o servidor cria uma
  e devolve o id. Mande o mesmo id nas próximas mensagens para o Biony lembrar do contexto.
  Um dispositivo fixo (ex.: o ESP32 do quarto) pode usar sempre o mesmo id.

Resposta `200`:

```json
{ "sessao": "6e1c…", "resposta": "Pronto!", "aguardando_confirmacao": false }
```

Erros: `401` token, `422` JSON inválido, `502` falha no LLM (`detail` explica).

## Confirmação de ações perigosas

Quando o Biony quer executar uma ação marcada como perigosa, ele **não executa**. Ele
responde com `aguardando_confirmacao: true` e uma pergunta ("Vou desligar o PC. Confirma?").

A próxima mensagem da mesma sessão é a resposta:

| Mensagem | Efeito |
| --- | --- |
| contém "sim", "pode", "confirmo"… (e nenhum "não") | executa |
| contém "não", "cancela", "deixa pra lá"… | cancela |
| qualquer outra coisa | cancela e trata a mensagem como um pedido novo |

Um "sim" que chega depois de a ação ter sido cancelada não executa nada.
