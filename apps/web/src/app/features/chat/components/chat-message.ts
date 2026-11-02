import { Component, computed, input } from '@angular/core';
import { MarkdownComponent } from 'ngx-markdown';

import type { ChatMessage as ChatMessageModel } from '../../../core/state/conversation.store';
import { Icon } from '../../../shared/ui/icon';
import { LogoMark } from '../../../shared/ui/logo-mark';
import { SourceChips } from '../../../shared/ui/source-chips';
import { FigureViewer } from './figure-viewer';

@Component({
  selector: 'app-chat-message',
  imports: [FigureViewer, Icon, LogoMark, MarkdownComponent, SourceChips],
  templateUrl: './chat-message.html',
})
export class ChatMessage {
  readonly message = input.required<ChatMessageModel>();

  protected readonly isUser = computed(() => this.message().role === 'user');
  protected readonly time = computed(() =>
    new Intl.DateTimeFormat('es', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(this.message().createdAt),
  );
  protected readonly isoTime = computed(() => new Date(this.message().createdAt).toISOString());
}
