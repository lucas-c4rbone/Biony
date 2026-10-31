"use strict";
// Detecta o fim da fala pelo silêncio, sem biblioteca. Recebe o volume (RMS, 0 a 1) a cada ~50 ms e diz
// em que pé está o turno. Separado do app.js para poder ser testado com sequências de volume sintéticas.

const BionyVad = (() => {
  const DEFAULTS = {
    floor: 0.02,        // volume mínimo para contar como voz (RMS); abaixo disso é silêncio
    ratio: 2.5,         // ...ou quantas vezes acima do ruído do ambiente, se o ambiente for barulhento
    minSpeechMs: 250,   // voz de verdade precisa durar isto (estalos e tosse curta não contam)
    calibrationMs: 400, // começo do turno: mede o ruído do ambiente (ar-condicionado, ventilador...)
    maxNoise: 0.06,     // ambiente mais barulhento que isto não é aprendido (senão engoliria a própria fala)
    endSilenceMs: 1300, // silêncio depois da fala que encerra o turno
    noSpeechMs: 8000,   // ninguém falou: desiste
    maxMs: 30000,       // trava de segurança
  };

  function create(options = {}) {
    const o = { ...DEFAULTS, ...options };
    let startedAt = null;
    let previous = null;
    let loudMs = 0;      // quanto tempo de voz já ouvimos
    let lastLoudAt = null;
    let noise = 0.004;   // estimativa do ruído de fundo
    const calibration = [];

    return {
      /** "esperando" | "falando" | "fim" | "sem_fala" | "limite" */
      feed(rms, now) {
        if (startedAt === null) { startedAt = now; previous = now; }
        const dt = now - previous;
        previous = now;
        if (now - startedAt < o.calibrationMs) {
          calibration.push(rms);
          return "esperando";
        }
        if (calibration.length) {
          // Média da metade mais quieta: se ele já começou a falar, as pausas entre as palavras são o "ambiente".
          calibration.sort((a, b) => a - b);
          const quiet = calibration.slice(0, Math.max(1, Math.ceil(calibration.length / 2)));
          noise = Math.min(o.maxNoise, quiet.reduce((a, b) => a + b, 0) / quiet.length);
          calibration.length = 0;
        }
        const loud = rms > Math.max(o.floor, noise * o.ratio);
        if (loud) {
          loudMs += dt;
          lastLoudAt = now;
        } else if (loudMs < o.minSpeechMs) {
          noise = Math.min(o.maxNoise, noise * 0.95 + rms * 0.05); // ainda sem fala: acompanha o ambiente
        }
        // Estalos soltos não se acumulam até virar "fala": passou 0,6 s de silêncio, recomeça a contar.
        if (loudMs < o.minSpeechMs && lastLoudAt !== null && now - lastLoudAt > 600) loudMs = 0;
        const speaking = loudMs >= o.minSpeechMs;
        if (now - startedAt >= o.maxMs) return "limite";
        if (speaking && now - lastLoudAt >= o.endSilenceMs) return "fim";
        if (!speaking && now - startedAt >= o.noSpeechMs) return "sem_fala";
        return speaking ? "falando" : "esperando";
      },
    };
  }

  return { create, DEFAULTS };
})();
