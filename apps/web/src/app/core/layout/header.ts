import { NgClass } from '@angular/common';
import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { environment } from '../../../environments/environment';
import { Icon } from '../../shared/ui/icon';
import { LogoMark } from '../../shared/ui/logo-mark';
import { AuditModeService } from '../services/audit-mode.service';
import { ShellStateService } from '../services/shell-state.service';
import { ShortcutsService } from '../services/shortcuts.service';
import { ThemeService } from '../services/theme.service';

@Component({
  selector: 'app-header',
  imports: [Icon, LogoMark, NgClass, RouterLink],
  template: `
    <header
      class="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-line/70 bg-canvas/80 px-4 backdrop-blur-xl sm:px-6"
    >
      <button
        type="button"
        class="inline-flex size-9 items-center justify-center rounded-xl border border-line/80 text-muted transition hover:bg-surface-2 hover:text-ink lg:hidden"
        (click)="openMobile()"
        aria-label="Abrir menú"
        aria-controls="croupier-sidebar"
        [attr.aria-expanded]="mobileOpen()"
      >
        <app-icon name="menu" [size]="19" />
      </button>

      <a
        routerLink="/chat"
        class="flex min-w-0 items-center gap-2.5 lg:hidden"
        aria-label="Croupier, ir al chat"
      >
        <app-logo-mark [size]="30" />
        <span class="font-display text-[1.05rem] font-semibold tracking-tight">Croupier</span>
      </a>

      <div class="hidden min-w-0 items-center gap-3 lg:flex">
        <span class="size-1.5 rounded-full bg-accent"></span>
        <div class="min-w-0">
          <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">Croupier</p>
          <p class="truncate text-[13px] font-semibold text-ink">Mesa de consulta técnica</p>
        </div>
      </div>

      <div class="ml-auto flex items-center gap-1.5 sm:gap-2">
        <button
          type="button"
          class="inline-flex size-9 items-center justify-center rounded-xl border border-line/80 font-display text-sm font-semibold text-muted transition hover:bg-surface-2 hover:text-ink"
          (click)="shortcuts.toggle()"
          aria-label="Ver atajos de teclado"
          title="Atajos de teclado (?)"
        >
          ?
        </button>

        @if (isMock) {
          <span
            data-testid="mock-badge"
            class="hidden items-center gap-1.5 rounded-full border border-accent/25 bg-accent-soft/35 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-accent-strong sm:inline-flex"
            title="Los datos son simulados; no se está llamando al backend"
          >
            <app-icon name="spark" [size]="12" />
            Demo local
          </span>
        }

        <button
          type="button"
          class="inline-flex size-9 items-center justify-center rounded-xl border border-line/80 text-muted transition hover:bg-surface-2 hover:text-ink"
          (click)="toggleTheme()"
          [attr.aria-label]="dark() ? 'Activar modo claro' : 'Activar modo oscuro'"
          [title]="dark() ? 'Modo claro' : 'Modo oscuro'"
        >
          <app-icon [name]="dark() ? 'sun' : 'moon'" [size]="18" />
        </button>

        <button
          type="button"
          data-testid="auditor-toggle"
          class="inline-flex items-center gap-2 rounded-xl border px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition hover:bg-surface-2 sm:px-3"
          [ngClass]="
            auditor()
              ? 'border-accent/50 bg-accent-soft/45 text-accent-strong'
              : 'border-line/80 text-muted'
          "
          (click)="toggleAuditor()"
          [attr.aria-pressed]="auditor()"
          [attr.aria-label]="auditor() ? 'Desactivar modo auditor' : 'Activar modo auditor'"
          title="Guardar preferencia de modo auditor"
        >
          <app-icon name="audit" [size]="16" />
          <span class="hidden sm:inline">Auditor</span>
        </button>
      </div>
    </header>
  `,
})
export class Header {
  private readonly theme = inject(ThemeService);
  private readonly audit = inject(AuditModeService);
  private readonly shell = inject(ShellStateService);
  protected readonly shortcuts = inject(ShortcutsService);

  protected readonly isMock = environment.useMock;
  protected readonly dark = this.theme.dark;
  protected readonly auditor = this.audit.enabled;
  protected readonly mobileOpen = this.shell.mobileSidebarOpen;

  protected openMobile(): void {
    this.shell.openMobile();
  }

  protected toggleTheme(): void {
    this.theme.toggle();
  }

  protected toggleAuditor(): void {
    this.audit.toggle();
  }
}
