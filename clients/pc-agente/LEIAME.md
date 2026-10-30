# Agente do Biony no PC (Windows)

Deixa o Biony **saber se o PC está ligado** e **desligar o Windows direito** antes de cortar o
filtro de linha. Roda como SYSTEM desde o boot, então funciona até na tela de bloqueio.

O agente só aceita 3 comandos fixos (`status`, `desligar`, `cancelar`), exige token e só
escuta a rede do Tailscale. O Biony nunca manda comandos livres para o PC.

## Instalar

1. Abra o **PowerShell como Administrador** na pasta do projeto.
2. Rode:
   ```powershell
   powershell -ExecutionPolicy Bypass -File clients\pc-agente\instalar.ps1
   ```
3. Ele mostra duas linhas (`PC_AGENT_URL` e `PC_AGENT_TOKEN`). Cole no `.env` do **servidor**
   e rode `cd ~/biony/deploy && docker compose up -d --force-recreate`.

Para remover: `clients\pc-agente\desinstalar.ps1` (também como Administrador).
O log fica em `C:\ProgramData\Biony\agente.log`.

## Como o Biony usa

- **"Liga o PC"**: liga o filtro (a BIOS liga o PC) e avisa no Telegram quando o agente
  responder. Aí é só conectar pelo Moonlight e digitar o PIN na tela de bloqueio.
- **"Desliga o PC"**: pede confirmação, manda o Windows desligar com aviso de 30 s na tela
  (dá para cancelar com `shutdown /a`) e **só corta o filtro depois que o PC parar de
  responder**. Se ele não desligar em ~4 min, o filtro fica ligado e você é avisado.
- **"O PC tá ligado?"**: diz se está ligado e se tem alguém logado.
