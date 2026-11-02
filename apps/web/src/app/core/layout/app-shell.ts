import { Component, inject } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';

import { KeyboardShortcuts } from '../../shared/ui/keyboard-shortcuts';
import { ShortcutsService } from '../services/shortcuts.service';
import { ShellStateService } from '../services/shell-state.service';
import { ConversationStore } from '../state/conversation.store';
import { Header } from './header';
import { Sidebar } from './sidebar';

@Component({
  selector: 'app-shell',
  imports: [Header, KeyboardShortcuts, RouterOutlet, Sidebar],
  host: {
    '(document:keydown.escape)': 'onEscape()',
    '(document:keydown)': 'onKeydown($event)',
  },
  templateUrl: './app-shell.html',
})
export class AppShell {
  private readonly shell = inject(ShellStateService);
  private readonly shortcuts = inject(ShortcutsService);
  private readonly store = inject(ConversationStore);
  private readonly router = inject(Router);

  protected closeMobileSidebar(): void {
    this.shell.closeMobile();
  }

  protected onEscape(): void {
    this.closeMobileSidebar();
    this.shortcuts.close();
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (isEditableTarget(event.target)) {
      return;
    }
    if (document.querySelector('[aria-modal="true"]')) {
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.shell.closeMobile();
      this.shortcuts.close();
      this.store.newConversation();
      void this.router.navigate(['/chat']);
      return;
    }
    if (event.key === '?') {
      event.preventDefault();
      this.shortcuts.toggle();
    }
  }
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}
