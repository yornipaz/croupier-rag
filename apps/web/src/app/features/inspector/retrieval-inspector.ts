import { Component, computed, inject, output } from '@angular/core';

import type { ChatMessage } from '../../core/state/conversation.store';
import { ConversationStore } from '../../core/state/conversation.store';
import { FocusTrap } from '../../shared/ui/focus-trap';
import { Icon } from '../../shared/ui/icon';

@Component({
  selector: 'app-retrieval-inspector',
  imports: [FocusTrap, Icon],
  host: {
    '(document:keydown.escape)': 'requestClose()',
  },
  templateUrl: './retrieval-inspector.html',
  styleUrl: './retrieval-inspector.css',
})
export class RetrievalInspector {
  readonly closed = output<void>();

  private readonly store = inject(ConversationStore);
  protected readonly assistantMessages = computed(() =>
    this.store
      .activeMessages()
      .filter((message) => message.role === 'assistant')
      .reverse(),
  );

  protected requestClose(): void {
    this.closed.emit();
  }

  protected time(message: ChatMessage): string {
    return new Intl.DateTimeFormat('es', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(message.createdAt);
  }

  protected rejectionReason(message: ChatMessage): string | null {
    if (message.sufficient) {
      return null;
    }
    return 'Rechazo defensivo: el mejor score no alcanzó el umbral o la respuesta no pudo validarse con las fuentes.';
  }

  protected bestScore(message: ChatMessage): number {
    const retrieved = message.debug?.retrieved ?? [];
    return retrieved.reduce((best, hit) => Math.max(best, hit.relevanceScore), 0);
  }
}
