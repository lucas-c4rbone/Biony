# Protocolo do Biony

Contrato entre o servidor e os clientes (terminal, PWA, ESP32). Qualquer cliente que siga
este documento funciona com qualquer servidor que o implemente.

Versão: **0.6** (texto, voz, login, PWA, agenda, ações no celular e WebSocket do totem).

## Autenticação

Todas as rotas, exceto `/health`, exigem:

    Authorization: Bearer <BIONY_API_TOKEN>

Sem token, ou com token errado: `401`.

Existem dois tipos de token:

- **Token mestre** (`BIONY_API_TOKEN` do `.env`): clientes fixos, como o terminal e o ESP32.
- **Token de login**: cada aparelho que entra na PWA com a senha ganha o seu. Pode ser revogado.

## `POST /login`

```json
{ "senha": "…", "aparelho": "celular" }
```

`200 {"token": "…"}`. Erros: `401` senha errada, `429` muitas tentativas erradas (bloqueio de
1 minuto depois de 5 erros), `503` login desativado (sem `BIONY_PASSWORD`).

## `POST /logout`

Revoga o token usado na requisição. `204`.

## `GET /sessoes/{sessao}/mensagens?limite=100`

Histórico legível da sessão (sem as chamadas de ferramenta):

```json
{ "sessao": "pwa-…", "mensagens": [ { "papel": "usuario", "texto": "oi" }, { "papel": "biony", "texto": "Opa!" } ] }
```

## Agenda: `/agenda`

Tarefas e lembretes (os mesmos que o Biony cria por conversa). Exigem o token. Prazos: `2026-11-15` (dia
inteiro) ou `2026-11-15T14:00` (horário local do servidor).

- `GET /agenda` → `{ "tarefas": [ { "id", "titulo", "prazo", "prazo_texto", "observacoes", "avisos": [ { "id", "quando", "quando_texto" } ] } ], "lembretes": [ { "id", "texto", "quando", "quando_texto" } ] }`.
  Só tarefas abertas e avisos pendentes; tarefas ordenadas por prazo (sem prazo por último).
- `POST /agenda/tarefas` `{ "titulo", "prazo"?, "observacoes"? }` → `201` com a tarefa. Com prazo, cria os avisos
  padrão (3/1/0 dias antes). `422` se o prazo for inválido ou já tiver passado.
- `POST /agenda/tarefas/{id}/concluir` → `204` (cancela os avisos da tarefa); `404` se não existir.

Apagar tarefas e criar lembretes avulsos continuam só por conversa (apagar pede confirmação).

## `GET /`

A PWA (arquivos estáticos). As rotas da API têm prioridade.

## `GET /health`

Público. `200 {"status": "ok", "voz": "pronta"}`.

`voz`: `pronta`, `carregando` (modelos sendo baixados/carregados), `desativada` ou `erro: …`.
O texto funciona desde o início; o `/voz` só depois de `pronta`.

## `POST /texto`

Requisição:

```json
{ "texto": "liga a luz", "sessao": "opcional", "capacidades": [] }
```

- `texto`: 1 a 8000 caracteres.
- `sessao`: identifica a conversa (até 128 caracteres). Se for omitida, o servidor cria uma
  e devolve o id. Mande o mesmo id nas próximas mensagens para o Biony lembrar do contexto.
  Um dispositivo fixo (ex.: o ESP32 do quarto) pode usar sempre o mesmo id.
- `capacidades`: o que ESTE cliente sabe executar (opcional, até 8 nomes). Hoje só existe
  `"acoes_celular"` (o app Android). Sem a capacidade, ferramentas que dependem do cliente recusam o
  pedido ("este canal não controla o celular") e o Biony avisa, em vez de fingir que fez.

Resposta `200`:

```json
{ "sessao": "6e1c…", "resposta": "Pronto!", "aguardando_confirmacao": false, "emocao": "feliz", "acoes": [] }
```

Erros: `401` token, `422` JSON inválido, `502` falha no LLM (`detail` explica).

`emocao` diz como o rosto deve reagir, calculado pelo que aconteceu (não pelo LLM):
`feliz` (ações deram certo), `triste` (alguma falhou), `duvida` (esperando confirmação),
`confuso` (não ouviu / se perdeu) ou `neutro`.

`acoes`: ações para o CLIENTE executar depois de mostrar a resposta (o servidor só as valida e repassa).
Só vem preenchida se o cliente declarou a capacidade. Cada ação tem `tipo`; tipos de `acoes_celular`:

