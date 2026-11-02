import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { DocumentResource } from '../api/chat-api.types';

export interface DocumentOption {
  id: string;
  filename: string;
  pages: number | null;
  chunks: number | null;
  createdAt: string;
}

const MOCK_DOCUMENTS: DocumentOption[] = [
  {
    id: 'manual-motor',
    filename: 'Manual_Motor.pdf',
    pages: 42,
    chunks: 186,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 26).toISOString(),
  },
  {
    id: 'manual-hvac',
    filename: 'Manual_HVAC.pdf',
    pages: 28,
    chunks: 94,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 52).toISOString(),
  },
  {
    id: 'guia-robotica',
    filename: 'Guia_Robotica.pdf',
    pages: 65,
    chunks: 312,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 80).toISOString(),
  },
];

@Injectable({ providedIn: 'root' })
export class DocumentCatalogService {
  private readonly http = inject(HttpClient);
  private readonly documentsState = signal<DocumentOption[]>(
    environment.useMock ? MOCK_DOCUMENTS : [],
  );
  private readonly selectedState = signal<string | null>(null);
  private readonly loadingState = signal(false);
  private readonly errorState = signal<string | null>(null);
  private loaded = environment.useMock;

  readonly documents = this.documentsState.asReadonly();
  readonly selectedId = this.selectedState.asReadonly();
  readonly loading = this.loadingState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly selectedDocument = computed(
    () =>
      this.documentsState().find((document) => document.id === this.selectedState()) ??
      null,
  );

  async load(force = false): Promise<void> {
    if (environment.useMock || this.loadingState() || (this.loaded && !force)) {
      return;
    }
    this.loadingState.set(true);
    this.errorState.set(null);
    try {
      const response = await firstValueFrom(
        this.http.get<DocumentResource[]>(
          `${environment.apiBaseUrl}${environment.apiPrefix}/documents`,
        ),
      );
      this.documentsState.set(
        response.map((document) => ({
          id: document.id,
          filename: document.filename,
          pages: document.pageCount ?? null,
          chunks: document.chunkCount ?? null,
          createdAt: document.createdAt,
        })),
      );
      this.loaded = true;
    } catch {
      this.errorState.set('No se pudieron cargar los documentos indexados.');
    } finally {
      this.loadingState.set(false);
    }
  }

  select(documentId: string | null): void {
    this.selectedState.set(documentId);
  }
}
