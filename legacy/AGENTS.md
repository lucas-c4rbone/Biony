# Biony — Contexto e Diretrizes do Projeto

## 1. Visão do projeto

Biony é um mascote robótico de mesa criado como um projeto DIY.

A ideia principal é criar um pequeno robô-companheiro que fique na mesa do computador e permita conversar com uma IA por voz, sem precisar abrir um aplicativo manualmente.

O Biony terá personalidade própria, rosto animado e, futuramente, um corpo físico impresso em 3D.

O projeto deve começar completamente no ambiente virtual/software. O hardware será desenvolvido posteriormente com base no software já funcionando.

---

## 2. Conceito principal

O Biony não deve ser tratado simplesmente como "um ChatGPT em uma caixa".

O objetivo é criar um personagem com:

- personalidade;
- rosto expressivo;
- estados e comportamentos próprios;
- voz;
- memória;
- capacidade de executar comandos;
- integração com dispositivos e serviços;
- possibilidade de evoluir futuramente para um robô móvel.

O cubo físico será apenas o "corpo" do Biony.

O cérebro principal deverá ficar separado do corpo para permitir que o mesmo sistema seja utilizado pelo robô físico, computador e aplicativo móvel.

---

# 3. Biony 1.0

A primeira versão física será um pequeno cubo/mascote de mesa.

Por enquanto, NÃO implementar mobilidade.

### Funções planejadas

- Ativação pela palavra "Biony".
- Reconhecimento de voz.
- Conversação por voz.
- Respostas geradas por IA.
- Síntese de voz.
- Rosto digital animado.
- Diversas expressões.
- Estado de espera/ociosidade.
- Estado de sono.
- Despertar quando chamado.
- Detecção de encerramento da conversa.
- Encerramento explícito através de frases como "Obrigado, Biony".
- Retorno automático ao estado de espera após silêncio.
- Exibição de informações quando ocioso, como:
  - horário;
  - temperatura;
  - data;
  - avisos;
  - outras informações úteis.
- Sistema de anotações/memória.
- Execução de determinados comandos no computador.
- Notificações.
- Integração com a impressora 3D Creality Kobra 4 Combo, principalmente para consultar o estado da impressão.
- Possibilidade de enviar informações para serviços como Discord e e-mail.

---

# 4. Comportamento esperado

Quando o Biony estiver sem interação, ele deverá ficar em um estado de espera.

Ele pode mostrar informações no rosto/tela.

Exemplo:

    15:42
    27°C

    👀   👀

Quando estiver realmente dormindo, poderá reduzir o brilho ou apagar a tela.

---

## 5. Ativação

O usuário chama:

    "Biony"

O sistema reconhece a palavra e muda de:

    SLEEPING
        ↓
    WAKING
        ↓
    LISTENING

O Biony deverá então responder de maneira natural, por exemplo:

    "Opa, Lucas! O que você quer?"

O nome do usuário é Lucas.

---

# 6. Estados do Biony

A arquitetura deve utilizar estados bem definidos.

Estados iniciais:

- SLEEPING
- IDLE
- WAKING
- LISTENING
- THINKING
- SPEAKING

Estados adicionais podem ser criados posteriormente.

Cada estado pode controlar:

- expressão facial;
- animações;
- comportamento;
- áudio;
- transições.

Evitar criar lógica espalhada pelo projeto para controlar o estado do Biony.

Preferir uma máquina de estados ou arquitetura equivalente e clara.

---

# 7. Rosto

O rosto é uma das partes mais importantes do projeto.

O Biony deverá possuir uma tela que funciona como seu rosto.

A interface não deve parecer um aplicativo convencional cheio de menus.

O rosto deve ser o elemento principal.

Os olhos precisam ser animados e expressivos.

Expressões desejadas incluem:

- normal;
- feliz;
- triste;
- confuso;
- surpreso;
- irritado;
- pensando;
- ouvindo;
- falando;
- sonolento;
- dormindo.

Também devem existir animações como:

- piscar;
- olhar para os lados;
- acordar;
- dormir;
- mudar de expressão;
- pequenas movimentações enquanto fala.

O sistema de rosto deverá ser independente do restante do sistema sempre que possível.

Isso permitirá que o mesmo rosto seja utilizado futuramente:

- no protótipo virtual;
- no aplicativo;
- na tela LCD do robô físico.

