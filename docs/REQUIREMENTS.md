# Requisitos oficiais — Biony 1.0

> Este documento consolida os requisitos definidos para o Biony 1.0. Itens marcados como **Confirmado** são decisões do projeto; itens marcados como **Em aberto** ainda exigem decisão posterior. Ausência de detalhe não deve ser interpretada como autorização para escolher ou implementar uma solução.

## 1. Visão geral e objetivo

**Confirmado**

- Biony é um mascote robótico de mesa, inicialmente desenvolvido como software e evoluído para um dispositivo físico.
- O objetivo é criar um personagem/assistente com rosto expressivo, voz, memória, estados próprios e capacidade de integração gradual.
- Biony 1.0 é um cubo ou mascote de mesa estacionário. Mobilidade não faz parte desta versão.
- O Biony físico é um cliente/terminal. O Biony Core é o cérebro central e não deve ficar acoplado ao corpo físico.
- O sistema deve evoluir de software para personagem, assistente, dispositivo e robô em etapas funcionais.

**Em aberto**

- Dimensões, materiais, aparência externa final e processo de fabricação do corpo.
- Cronograma, critérios de aceite e versão de lançamento do Biony 1.0.

## 2. Corpo físico

**Confirmado**

- O primeiro corpo físico será um pequeno cubo/mascote de mesa.
- Não haverá mobilidade no Biony 1.0.
- O corpo exibirá o rosto digital e atuará como terminal do Biony Core.

**Em aberto**

- Modelo de processador/controlador local, sensores, câmeras e demais componentes físicos.
- Conexões físicas internas, gabinete, impressão 3D e montagem.

## 3. Display e rosto

**Confirmado**

- O display funciona como o rosto e deve ser o elemento visual principal, sem aparência de aplicativo convencional cheio de menus.
- O rosto precisa ser independente do restante do sistema para poder ser reutilizado no protótipo virtual, aplicativo móvel e display do robô físico.
- A direção visual atual é uma pequena tela preta/escura com olhos em pixel art ciano/azul-claro, renderizados por código em uma grade lógica escalável.
- Não usar imagens externas, sprites ou olhos realistas para o rosto.
- O rosto deve ser expressivo por deformação, posição, tamanho, abertura e movimento de blocos/pixels.

**Em aberto**

- Tecnologia, tamanho, resolução e interface elétrica do display físico.
- Resolução lógica definitiva para o display físico.

## 4. Controlador local e Wi-Fi

**Confirmado**

- O Biony físico terá um controlador local e comunicação por Wi-Fi.
- O controlador local é cliente do Biony Core: exibe o rosto, participa da interação local e recebe/executa tarefas destinadas ao corpo quando estiver online.
- O desktop não é requisito para o Biony físico funcionar. O corpo físico depende do Biony Core executando no servidor, não de um computador desktop local.

**Em aberto**

- Modelo do controlador local.
- Protocolo de comunicação, autenticação, descoberta de dispositivos, formato de mensagens e estratégia de reconexão.

## 5. Alimentação

**Confirmado**

- O Biony físico será alimentado por uma fonte USB-C independente.

**Em aberto**

- Potência da fonte, bateria (se houver), circuito de carga, consumo estimado e comportamento em falta de energia.

## 6. Áudio

**Confirmado**

- O Biony terá interação por voz, incluindo captura de voz, geração de respostas por IA e reprodução de fala.
- A arquitetura deverá prever microfone, speaker, amplificador e controle de volume por potenciômetro.
- Ruído ambiente e eco são preocupações funcionais que devem ser tratados antes de considerar a conversa por voz pronta.

**Em aberto**

- Modelos de microfone, speaker, amplificador e potenciômetro.
- Tecnologias específicas de STT, TTS, redução de ruído, cancelamento de eco e processamento de áudio.
- Posicionamento físico dos componentes e critérios mensuráveis de qualidade de áudio.

## 7. Wake word e fluxo de voz

**Confirmado**

- A palavra de ativação é “Biony”.
- O fluxo inicial previsto é `SLEEPING → WAKING → LISTENING` quando o Biony for chamado.
- O Biony deve detectar o encerramento da conversa, incluindo frases explícitas como “Obrigado, Biony”, e retornar ao estado apropriado após silêncio.

