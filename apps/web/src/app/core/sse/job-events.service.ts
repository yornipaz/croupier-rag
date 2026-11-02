import { Injectable, signal } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { JobEvent } from '../api/documents.types';

export type JobConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed';

const TERMINAL_STATUSES: ReadonlySet<JobEvent['status']> = new Set(['COMPLETED', 'FAILED']);

@Injectable({ providedIn: 'root' })
export class JobEventsService {
  private readonly lastEventState = signal<JobEvent | null>(null);
  private readonly connectionState = signal<JobConnectionState>('idle');

  readonly lastEvent = this.lastEventState.asReadonly();
  readonly connection = this.connectionState.asReadonly();

  watch(jobId: string): Observable<JobEvent> {
    return new Observable<JobEvent>((subscriber) => {
      let source: EventSource | null = null;
      let reconnectTimer: number | null = null;
      let attempts = 0;
      let stopped = false;

      const cleanup = () => {
        stopped = true;
        if (reconnectTimer !== null) {
          window.clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
        source?.close();
        source = null;
      };

      const scheduleReconnect = () => {
        if (stopped) {
          return;
        }
        attempts += 1;
        if (attempts > 6) {
          this.connectionState.set('closed');
          subscriber.error(
            new Error('No se pudo restablecer la conexión con el progreso del job.'),
          );
          cleanup();
          return;
        }
        this.connectionState.set('reconnecting');
        const delay = Math.min(10_000, 500 * 2 ** Math.min(attempts - 1, 4));
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, delay);
      };

      const connect = () => {
        if (stopped) {
          return;
        }
        this.connectionState.set(attempts === 0 ? 'connecting' : 'reconnecting');
        source = new EventSource(this.eventsUrl(jobId));
        source.onopen = () => {
          if (stopped) {
            return;
          }
          attempts = 0;
          this.connectionState.set('open');
        };
        source.addEventListener('job', (event: Event) => {
          if (stopped) {
            return;
          }
          const message = event as MessageEvent<string>;
          let job: JobEvent;
          try {
            job = JSON.parse(message.data) as JobEvent;
          } catch {
            return;
          }
          attempts = 0;
          this.lastEventState.set(job);
          this.connectionState.set('open');
          subscriber.next(job);
          if (TERMINAL_STATUSES.has(job.status)) {
            this.connectionState.set('closed');
            cleanup();
            subscriber.complete();
          }
        });
        source.onerror = () => {
          if (stopped) {
            return;
          }
          source?.close();
          source = null;
          scheduleReconnect();
        };
      };

      connect();
      return () => {
        if (!stopped) {
          this.connectionState.set('closed');
        }
        cleanup();
      };
    });
  }

  private eventsUrl(jobId: string): string {
    return `${environment.apiBaseUrl}${environment.apiPrefix}/jobs/${jobId}/events`;
  }
}