---

# 8. Biony Core

O projeto deve separar o "Biony Core" do dispositivo físico.

O Biony Core será responsável por:

- lógica principal;
- comunicação com IA;
- memória;
- comandos;
- integrações;
- gerenciamento de tarefas;
- estado do Biony;
- comunicação com clientes.

A arquitetura planejada é aproximadamente:

                    BIONY CORE
                         │
              ┌──────────┼──────────┐
              │          │          │
              ▼          ▼          ▼
          🤖 Robô      📱 App      🖥️ PC
          físico

O robô físico não deve conter toda a inteligência do sistema.

---

# 9. Biony App

O projeto também terá um aplicativo móvel.

O aplicativo não será simplesmente um controle remoto do robô.

Ele será uma interface remota para o Biony Core.

O usuário poderá utilizar o aplicativo quando estiver fora de casa.

Funções planejadas:

- conversar com o Biony por texto;
- conversar por voz;
- adicionar comandos;
- adicionar anotações;
- consultar anotações;
- receber respostas;
- receber avisos;
- consultar informações;
- futuramente acessar funções do PC;
- futuramente consultar a impressora;
- visualizar o rosto animado do Biony durante as respostas.

O rosto exibido no aplicativo deve utilizar o mesmo conceito visual do rosto do robô físico.

---

# 10. Comandos enviados pelo aplicativo

O aplicativo poderá enviar comandos ao servidor.

O servidor deverá determinar se o comando:

1. pode ser executado imediatamente pelo servidor;
2. precisa do Biony físico;
3. precisa de outro dispositivo.

### Exemplo de comando que NÃO precisa do Biony:

    "Qual é a temperatura do meu quarto?"

O servidor pode processar e responder diretamente.

### Exemplo de comando que precisa do Biony:

    "Quando o Biony ligar, me lembra de testar a câmera."

Nesse caso, o servidor guarda a tarefa.

Quando o Biony físico ficar online, ele recebe a tarefa pendente.

---

# 11. Comandos pendentes

O servidor deverá possuir um sistema de tarefas/comandos pendentes.

Exemplo:

    ID: 123
    Tipo: BIONY_REQUIRED
    Comando: Lembrar Lucas de testar a câmera.
    Estado: PENDING

Quando o Biony físico conectar:

    PENDING
       ↓
    ENTREGUE
       ↓
    CONCLUÍDO

Esse sistema será importante para permitir que o usuário interaja com o Biony mesmo quando o robô estiver desligado.

---

# 12. Dependência do Biony físico

O Biony físico ficará conectado ao computador.

Se o computador estiver desligado, o Biony físico também estará desligado.

Por isso:

- o Biony físico não deve ser requisito para todas as funções;
- o servidor deve continuar funcionando independentemente do robô;
- comandos que não dependem do corpo físico devem funcionar sem ele;
- comandos que dependem do hardware devem poder ficar pendentes.

---

# 13. Integração com o computador

O Biony deverá futuramente executar determinadas ações no computador.

Exemplos:

    "Biony, abre o Discord."

    "Biony, abre o VS Code."

    "Biony, abre o Steam."

    "Biony, tira um print."

    "Biony, anota isso."

Ações potencialmente perigosas devem exigir confirmação.

Exemplo:

    Usuário:
    "Apaga essa pasta."

    Biony:
    "Você tem certeza que quer apagar essa pasta?"

Somente após confirmação a ação deve ser executada.

Nunca permitir que uma interpretação ambígua execute automaticamente uma ação destrutiva.

---

# 14. Anotações e memória

O Biony deverá possuir um sistema de memória/anotações.

Exemplo:

    "Biony, anota que preciso comprar filamento preto."

O sistema salva:

    comprar filamento preto

Posteriormente:

    "Biony, o que eu tinha para comprar?"

O Biony recupera a informação.

O sistema de memória deve ser separado da lógica de conversa sempre que possível.

---

# 15. Impressora 3D

Está planejada integração com uma Creality Kobra 4 Combo.

Exemplos:

    "Biony, quanto falta para terminar a impressão?"

Resposta esperada:

    "Aproximadamente 2 horas e 20 minutos."

Outras informações futuras:

- porcentagem da impressão;
- tempo restante;
- nome do arquivo;
- estado da impressão;
- material;
- temperatura;
- impressão concluída.

