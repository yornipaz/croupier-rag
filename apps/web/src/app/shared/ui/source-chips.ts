import { Component, input } from '@angular/core';

import type { ChatSource } from '../../core/api/chat-api.types';
import { Icon } from './icon';

@Component({
  selector: 'app-source-chips',
  imports: [Icon],
  template: `
    @if (sources().length > 0) {
      <div class="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Fuentes consultadas">
        <span class="mr-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
          Fuentes
        </span>
        @for (source of sources(); track source.file + source.page) {
          <span
            class="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-surface-2/70 px-2.5 py-1 text-[11px] font-medium text-muted"
            [title]="source.sectionPath.join(' / ')"
          >
            <app-icon name="document" [size]="12" />
            <span class="max-w-40 truncate">{{ source.file }}</span>
            <span class="text-accent" aria-hidden="true">·</span>
            <span class="whitespace-nowrap text-ink/80">p. {{ source.page }}</span>
          </span>
        }
      </div>
    }
  `,
})
export class SourceChips {
  readonly sources = input.required<ChatSource[]>();
}
