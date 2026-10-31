# Biony para Android

O Biony no celular: a PWA do servidor dentro de um app, mais o que a PWA sozinha não consegue:

- **Ações no celular** por voz ou texto: despertador, timer, lanterna e abrir app.
- **Abrir já ouvindo**: atalho no ícone, ladrilho no painel rápido e atalho fixo nas notificações.
- Conversa, agenda e login são os da própria PWA (nada é duplicado no app).
- **Conversa contínua por voz**: toque no microfone, fale e faça uma pausa; ele envia, responde e volta a ouvir. Toque de novo para encerrar.
  Isso vem da PWA (servidor), então atualizar o servidor basta; não precisa de APK novo.

O servidor só valida o pedido e o devolve em `acoes` (ver `protocol/PROTOCOL.md`); quem executa é o app.
Por isso "põe um despertador" só funciona falando pelo app: no Telegram ou no PC o Biony avisa que não dá.

## Compilar

Precisa do Android Studio (traz o JDK 21 e o SDK). No PowerShell, na pasta `clients/android`:

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat :app:assembleDebug
```

O APK sai em `app/build/outputs/apk/debug/app-debug.apk` (assinado com a chave de debug, só para uso próprio).

## Instalar no celular

1. Passe o `app-debug.apk` para o celular (Telegram, cabo, Drive...).
2. Abra o arquivo e permita "instalar apps desconhecidos" para o app que o abriu.
3. Na primeira abertura, digite o endereço **HTTPS** do Biony (o do `tailscale serve`) e toque em **Salvar e abrir**.
   O Tailscale precisa estar ligado no celular.
4. Entre com a senha, como na PWA, e libere o microfone.

Para atualizar, instale o APK novo por cima (precisa ser assinado pela mesma chave, ou seja, compilado neste PC).

## Testar sem o servidor

Em **⚙️ → Testes**: timer de 10 s, despertador daqui a 2 minutos (apague depois no Relógio) e lanterna por 3 s.
Se algum falhar aqui, o problema é do celular, não do servidor.

## POCO / Xiaomi: para o app não ser fechado

- Configurações → Apps → Biony → **Início automático** ligado.
- Bateria do app → **Sem restrições**.
- Na tela de apps recentes, segure o card do Biony e toque no **cadeado**.

## Limites desta versão

- Cria despertador e timer, mas **não lista nem apaga** os que já existem (o Android não deixa de forma confiável).
- Não dá para saber se o Relógio aceitou: o app mostra um aviso "enviado ao Relógio" e pronto.
- A lanterna pode apagar sozinha se o Android encerrar o app. Se acontecer, me avise.
- Ainda **não** vira o assistente do botão power (etapa C).
