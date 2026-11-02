import { Injectable } from '@angular/core';

import type { ChatApiContract, ChatAskRequest, ChatResponse } from './chat-api.types';

const INSUFFICIENT_PATTERN =
  /caf[eé]|sin informaci[oó]n|no existe|desconocid|frenos? regenerativ/i;

@Injectable({ providedIn: 'root' })
export class MockChatApi implements ChatApiContract {
  async ask(request: ChatAskRequest, options?: { debug?: boolean }): Promise<ChatResponse> {
    await delay(700 + Math.round(Math.random() * 550));

    if (INSUFFICIENT_PATTERN.test(request.query)) {
      return {
        answer:
          'No tengo información suficiente en los documentos para responder esto.',
        sufficient: false,
        sources: [],
        images: [],
        debug: options?.debug ? { retrieved: [] } : null,
      };
    }

    return {
      answer: [
        'El **panel de control** concentra la alimentación y las señales de campo del equipo. La revisión del fabricante indica que el conector **J1** corresponde a la alimentación de 24 V y el bloque **J2** agrupa las entradas digitales [S1].',
        '',
        '### Lectura rápida',
        '- Verifica la continuidad de J1 antes de energizar.',
        '- Confirma que las entradas digitales compartan la referencia de 0 V.',
        '- Si el LED de diagnóstico permanece apagado, revisa el fusible F2 [S2].',
        '',
        '> El diagrama adjunto muestra la disposición de referencia; no sustituye la revisión física del tablero.',
      ].join('\n'),
      sufficient: true,
      sources: [
        {
          file: 'Manual_Motor.pdf',
          page: 12,
          bbox: [50, 160, 300, 330],
          sectionPath: ['Panel de control', 'Conexiones'],
        },
        {
          file: 'Manual_Motor.pdf',
          page: 18,
          bbox: [60, 210, 420, 360],
          sectionPath: ['Panel de control', 'Diagnóstico'],
        },
      ],
      images: [
        {
          url: '/mock-panel.svg',
          page: 12,
          bbox: [50, 160, 300, 330],
        },
      ],
      debug: options?.debug
        ? {
            retrieved: [
              {
                chunkId: 'mock-chunk-1',
                docId: 'manual-motor',
                page: 12,
                sectionPath: ['Panel de control', 'Conexiones'],
                kind: 'text',
                rrfScore: 1,
                relevanceScore: 0.82,
                denseRank: 1,
                sparseRank: 1,
              },
              {
                chunkId: 'mock-chunk-2',
                docId: 'manual-motor',
                page: 18,
                sectionPath: ['Panel de control', 'Diagnóstico'],
                kind: 'text',
                rrfScore: 0.5,
                relevanceScore: 0.61,
                denseRank: 2,
                sparseRank: 3,
              },
            ],
          }
        : null,
    };
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}
