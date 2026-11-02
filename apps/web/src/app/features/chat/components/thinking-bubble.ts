import { Component } from '@angular/core';

import { LogoMark } from '../../../shared/ui/logo-mark';

@Component({
  selector: 'app-thinking-bubble',
  imports: [LogoMark],
  template: `
    <div class="flex gap-3" role="status" aria-live="polite">
      <app-logo-mark [size]="28" class="mt-1 hidden sm:inline-flex" />
      <div class="rounded-[1.4rem] rounded-tl-md border border-line/80 bg-surface/70 px-4 py-3">
        <div class="mb-1.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
          <span class="text-accent">Croupier</span>
          <span aria-hidden="true" class="text-line">·</span>
          <span>Pensando</span>
        </div>
        <div class="flex items-center gap-2 text-[13px] text-muted">
          <span class="flex items-center gap-1" aria-hidden="true">
            <span class="thinking-dot"></span>
            <span class="thinking-dot"></span>
            <span class="thinking-dot"></span>
          </span>
          Cruzando el manual y verificando fuentes…
        </div>
      </div>
    </div>
  `,
})
export class ThinkingBubble {}
