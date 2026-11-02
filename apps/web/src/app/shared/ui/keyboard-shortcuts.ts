import { Component, inject } from '@angular/core';

import { ShortcutsService } from '../../core/services/shortcuts.service';
import { FocusTrap } from './focus-trap';
import { Icon } from './icon';

@Component({
  selector: 'app-keyboard-shortcuts',
  imports: [FocusTrap, Icon],
  host: {
    '(document:keydown.escape)': 'close()',
  },
  template: `
    @if (shortcuts.open()) {
      <div class="fixed inset-0 z-[90] flex items-center justify-center p-4">
        <div
          class="absolute inset-0 bg-black/55 backdrop-blur-sm"
          (click)="close()"
          aria-hidden="true"
        ></div>
        <section
          class="relative z-10 w-full max-w-md overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="shortcuts-title"
          appFocusTrap
          tabindex="-1"
        >
          <header class="flex items-center gap-3 border-b border-line/80 px-4 py-3.5">
            <span
              class="flex size-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft/35 text-accent"
            >
              <app-icon name="spark" [size]="15" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent">
                Teclado
              </p>
              <h2 id="shortcuts-title" class="text-[13px] font-semibold text-ink">
                Atajos de Croupier
              </h2>
            </div>
            <button
              type="button"
              class="inline-flex size-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
              (click)="close()"
              aria-label="Cerrar atajos"
            >
              <app-icon name="close" [size]="16" />
            </button>
          </header>
          <dl class="divide-y divide-line/60 px-4 py-2">
            @for (shortcut of shortcutsList; track shortcut.keys) {
              <div class="flex items-center gap-4 py-2.5">
                <dt class="flex shrink-0 items-center gap-1">
                  @for (key of shortcut.keys; track key) {
                    <kbd
                      class="rounded-md border border-line/80 bg-surface-2 px-1.5 py-1 font-sans text-[10px] font-semibold text-ink"
                    >
                      {{ key }}
                    </kbd>
                  }
                </dt>
                <dd class="text-[11px] text-muted">{{ shortcut.description }}</dd>
              </div>
            }
          </dl>
          <footer class="border-t border-line/80 px-4 py-2.5 text-[10px] text-muted/80">
            Los atajos se desactivan mientras escribes en un campo.
          </footer>
        </section>
      </div>
    }
  `,
})
export class KeyboardShortcuts {
  protected readonly shortcuts = inject(ShortcutsService);
  protected readonly shortcutsList = [
    { keys: ['Enter'], description: 'Enviar la consulta' },
    { keys: ['Shift', 'Enter'], description: 'Insertar un salto de línea' },
    { keys: ['Ctrl', 'K'], description: 'Nueva conversación (Cmd en macOS)' },
    { keys: ['/'], description: 'Enfocar el campo de consulta' },
    { keys: ['Esc'], description: 'Cerrar modales, paneles y menú móvil' },
    { keys: ['?'], description: 'Abrir esta ayuda' },
  ];

  protected close(): void {
    this.shortcuts.close();
  }
}