**Em aberto**

- Motor de wake word, STT e TTS.
- Duração do silêncio, frases completas de encerramento, limiares de confiança e tratamento de falsos positivos.

## 8. Estados do Biony

**Confirmado**

Estados iniciais oficiais:

- `SLEEPING`
- `IDLE`
- `WAKING`
- `LISTENING`
- `THINKING`
- `SPEAKING`

Cada estado pode controlar expressão facial, animações, comportamento, áudio e transições. A lógica de estados deve permanecer centralizada em uma máquina de estados ou arquitetura equivalente clara.

**Em aberto**

- Estados adicionais e regras completas de transição quando áudio, ferramentas e hardware forem implementados.

## 9. Expressões e animações

**Confirmado**

O sistema visual deve suportar, no mínimo:

- `NORMAL`, `HAPPY`, `CURIOUS`, `THINKING`, `SURPRISED`, `CONFUSED`, `SLEEPING`, `LISTENING`, `SPEAKING` e `WAKING`.
- Piscar automático com fechamento e abertura reais.
- Flutuação/movimento sutil para que os olhos pareçam vivos.
- Olhar para os lados, para cima e para baixo; abrir, fechar, ampliar, reduzir, aproximar, separar, inclinar e deformar os olhos em pixels.

### Lista oficial de animações comuns

- Piscar.
- Flutuação sutil.
- Olhar para os lados.
- Acordar e dormir.
- Mudança suave de expressão.
- Pequenas movimentações durante a fala.
- Equalizador/ondas em pixel art durante `SPEAKING`.
- Indicador discreto de atenção durante `LISTENING`.
- Olhar elevado/deslocado e mudança sutil de formato durante `THINKING`.

### Animações especiais e easter eggs

**Em aberto**

- Não há animações especiais ou easter eggs oficialmente definidos nesta etapa. Eles não devem ser inventados ou implementados sem uma especificação posterior.

## 10. Idle, sono e carrossel de informações

**Confirmado**

- Sem interação, Biony permanece em `IDLE` e pode exibir informações úteis no rosto/display.
- Em sono real, o display poderá reduzir brilho ou apagar.
- O conteúdo de idle inclui horário, data, avisos e outras informações úteis.
- O clima exibido será temperatura e umidade de Aragarças-GO, obtidas pela internet.
- Biony 1.0 não terá sensor físico de temperatura.

**Em aberto**

- Ordem, duração, transições e conteúdo completo do carrossel de informações.
- Serviço de clima, frequência de atualização, comportamento sem internet e regras de apresentação de avisos.
- Critérios que diferenciam `IDLE` de `SLEEPING` e política de brilho/apagamento.

## 11. Memória permanente

**Confirmado**

- Biony terá sistema de anotações/memória separado da lógica de conversa sempre que possível.
- Memória permanente só pode ser criada quando o usuário pedir explicitamente para guardar algo.
- O usuário deve poder consultar posteriormente as informações guardadas, por exemplo anotações de compras.

**Em aberto**

- Banco de dados, formato dos registros, retenção, edição, exclusão, busca, backup e privacidade.
- Linguagem exata de confirmação para salvar, alterar ou apagar memórias.

## 12. Biony Core e LLM online

**Confirmado**

- O Biony Core é o cérebro central: gerencia lógica principal, estados, memória, comunicação com IA, ferramentas, integrações, tarefas e comunicação com clientes.
- O Core deve continuar funcional independentemente do Biony físico.
- A LLM online será acessada pela OpenAI API.
- O Biony físico, aplicativo móvel e outros clientes devem se comunicar com o Core, não carregar toda a inteligência localmente.

**Em aberto**

- Modelo específico da OpenAI, prompts, gestão de chaves, limites de custo, contexto, privacidade e política de falhas da API.
- Local de hospedagem, banco de dados, autenticação, observabilidade e estratégia de disponibilidade do Core.

## 13. Aplicativo móvel

**Confirmado**

- O aplicativo móvel é uma interface remota para o Biony Core, não apenas um controle remoto do robô.
- Funções planejadas: conversa por texto e voz, anotações, comandos, consulta de informações, avisos, respostas e visualização do rosto animado.
- O aplicativo deve permitir interação mesmo quando o corpo físico não estiver disponível.

