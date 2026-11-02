import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';

import { ConversationStore } from '../state/conversation.store';
import { ShellStateService } from '../services/shell-state.service';
import { Icon } from '../../shared/ui/icon';
import { LogoMark } from '../../shared/ui/logo-mark';

@Component({
  selector: 'app-sidebar',
  imports: [Icon, LogoMark, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
})
export class Sidebar {
  private readonly router = inject(Router);
  private readonly shell = inject(ShellStateService);
  protected readonly store = inject(ConversationStore);

  protected readonly collapsed = this.shell.sidebarCollapsed;
  protected readonly mobileOpen = this.shell.mobileSidebarOpen;
  protected readonly conversations = this.store.conversations;
  protected readonly activeId = this.store.activeId;

  protected toggleSidebar(): void {
    this.shell.toggleSidebar();
  }

  protected closeMobile(): void {
    this.shell.closeMobile();
  }

  protected newConversation(): void {
    this.store.newConversation();
    this.shell.closeMobile();
    void this.router.navigate(['/chat']);
  }

  protected selectConversation(conversationId: string): void {
    this.store.select(conversationId);
    this.shell.closeMobile();
    void this.router.navigate(['/chat']);
  }

  protected formatUpdated(updatedAt: number): string {
    const minutes = Math.max(0, Math.floor((Date.now() - updatedAt) / 60000));
    if (minutes < 1) {
      return 'Ahora';
    }
    if (minutes < 60) {
      return `Hace ${minutes} min`;
    }
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
      return `Hace ${hours} h`;
    }
    return new Intl.DateTimeFormat('es', { day: '2-digit', month: 'short' }).format(
      updatedAt,
    );
  }
}
