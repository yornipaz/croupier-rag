import { Injectable, computed, signal } from '@angular/core';

import { environment } from '../../../environments/environment';
import type { ChatDebug, ChatImage, ChatSource } from '../api/chat-api.types';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: ChatSource[];
  images: ChatImage[];
  sufficient: boolean;
  createdAt: number;
  debug: ChatDebug | null;
}

export interface Conversation {
  id: string;
  title: string;
  preview: string;
  updatedAt: number;
  messages: ChatMessage[];
}

@Injectable({ providedIn: 'root' })
export class ConversationStore {
  private readonly conversationsState = signal<Conversation[]>(createSeedConversations());
  private readonly activeIdState = signal<string>(this.conversationsState()[0]?.id ?? '');
  private readonly activeConversation = computed(
    () =>
      this.conversationsState().find((conversation) => conversation.id === this.activeIdState()) ??
      this.conversationsState()[0] ??
      null,
  );

  readonly conversations = this.conversationsState.asReadonly();
  readonly activeId = this.activeIdState.asReadonly();
  readonly active = this.activeConversation;
  readonly activeMessages = computed(() => this.activeConversation()?.messages ?? []);

  select(conversationId: string): void {
    this.activeIdState.set(conversationId);
  }

  newConversation(): string {
    const conversation: Conversation = {
      id: createId(),
      title: 'Nueva conversación',
      preview: 'Empieza una consulta sobre tus manuales.',
      updatedAt: Date.now(),
      messages: [],
    };
    this.conversationsState.update((conversations) => [conversation, ...conversations]);
    this.activeIdState.set(conversation.id);
    return conversation.id;
  }

  addMessage(conversationId: string, message: ChatMessage): void {
    this.conversationsState.update((conversations) => {
      const updated = conversations.map((conversation) => {
        if (conversation.id !== conversationId) {
          return conversation;
        }
        const title =
          conversation.title === 'Nueva conversación' && message.role === 'user'
            ? previewText(message.content, 36)
            : conversation.title;
        return {
          ...conversation,
          title,
          preview: previewText(message.content, 64),
          updatedAt: message.createdAt,
          messages: [...conversation.messages, message],
        };
      });
      const current = updated.find((conversation) => conversation.id === conversationId);
      return current
        ? [current, ...updated.filter((conversation) => conversation.id !== conversationId)]
        : updated;
    });
  }
}

function createSeedConversations(): Conversation[] {
  if (!environment.useMock) {
    return [
      {
        id: createId(),
        title: 'Nueva conversación',
        preview: 'Empieza una consulta sobre tus manuales.',
        updatedAt: Date.now(),
        messages: [],
      },
    ];
  }

  const now = Date.now();
  return [
    {
      id: createId(),
      title: 'Panel de control',
      preview: 'Conexiones, diagnóstico y diagrama de referencia.',
      updatedAt: now - 1000 * 60 * 9,
      messages: [
        {
          id: createId(),
          role: 'user',
          content: '¿Cómo interpreto el diagrama del panel de control?',
          sources: [],
          images: [],
          sufficient: true,
          createdAt: now - 1000 * 60 * 11,
          debug: null,
        },
        {
          id: createId(),
          role: 'assistant',
          content: [
            'El **panel de control** agrupa la alimentación y las señales de campo. En la vista de referencia, **J1** corresponde a la alimentación de 24 V y **J2** reúne las entradas digitales [S1].',
            '',
            '### Antes de energizar',
            '- Revisa la continuidad de J1 y la referencia de 0 V.',
            '- Confirma que el fusible **F2** esté íntegro [S2].',
            '- Si el LED de diagnóstico no enciende, contrasta el estado con el diagrama adjunto.',
          ].join('\n'),
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
          sufficient: true,
          createdAt: now - 1000 * 60 * 9,
          debug: {
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
          },
        },
      ],
    },
    {
      id: createId(),
      title: 'Frenos regenerativos',
      preview: 'Sin respaldo documental suficiente.',
      updatedAt: now - 1000 * 60 * 46,
      messages: [
        {
          id: createId(),
          role: 'user',
          content: '¿Qué mantenimiento requiere el sistema de frenos regenerativos?',
          sources: [],
          images: [],
          sufficient: true,
          createdAt: now - 1000 * 60 * 47,
          debug: null,
        },
        {
          id: createId(),
          role: 'assistant',
          content: 'No tengo información suficiente en los documentos para responder esto.',
          sources: [],
          images: [],
          sufficient: false,
          createdAt: now - 1000 * 60 * 46,
          debug: {
            retrieved: [
              {
                chunkId: 'mock-chunk-low',
                docId: 'manual-motor',
                page: 4,
                sectionPath: ['Frenado', 'Mantenimiento'],
                kind: 'text',
                rrfScore: 0.25,
                relevanceScore: 0.18,
                denseRank: 3,
                sparseRank: 5,
              },
            ],
          },
        },
      ],
    },
  ];
}

function createId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `msg-${Date.now()}-${Math.random()}`;
}

function previewText(value: string, limit: number): string {
  const clean = value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`]/g, ' ')
    .replace(/\[[^\]]*\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return clean.length > limit ? `${clean.slice(0, limit - 1).trimEnd()}…` : clean;
}