**Em aberto**

- Plataforma, tecnologia, telas, autenticação, notificações, distribuição e escopo inicial do aplicativo.

## 14. Ferramentas do PC e permissões

**Confirmado**

- Futuramente Biony poderá executar determinadas ações no computador, como abrir aplicativos, capturar tela e criar anotações.
- Ações destrutivas ou potencialmente perigosas exigem confirmação explícita.
- Uma interpretação ambígua nunca pode executar automaticamente uma ação destrutiva.

**Em aberto**

- Lista oficial de ferramentas, permissões por ferramenta/dispositivo/usuário, interface de confirmação, auditoria e revogação de permissões.

## 15. Integração com Kobra 4

**Confirmado**

- Há integração planejada com a impressora Creality Kobra 4 Combo.
- Consultas previstas incluem porcentagem, tempo restante, arquivo, estado, material, temperaturas e conclusão da impressão.
- Cancelar impressão e outros comandos destrutivos exigirão confirmação.

**Em aberto**

- Método de integração, capacidades realmente disponíveis, autenticação, comandos suportados e comportamento quando a impressora estiver offline.

## 16. Notificações e integrações externas

**Confirmado**

- Biony deverá emitir notificações para PC e celular.
- Integrações futuras podem incluir Discord e e-mail, mantidas em módulos próprios e fora do núcleo principal.

**Em aberto**

- Canais, prioridades, preferências do usuário, regras de silêncio, formato e entrega de notificações.
- Implementação e credenciais de Discord, e-mail e demais integrações.

## 17. Comandos pendentes e indisponibilidade

**Confirmado**

- O Core deve classificar um comando: executável imediatamente, dependente do Biony físico ou dependente de outro dispositivo.
- Comandos que requerem o Biony físico podem ficar pendentes enquanto ele estiver offline.
- Fluxo previsto de tarefa do corpo: `PENDING → ENTREGUE → CONCLUÍDO`.
- Funções que não exigem o corpo físico devem continuar disponíveis pelo Core e pelo aplicativo.
- Se o Core estiver offline, clientes não devem presumir que comandos, memória, IA ou integrações foram processados.

**Em aberto**

- Persistência, reenvio, expiração, deduplicação e recuperação de comandos pendentes.
- Mensagens e experiência de usuário quando o Core, o corpo físico, internet, PC ou dispositivos integrados estiverem indisponíveis.

## 18. Arquitetura e responsabilidades

**Confirmado**

| Componente | Responsabilidade |
| --- | --- |
| Biony Core | Cérebro central: estados, IA, memória, tarefas, ferramentas, integrações e comunicação com clientes. |
| Biony físico | Cliente/terminal Wi-Fi com display, áudio e controlador local; não é requisito para o Core funcionar. |
| Aplicativo móvel | Cliente remoto para conversar, consultar informações, registrar anotações e receber avisos. |
| Cliente de PC | Futuro executor de ferramentas autorizadas e origem/destino de notificações. |
| Face | Sistema visual independente do hardware e da lógica de IA, reutilizável em display físico, software e app. |
| Áudio | Camada separada para entrada, saída e processamento de voz. |
| Integrações | Módulos independentes para impressora, Discord, e-mail e futuros serviços. |

**Em aberto**

- Interfaces públicas entre componentes, protocolo de rede, modelos de dados, mecanismo de autenticação e implantação.

## 19. Arquitetura do Biony Core

**Confirmado**

