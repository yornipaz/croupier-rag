import { Component, computed, effect, inject, input, output, signal } from '@angular/core';

import type { JobEvent } from '../../../core/api/documents.types';
import { JobEventsService, type JobConnectionState } from '../../../core/sse/job-events.service';
import { Icon } from '../../../shared/ui/icon';

interface TimelineStage {
  key: string;
  label: string;
  detail: string;
  index: number;
}

const STAGES: TimelineStage[] = [
  { key: 'parse', label: 'Parsing', detail: 'Texto, tablas y estructura', index: 0 },
  { key: 'images', label: 'Imágenes', detail: 'Figuras, captions y vínculos', index: 1 },
  { key: 'chunk', label: 'Chunking', detail: 'Bloques con contexto de sección', index: 2 },
  { key: 'embed', label: 'Embeddings', detail: 'Vector denso + BM25 por lotes', index: 3 },
  { key: 'index', label: 'Indexando', detail: 'Upsert híbrido en Qdrant', index: 4 },
];

const STAGE_INDEX: Record<string, number> = {
  queued: -1,
  pending: -1,
  loading: -1,
  parse: 0,
  detect_structure: 0,
  link_images: 1,
  chunk: 2,
  embed: 3,
  index: 4,
  completed: 5,
  failed: -1,
};

type StageState = 'done' | 'active' | 'pending' | 'failed';

@Component({
  selector: 'app-job-timeline',
  imports: [Icon],
  templateUrl: './job-timeline.html',
  styleUrl: './job-timeline.css',
})
export class JobTimeline {
  readonly jobId = input.required<string>();
  readonly finished = output<JobEvent>();

  private readonly events = inject(JobEventsService);
  protected readonly job = signal<JobEvent | null>(null);
  protected readonly streamError = signal<string | null>(null);
  protected readonly connection = this.events.connection;
  protected readonly stages = STAGES;
  protected readonly activeIndex = computed(() => {
    const job = this.job();
    return job ? (STAGE_INDEX[job.stage] ?? 0) : -1;
  });

  constructor() {
    effect((onCleanup) => {
      const jobId = this.jobId();
      this.job.set(null);
      this.streamError.set(null);
      const subscription = this.events.watch(jobId).subscribe({
        next: (job) => {
          this.job.set(job);
          if (job.status === 'COMPLETED' || job.status === 'FAILED') {
            this.finished.emit(job);
          }
        },
        error: (error: unknown) => {
          this.streamError.set(
            error instanceof Error
              ? error.message
              : 'Se perdió la conexión con el progreso del job.',
          );
        },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }

  protected stageState(index: number): StageState {
    const job = this.job();
    if (!job) {
      return 'pending';
    }
    if (job.status === 'COMPLETED') {
      return 'done';
    }
    if (job.status === 'FAILED' && index === this.activeIndex()) {
      return 'failed';
    }
    if (index < this.activeIndex()) {
      return 'done';
    }
    if (job.status === 'PROCESSING' && index === this.activeIndex()) {
      return 'active';
    }
    return 'pending';
  }

  protected stagePercent(index: number): number {
    const job = this.job();
    if (!job) {
      return 0;
    }
    const state = this.stageState(index);
    if (state === 'done') {
      return 100;
    }
    if (state === 'active' || state === 'failed') {
      return job.progress;
    }
    return 0;
  }

  protected stageStatus(index: number): string {
    const state = this.stageState(index);
    if (state === 'done') {
      return 'Completado';
    }
    if (state === 'active') {
      return `${this.job()?.progress ?? 0}%`;
    }
    if (state === 'failed') {
      return 'Error';
    }
    return 'Pendiente';
  }

  protected connectionLabel(): string {
    return this.connectionLabelFor(this.connection());
  }

  private connectionLabelFor(state: JobConnectionState): string {
    switch (state) {
      case 'connecting':
        return 'Conectando';
      case 'open':
        return 'En vivo';
      case 'reconnecting':
        return 'Reconectando';
      case 'closed':
        return 'Finalizado';
      default:
        return 'En espera';
    }
  }

  protected jobTitle(): string {
    const job = this.job();
    if (!job) {
      return 'Esperando estado de ingesta';
    }
    if (job.status === 'COMPLETED') {
      return 'Documento listo';
    }
    if (job.status === 'FAILED') {
      return 'La ingesta falló';
    }
    return 'Procesando documento';
  }
}
