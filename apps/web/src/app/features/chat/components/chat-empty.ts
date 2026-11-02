import { Component, output } from '@angular/core';

import { Icon, type IconName } from '../../../shared/ui/icon';
import { LogoMark } from '../../../shared/ui/logo-mark';

interface Suggestion {
  label: string;
  query: string;
  icon: IconName;
}

@Component({
  selector: 'app-chat-empty',
  imports: [Icon, LogoMark],
  template: `
    <section class="mx-auto flex w-full max-w-4xl flex-col items-center px-5 py-10 text-center sm:py-16">
      <div class="relative mb-6">
        <div class="absolute inset-0 -z-10 blur-2xl">
          <div class="mx-auto size-28 rounded-full bg-accent/20"></div>
        </div>
        <app-logo-mark [size]="74" />
      </div>

      <p class="mb-3 text-[10px] font-semibold uppercase tracking-[0.26em] text-accent">
        Mesa de consulta · RAG técnico
      </p>
      <h1
        class="font-display max-w-2xl text-4xl font-semibold leading-[1.04] tracking-[-0.035em] text-ink sm:text-5xl"
      >
        Pregunta al manual.
        <span class="text-accent">Te enseño la página.</span>
      </h1>
      <p class="mt-4 max-w-xl text-sm leading-6 text-muted sm:text-[0.95rem]">
        Respuestas ancladas a tus PDFs, con la fuente, la página y el diagrama exacto.
        Sin adivinar cuando el documento no alcanza.
      </p>

      <div class="mt-9 grid w-full max-w-3xl gap-3 text-left sm:grid-cols-3">
        @for (suggestion of suggestions; track suggestion.query) {
          <button
            type="button"
            class="group flex min-h-28 flex-col items-start rounded-2xl border border-line/80 bg-surface/70 p-4 text-left transition hover:-translate-y-0.5 hover:border-accent/40 hover:bg-surface hover:shadow-soft"
            (click)="ask.emit(suggestion.query)"
          >
            <span
              class="mb-3 flex size-8 items-center justify-center rounded-lg border border-line/80 text-muted transition group-hover:border-accent/30 group-hover:text-accent"
            >
              <app-icon [name]="suggestion.icon" [size]="16" />
            </span>
            <span class="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">
              Prueba con
            </span>
            <span class="mt-1 text-[13px] font-semibold leading-5 text-ink">
              {{ suggestion.label }}
            </span>
            <span class="mt-auto pt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-accent opacity-0 transition group-hover:opacity-100">
              Consultar
              <app-icon name="arrow-right" [size]="12" />
            </span>
          </button>
        }
      </div>

      <p class="mt-7 inline-flex items-center gap-2 text-[10px] text-muted/80">
        <app-icon name="shield" [size]="13" />
        El asistente cita fuentes y declara cuando no tiene respaldo documental.
      </p>
    </section>
  `,
})
export class ChatEmpty {
  readonly ask = output<string>();

  protected readonly suggestions: Suggestion[] = [
    {
      label: 'Interpretar el diagrama del panel de control',
      query: '¿Cómo interpreto el diagrama del panel de control?',
      icon: 'layers',
    },
    {
      label: 'Revisar el procedimiento de diagnóstico',
      query: '¿Qué pasos de diagnóstico recomienda el manual para el panel?',
      icon: 'audit',
    },
    {
      label: 'Probar el estado sin información',
      query: '¿Hay datos sobre frenos regenerativos en estos manuales?',
      icon: 'shield',
    },
  ];
}