- O Biony Core é o cérebro central do sistema. Ele orquestra conversas, estados, memória, ferramentas, dispositivos, áudio, clima, notificações e a comunicação com clientes.
- O Core deve permanecer independente de PySide6, do display, de um protocolo de comunicação específico e de detalhes de hardware.
- O Biony físico, o aplicativo móvel, o cliente de PC e a integração da Kobra 4 são clientes ou adaptadores do Core; eles não carregam a lógica central do Biony.
- A `StateMachine` é parte do Core e permanece independente de PySide6. Clientes recebem eventos de estado e decidem como representá-los visualmente ou fisicamente.
- `SimulatedBrain` deve ser preservado como implementação local de desenvolvimento.
- `Brain` é uma porta substituível: serviços de conversa dependem da interface do Brain, não de um provedor específico de IA.
- A OpenAI API será um adaptador futuro para a porta `Brain`; o modelo da OpenAI continua em aberto.
- A memória permanente é controlada exclusivamente pelo Core. Um Brain pode sugerir memória, mas não pode gravá-la diretamente. O Core só cria memória quando há solicitação explícita do usuário.
- Ferramentas são explícitas, registradas e limitadas por contrato. Cada ferramenta deve declarar argumentos validados, destino, risco e se exige confirmação.
- Nenhuma ferramenta, Brain ou cliente recebe acesso arbitrário ao terminal, shell, sistema de arquivos ou dispositivos.
- O Core deve controlar tarefas pendentes para clientes/dispositivos indisponíveis e publicar eventos quando seu estado mudar.

### Camadas e responsabilidades

```text
Clientes e dispositivos
    ↓
Adaptadores de API/comunicação
    ↓
Biony Core: serviços de aplicação e orquestração
    ├── State
    ├── Conversation / Brain
    ├── Memory
    ├── Tools + Permissions
    ├── Devices + tarefas pendentes
    ├── Audio orchestration
    ├── Weather
    └── Notifications
    ↓
Portas (interfaces) e adaptadores concretos
```

### Portas principais

| Porta | Responsabilidade |
| --- | --- |
| `Brain` | Produzir uma resposta ou proposta de ação a partir da conversa. |
| `Memory` | Salvar e consultar memórias explicitamente autorizadas pelo usuário. |
| `State` | Controlar o estado e publicar transições. |
| `Tools` | Descrever e executar capacidades permitidas e validadas. |
| `Devices` | Registrar clientes/dispositivos, capacidades, disponibilidade e tarefas pendentes. |
| `Audio` | Orquestrar eventos de voz, wake word, entrada e saída de áudio entre clientes e serviços. |
| `Notifications` | Entregar avisos aos canais autorizados. |
| `Weather` | Consultar temperatura e umidade online para Aragarças-GO. |
| `API/comunicação` | Traduzir comandos de clientes em chamadas do Core e publicar eventos de retorno. |

### Áudio

**Confirmado**

- O Core orquestra o fluxo de áudio e os estados associados, como ativação, escuta, processamento e fala.
- STT e TTS são serviços/adaptadores substituíveis conectados à camada de áudio; não fazem parte da lógica central do Core.

**Em aberto**

- Implementações específicas de STT, TTS, wake word, redução de ruído e cancelamento de eco.

### Comunicação com clientes e adaptadores

| Componente | Papel diante do Core |
| --- | --- |
| Biony físico | Cliente Wi-Fi: anuncia capacidades, recebe estados, expressões, fala e tarefas; envia eventos locais como wake word e áudio. |
| App mobile | Cliente remoto: envia mensagens, pedidos de memória e comandos; recebe respostas, estados e notificações. |
| PC | Adaptador/agente opcional para executar somente ferramentas autorizadas e devolver resultados. |
| Kobra 4 | Adaptador de impressora que expõe consultas e ações controladas; ações destrutivas exigem confirmação. |
| OpenAI API | Futuro adaptador da porta `Brain`; não é acessado diretamente por face, app ou dispositivos. |

**Em aberto**

- Protocolo de comunicação, formatos de mensagem, autenticação e mecanismo de publicação de eventos.
- Hardware específico do Biony físico e interfaces de seus componentes.
- Armazenamento, hospedagem, observabilidade, persistência de tarefas e interfaces públicas detalhadas entre os componentes.

## 20. Limites deliberados da etapa atual

**Confirmado**

- Não escolher modelo específico de hardware.
- Não escolher modelo da OpenAI.
- Não escolher STT, TTS ou protocolo de comunicação específicos.
- Não assumir que o Biony físico, PC, impressora ou integrações estejam disponíveis.
- Não implementar mobilidade, câmera, hardware, IA real ou integrações antes das respectivas etapas.

Este documento deve ser atualizado antes de implementar uma decisão que atualmente esteja marcada como **Em aberto**.
