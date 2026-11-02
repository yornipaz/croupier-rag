import { Component } from '@angular/core';

import { Icon } from '../../shared/ui/icon';

@Component({
  selector: 'app-inspector-panel',
  imports: [Icon],
  template: `
    <aside
      class="flex h-full w-80 shrink-0 flex-col border-l border-line/70 bg-surface/45 backdrop-blur-sm"
      aria-label="Inspector de auditoría"
    >
      <div class="border-b border-line/70 px-4 py-4">
        <div class="flex items-center gap-2">
          <span class="flex size-8 items-center justify-center rounded-xl border border-accent/30 bg-accent-soft/35 text-accent">
            <app-icon name="audit" [size]="16" />
          </span>
          <div>
            <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-accent">
              Modo auditor
            </p>
            <p class="text-[13px] font-semibold text-ink">Trazas de la consulta</p>
          </div>
        </div>
      </div>

      <div class="space-y-3 overflow-y-auto p-4">
        <div class="rounded-2xl border border-dashed border-line/90 bg-canvas/35 p-4">
          <div class="flex items-center gap-2 text-[11px] font-semibold text-ink">
            <app-icon name="layers" [size]="14" class="text-accent" />
            Recuperación híbrida
          </div>
          <p class="mt-2 text-[11px] leading-5 text-muted">
            Rankings denso y BM25, fusión RRF y umbral defensivo aparecerán aquí en la
            siguiente iteración.
          </p>
        </div>

        <div class="rounded-2xl border border-dashed border-line/90 bg-canvas/35 p-4">
          <div class="flex items-center gap-2 text-[11px] font-semibold text-ink">
            <app-icon name="document" [size]="14" class="text-accent" />
            Prompt y citas
          </div>
          <p class="mt-2 text-[11px] leading-5 text-muted">
            Esta vista conserva el estado de auditoría. El prompt defensivo y las fuentes
            usadas se conectarán cuando el backend exponga debug=true al frontend.
          </p>
        </div>

        <p class="px-1 text-[10px] leading-4 text-muted/80">
          El toggle superior solo guarda la preferencia por ahora; no altera las consultas.
        </p>
      </div>
    </aside>
  `,
})
export class InspectorPanel {}