Comandos de controle da impressora poderão existir futuramente.

Comandos destrutivos, como cancelar uma impressão, deverão exigir confirmação.

---

# 16. Discord e e-mail

O Biony poderá futuramente enviar informações para serviços externos.

Exemplos:

    "Biony, manda essa resposta para o meu Discord."

    "Biony, manda essa anotação para o meu e-mail."

As integrações devem ficar dentro de módulos próprios.

Não colocar lógica específica de Discord ou e-mail dentro do núcleo principal do Biony.

---

# 17. Arquitetura do código

Priorizar arquitetura modular.

Estrutura inicial sugerida:

    Biony/
    │
    ├── AGENTS.md
    ├── README.md
    │
    ├── app/
    ├── face/
    ├── core/
    ├── audio/
    ├── integrations/
    ├── assets/
    ├── config/
    └── tests/

Essa estrutura pode ser alterada se houver uma razão técnica clara.

Não criar arquivos ou módulos apenas por criar.

---

# 18. Desenvolvimento inicial

O projeto será desenvolvido primeiro como software.

NÃO começar pelo hardware.

A primeira etapa é criar um Biony virtual funcional.

Primeiro objetivo:

    abrir o programa
        ↓
    mostrar o rosto do Biony
        ↓
    animar os olhos
        ↓
    controlar os estados
        ↓
    simular interação

Inicialmente não é necessário:

- microfone;
- IA;
- câmera;
- hardware;
- Kobra;
- Discord;
- e-mail.

Esses componentes serão adicionados gradualmente.

---

# 19. Primeiro protótipo visual

O primeiro protótipo deverá possuir:

- janela dedicada ao Biony;
- rosto ocupando a maior parte da interface;
- dois olhos;
- animações;
- estados;
- relógio/informação ambiente;
- modo dormindo;
- modo acordando;
- modo ouvindo;
- modo pensando;
- modo falando.

Para testes iniciais, os estados podem ser acionados pelo teclado.

Exemplo:

    S → SLEEPING
    B → WAKING
    L → LISTENING
    T → THINKING
    P → SPEAKING

Isso permite testar o rosto antes de implementar áudio e IA.

---

# 20. Tecnologia inicial

A linguagem inicial do protótipo será:

    Python

Interface gráfica inicial:

    PySide6

O projeto deve permanecer simples e fácil de modificar.

Tecnologias adicionais só devem ser adicionadas quando houver necessidade real.

---

# 21. Princípios de desenvolvimento

1. Não implementar funcionalidades que não foram solicitadas.

2. Não transformar o projeto em uma arquitetura excessivamente complexa sem necessidade.

3. Priorizar código legível.

4. Priorizar módulos independentes.

5. Evitar dependências desnecessárias.

6. Não colocar toda a lógica em um único arquivo.

7. Criar testes para partes importantes quando fizer sentido.

8. Não esconder erros silenciosamente.

9. Explicar mudanças arquiteturais importantes antes de realizá-las.

10. Fazer mudanças incrementais.

11. Preservar a possibilidade de substituir o protótipo virtual por hardware posteriormente.

12. O rosto do Biony deve permanecer independente do hardware.

13. O Biony Core deve permanecer independente do dispositivo que está usando.

14. Nunca assumir que o Biony físico está disponível.

15. Segurança deve ser considerada para comandos que alteram ou apagam dados.

---

# 22. Futuro do projeto

O Biony 1.0 será apenas o começo.

Possíveis versões futuras:

### Biony 1.0
Cubo de mesa parado.

### Biony 1.x
Câmera e visão computacional.

### Biony 2.0
Mobilidade com rodas.

### Biony 3.0
Base de carregamento automático.

### Biony 4.0+
Braços, sensores adicionais e comportamentos autônomos.

Essas versões futuras não devem complicar desnecessariamente o desenvolvimento do Biony 1.0.

---

# 23. Regra principal

O objetivo não é construir tudo rapidamente.

O objetivo é construir uma base que permita transformar o Biony gradualmente de:

    SOFTWARE
       ↓
    PERSONAGEM
       ↓
    ASSISTENTE
       ↓
    DISPOSITIVO
       ↓
    ROBÔ

Cada etapa deve funcionar antes de adicionar complexidade à próxima.