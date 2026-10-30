# Lista de compras — totem do Biony (F7)

O totem é um "cliente" do servidor: ouve a palavra "Biony", grava o pedido, manda para o
servidor e toca a resposta. Toda a inteligência continua no servidor.

Preços são **faixas aproximadas** (out/2026) — confira na hora. AliExpress costuma sair pela
metade do preço, mas demora de 2 a 5 semanas; Mercado Livre chega em dias.

## Essencial

| # | Peça | Quantidade | Faixa de preço | Por quê |
|---|---|---|---|---|
| 1 | **ESP32-S3-DevKitC-1 N16R8** (16 MB flash, 8 MB PSRAM, USB-C) | 1 | R$ 60–130 | O cérebro do totem. O **N16R8** importa: a PSRAM de 8 MB guarda o áudio e o modelo do wake word. |
| 2 | **Microfone I2S INMP441** (módulo) | 2 | R$ 15–25 cada | Microfone digital, sem ruído de fio. Compre 2: é barato e fácil de queimar soldando. |
| 3 | **Amplificador I2S MAX98357A** (módulo) | 1 | R$ 15–25 | Recebe o áudio digital do ESP32 e toca no alto-falante. |
| 4 | **Alto-falante 3 W, 4 Ω** (40 mm ou 28 mm) | 1 | R$ 10–20 | A voz do Biony. 4 Ω é o que o MAX98357A gosta. |
| 5 | **Tela IPS 1,54" 240×240 SPI (ST7789)** | 1 | R$ 30–50 | O rosto (fica para depois, mas já compra para o corpo nascer certo). Quadrada combina com o cubo. |
| 6 | **Protoboard 830 pontos + jumpers** (macho-macho e macho-fêmea) | 1 kit | R$ 20–35 | Para montar e testar sem solda definitiva. Se o kit do seu Arduino tem, pule. |

**Total essencial: ~R$ 165–310** (com 2 microfones).

## Ferramentas (se ainda não tiver)

| Peça | Faixa de preço | Por quê |
|---|---|---|
| **Ferro de solda 40–60 W + estanho** (fino, com fluxo) | R$ 40–80 | O INMP441 e o MAX98357A quase sempre vêm com a barra de pinos **solta**: precisa soldar 6–7 pinos em cada. |
| **Cabo USB-C que transfere dados** (não só carrega) | R$ 15–25 | Para programar o ESP32 pela Arduino IDE. Muito cabo de celular barato é só de carga. |
| **Fonte USB 5 V 2 A** | — | Um carregador de celular comum serve. |

## Opcional

| Peça | Faixa de preço | Por quê |
|---|---|---|
| **Potenciômetro 10 kΩ** | R$ 3–5 | Botão físico de volume (dá para fazer só por software). |
| **Botão táctil** | R$ 2 | Falar com o Biony apertando, sem wake word (útil para testar). |
| **LED RGB / anel WS2812 pequeno** | R$ 10–20 | Mostrar "ouvindo/pensando" antes da tela funcionar. |

## Cuidados na compra

- Tem que ser **ESP32-S3**. Não serve ESP32 "comum", ESP32-C3 nem ESP8266.
- Procure **"N16R8"** no anúncio. A versão N8 sem a letra R não tem PSRAM.
- Não confunda o **INMP441** (I2S, digital) com microfones analógicos tipo **MAX4466/MAX9814**.
- Se achar o INMP441 e o MAX98357A **já com os pinos soldados**, vale pagar um pouco a mais.
- O Arduino UNO R3 que você tem **não serve** para o totem (pouca memória e sem Wi-Fi), mas
  a mesma Arduino IDE programa o ESP32-S3.

## Alternativa "tudo em um" (mais cara, zero fiação)

**ESP32-S3-BOX-3** (Espressif): já vem com 2 microfones, alto-falante, tela 2,4" sensível ao
toque e caixinha. Custa bem mais (R$ 300–500, geralmente importado) e o formato é fixo, o que
atrapalha o corpo em cubo impresso em 3D. Só vale se você quiser fugir da solda e da protoboard.
