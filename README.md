# Biony

Protótipo visual do mascote Biony, construído em Python e PySide6.

Além dos estados visuais, o protótipo inclui uma conversa textual simulada e local.

## Executar

```powershell
python -m pip install -e .
python -m app.main
```

## OpenAI e Áudio (opcional)

Para usar `OpenAIBrain` e os adaptadores de áudio reais:
- `OPENAI_API_KEY`: Chave da API OpenAI.
- `OPENAI_MODEL`: Modelo do Brain (padrão `gpt-4.1-mini`).
- `OPENAI_TIMEOUT`: Timeout da API em segundos (padrão `30.0`).
- `OPENWAKEWORD_MODEL_PATH`: Caminho do arquivo de modelo do openWakeWord (.onnx / .tflite).
- `OPENWAKEWORD_THRESHOLD`: Limiar de detecção da palavra de ativação (padrão `0.5`).
- `OPENAI_STT_MODEL`: Modelo de transcrição STT (padrão `gpt-4o-mini-transcribe`).
- `OPENAI_TTS_MODEL`: Modelo de síntese TTS (padrão `gpt-4o-mini-tts`).
- `OPENAI_TTS_VOICE`: Voz do TTS (padrão `alloy`).

## API Local

A API local é criada com `core.api.create_app`, recebendo um `BionyCore` e um
`LocalDeviceAuthenticator` configurado por uma credencial local fornecida no
processo. Ela expõe `/health`, `/devices/register`, `/messages`, sessões e o
WebSocket autenticado `/ws`.

## Estados de teste

| Tecla | Estado |
| --- | --- |
| `S` | Dormindo |
| `B` | Acordando |
| `L` | Ouvindo |
| `T` | Pensando |
| `P` | Falando |
| `I` | Ocioso |

Digite uma mensagem na faixa inferior e pressione `Enter`. O Biony passará por
`LISTENING`, `THINKING`, `SPEAKING` e, então, voltará para `IDLE`.
