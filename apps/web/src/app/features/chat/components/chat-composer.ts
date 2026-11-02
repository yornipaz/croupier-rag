import { Component, ElementRef, computed, input, output, signal, viewChild } from '@angular/core';

import type { DocumentOption } from '../../../core/services/document-catalog.service';
import { Icon } from '../../../shared/ui/icon';

@Component({
  selector: 'app-chat-composer',
  imports: [Icon],
  templateUrl: './chat-composer.html',
})
export class ChatComposer {
  readonly disabled = input(false);
  readonly documents = input<DocumentOption[]>([]);
  readonly selectedDocId = input<string | null>(null);
  readonly send = output<{ query: string; docId: string | null }>();
  readonly documentChange = output<string | null>();

  protected readonly draft = signal('');
  protected readonly canSend = computed(
    () => !this.disabled() && this.draft().trim().length > 0,
  );
  private readonly textarea = viewChild<ElementRef<HTMLTextAreaElement>>('textarea');

  protected onInput(event: Event): void {
    const element = event.target as HTMLTextAreaElement;
    this.draft.set(element.value);
    this.resize(element);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      this.submit();
    }
  }

  protected submit(): void {
    const query = this.draft().trim();
    if (!query || !this.canSend()) {
      return;
    }
    this.send.emit({ query, docId: this.selectedDocId() });
    this.draft.set('');
    const element = this.textarea()?.nativeElement;
    if (element) {
      element.value = '';
      element.style.height = 'auto';
    }
  }

  protected onDocumentChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.documentChange.emit(value || null);
  }

  private resize(element: HTMLTextAreaElement): void {
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 168)}px`;
  }
}