| `tipo` | Campos |
| --- | --- |
| `despertador` | `hora` (0-23), `minuto` (0-59), `dias` (lista de `seg`…`dom`; vazia = só a próxima vez), `mensagem` |
| `timer` | `segundos` (1 a 86400), `mensagem` |
| `lanterna` | `ligar` (`true`/`false`) |
| `abrir_app` | `app` (nome como aparece no celular) |

O cliente deve ignorar tipos que não conhece. Não há confirmação de volta: o app executa e mostra um aviso na tela.

## `POST /voz`

`multipart/form-data`:

| Campo | Tipo | |
| --- | --- | --- |
| `audio` | arquivo | WAV, WebM, OGG, MP3… até 10 MB. Ideal: WAV 16 kHz mono |
| `sessao` | texto | opcional, igual ao `/texto` |
| `responder_com_audio` | `true`/`false` | padrão `true` |
| `capacidades` | texto | opcional, separadas por vírgula (ex.: `acoes_celular`), igual ao `/texto` |

Resposta `200`:

```json
{
  "sessao": "6e1c…",
  "transcricao": "liga a luz",
  "resposta": "Pronto, liguei!",
  "aguardando_confirmacao": false,
  "emocao": "feliz",
  "acoes": [],
  "audio_wav_base64": "UklGR…"
}
```

- `audio_wav_base64`: a resposta falada (WAV 22050 Hz mono 16 bits), ou `null` quando
  `responder_com_audio=false`.
- Se o áudio só tiver silêncio, `transcricao` vem `""` e a resposta é um pedido para repetir.
- Pela voz, o Biony responde do jeito que se fala ("vinte horas e trinta"). Pelo texto, com
  algarismos ("20:30").

Erros: `401`, `413` (áudio > 10 MB), `422` (áudio ilegível), `502` (LLM), `503` (voz desativada,
ainda carregando ou com erro; o `detail` diz qual).

## Totem: WebSocket `/ws/dispositivo`

Para clientes que ficam sempre ligados (o ESP32): áudio em tempo real nos dois sentidos.
Mensagens de controle são JSON em frames de texto; áudio vai em frames binários.

**1. Olá (autenticação).** A primeira mensagem precisa ser:

```json
{ "tipo": "ola", "token": "<token mestre ou de login>", "dispositivo": "quarto", "versao": 1 }
```

O token vai aqui, e não na URL, para não aparecer em logs. Resposta:

```json
{ "tipo": "ola_ok", "versao": 1, "sessao": "totem-quarto", "voz": "pronta",
  "microfone": { "formato": "pcm16", "taxa": 16000, "max_segundos": 30 } }
```

Token errado: `{"tipo":"erro"}` e fecha com código `4401`. Primeira mensagem que não é `ola`
(ou nada em 10 s): fecha com `4400`. O `dispositivo` vira a sessão (`totem-<nome>`), então a
conversa continua entre reconexões.

**2. Falar** (depois do wake word):

| Totem → servidor | |
| --- | --- |
| `{"tipo":"ouvir_inicio"}` | começa uma fala |
| frames binários | PCM 16 bits, mono, little-endian, **16 kHz**, mandados enquanto grava |
| `{"tipo":"ouvir_fim"}` | terminou; o servidor responde |
| `{"tipo":"cancelar"}` | descarta a fala em andamento |
| `{"tipo":"texto","texto":"…"}` | pedido por texto (a resposta vem falada) |
| `{"tipo":"ping"}` | responde `{"tipo":"pong"}` |

Fala com menos de 0,25 s é ignorada (`{"tipo":"estado","estado":"ocioso"}`); com mais de 30 s,
erro.

**3. Resposta**, nesta ordem:

```json
{ "tipo": "estado", "estado": "pensando" }
{ "tipo": "transcricao", "texto": "liga a luz" }
{ "tipo": "resposta", "texto": "Liguei!", "emocao": "feliz", "aguardando_confirmacao": false, "audio": true }
{ "tipo": "audio_inicio", "formato": "pcm16", "taxa": 22050, "bytes": 88200 }
```

seguidos de frames binários de PCM 16 bits mono na `taxa` indicada (pedaços de 4096 bytes,
prontos para o I2S) e `{"tipo":"audio_fim"}`. Se `audio` for `false`, não vem fala.
`transcricao` só existe quando o pedido foi falado.

Erros não fecham a conexão: `{"tipo":"erro","mensagem":"…","emocao":"triste"}`.

Para testar sem o ESP32: `python clients/pc/totem_sim.py`.

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

## Telegram

Não faz parte da API HTTP: o servidor conversa com o Telegram por conta própria (long polling).
Só o chat `TELEGRAM_CHAT_ID` é atendido; texto e mensagens de voz funcionam como no `/texto`,
na sessão `telegram-<chat id>`. Os lembretes também chegam por esse chat.
