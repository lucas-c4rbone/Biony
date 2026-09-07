# Biony

Protótipo visual do mascote Biony, construído em Python e PySide6.

Além dos estados visuais, o protótipo inclui uma conversa textual simulada e local.

## Executar

```powershell
python -m pip install -e .
python -m app.main
```

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
