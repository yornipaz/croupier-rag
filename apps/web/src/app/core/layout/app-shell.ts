import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { Header } from './header';
import { Sidebar } from './sidebar';
import { ShellStateService } from '../services/shell-state.service';

@Component({
  selector: 'app-shell',
  imports: [Header, RouterOutlet, Sidebar],
  host: {
    '(document:keydown.escape)': 'closeMobileSidebar()',
  },
  templateUrl: './app-shell.html',
})
export class AppShell {
  private readonly shell = inject(ShellStateService);

  closeMobileSidebar(): void {
    this.shell.closeMobile();
  }
}
