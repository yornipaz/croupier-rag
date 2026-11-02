import {
  Component,
  ElementRef,
  afterEveryRender,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import {
  ChatApi,
  type ChatResponse,
  type ChatTurn,
} from '../../core/api/chat-api';
import { AuditModeService } from '../../core/services/audit-mode.service';
import { DocumentCatalogService } from '../../core/services/document-catalog.service';
import {
  ConversationStore,
  type ChatMessage,
} from '../../core/state/conversation.store';
import { ChatComposer } from './components/chat-composer';
import { ChatEmpty } from './components/chat-empty';
import { ChatMessage as ChatMessageComponent } from './components/chat-message';
import { ThinkingBubble } from './components/thinking-bubble';
import { Icon } from '../../shared/ui/icon';
import { InspectorPanel } from '../inspector/inspector-panel';

interface FailedRequest {
  query: string;
  history: ChatTurn[];
  docId: string | null;
  conversationId: string;
}

@Component({
  selector: 'app-chat-page',
  imports: [
    ChatComposer,
    ChatEmpty,
    ChatMessageComponent,
    Icon,
    InspectorPanel,
    ThinkingBubble,
  ],
  host: { class: 'absolute inset-0' },
  templateUrl: './chat-page.html',
})
export class ChatPage {
  private readonly chatApi = inject(ChatApi);
  private readonly documents = inject(DocumentCatalogService);
  private readonly auditMode = inject(AuditModeService);
  protected readonly store = inject(ConversationStore);

  protected readonly activeConversation = this.store.active;
  protected readonly messages = this.store.activeMessages;
  protected readonly documentOptions = this.documents.documents;
  protected readonly selectedDocId = this.documents.selectedId;
  protected readonly auditorEnabled = this.auditMode.enabled;
  protected readonly thinking = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly lastFailed = signal<FailedRequest | null>(null);
  protected readonly visibleError = computed(() => {
    const failed = this.lastFailed();
    return failed?.conversationId === this.store.activeId() ? this.error() : null;
  });

  private readonly bottom = viewChild<ElementRef<HTMLDivElement>>('bottom');
  private lastRenderKey = '';

  constructor() {
    void this.documents.load();
    afterEveryRender(() => {
      const key = `${this.store.activeId()}:${this.messages().length}:${this.thinking()}:${this.error() !== null}`;
      if (key === this.lastRenderKey) {
        return;
      }
      this.lastRenderKey = key;
      this.bottom()?.nativeElement.scrollIntoView({
        behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
          ? 'auto'
          : 'smooth',
        block: 'end',
      });
    });
  }

  protected send(event: { query: string; docId: string | null }): void {
    if (this.thinking()) {
      return;
    }
    const conversationId = this.store.activeId() || this.store.newConversation();
    const history = this.historyBeforeSend();
    this.error.set(null);
    this.lastFailed.set(null);
    this.store.addMessage(conversationId, {
      id: createMessageId(),
      role: 'user',
      content: event.query,
      sources: [],
      images: [],
      sufficient: true,
      createdAt: Date.now(),
    });
    void this.performAsk(event.query, history, event.docId, conversationId);
  }

  protected sendPrompt(query: string): void {
    this.send({ query, docId: this.documents.selectedId() });
  }

  protected onDocumentChange(documentId: string | null): void {
    this.documents.select(documentId);
  }

  protected retry(): void {
    const failed = this.lastFailed();
    if (!failed || this.thinking()) {
      return;
    }
    this.error.set(null);
    void this.performAsk(
      failed.query,
      failed.history,
      failed.docId,
      failed.conversationId,
    );
  }

  protected clearError(): void {
    this.error.set(null);
    this.lastFailed.set(null);
  }

  private async performAsk(
    query: string,
    history: ChatTurn[],
    docId: string | null,
    conversationId: string,
  ): Promise<void> {
    this.thinking.set(true);
    this.error.set(null);
    try {
      const response = await this.chatApi.ask({
        query,
        history,
        docId,
        conversationId,
      });
      this.store.addMessage(conversationId, this.assistantMessage(response));
      this.lastFailed.set(null);
    } catch (error) {
      this.error.set(
        error instanceof Error
          ? error.message
          : 'No se pudo completar la consulta. Inténtalo de nuevo.',
      );
      this.lastFailed.set({ query, history, docId, conversationId });
    } finally {
      this.thinking.set(false);
    }
  }

  private assistantMessage(response: ChatResponse): ChatMessage {
    return {
      id: createMessageId(),
      role: 'assistant',
      content: response.answer,
      sources: response.sources ?? [],
      images: response.images ?? [],
      sufficient: response.sufficient,
      createdAt: Date.now(),
    };
  }

  private historyBeforeSend(): ChatTurn[] {
    return this.messages()
      .slice(-12)
      .map((message) => ({
        role: message.role,
        content: message.content,
      }));
  }
}

function createMessageId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `message-${Date.now()}-${Math.random()}`;
}
