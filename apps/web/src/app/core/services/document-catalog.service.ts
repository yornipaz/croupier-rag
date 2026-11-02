import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { DocumentResource, UploadDocumentResponse } from '../api/documents.types';

export interface DocumentOption {
  id: string;
  filename: string;
  pages: number | null;
  chunks: number | null;
  createdAt: string;
  jobId: string | null;
}

const MOCK_DOCUMENTS: DocumentOption[] = [
  {
    id: 'manual-motor',
    filename: 'Manual_Motor.pdf',
    pages: 42,
    chunks: 186,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 26).toISOString(),
    jobId: null,
  },
  {
    id: 'manual-hvac',
    filename: 'Manual_HVAC.pdf',
    pages: 28,
    chunks: 94,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 52).toISOString(),
    jobId: null,
  },
  {
    id: 'guia-robotica',
    filename: 'Guia_Robotica.pdf',
    pages: 65,
    chunks: 312,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 80).toISOString(),
    jobId: null,
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
  private loaded = false;
  private live = false;

  readonly documents = this.documentsState.asReadonly();
  readonly selectedId = this.selectedState.asReadonly();
  readonly loading = this.loadingState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly selectedDocument = computed(
    () => this.documentsState().find((document) => document.id === this.selectedState()) ?? null,
  );

  async load(force = false): Promise<void> {
    if (this.loadingState() || (this.loaded && !force)) {
      return;
    }
    this.loadingState.set(true);
    this.errorState.set(null);
    try {
      const response = await firstValueFrom(
        this.http.get<DocumentResource[]>(this.apiUrl('/documents')),
      );
      this.documentsState.set(
        response.map((document) => ({
          id: document.id,
          filename: document.filename,
          pages: document.pageCount ?? null,
          chunks: document.chunkCount ?? null,
          createdAt: document.createdAt,
          jobId: document.jobId ?? null,
        })),
      );
      this.loaded = true;
      this.live = true;
    } catch {
      if (this.live || !environment.useMock) {
        this.errorState.set('No se pudieron cargar los documentos indexados.');
      } else {
        this.loaded = true;
      }
    } finally {
      this.loadingState.set(false);
    }
  }

  async upload(file: File): Promise<UploadDocumentResponse> {
    const form = new FormData();
    form.append('file', file);
    try {
      const response = await firstValueFrom(
        this.http.post<UploadDocumentResponse>(this.apiUrl('/documents'), form),
      );
      this.live = true;
      this.loaded = true;
      this.documentsState.update((documents) => [
        {
          id: response.documentId,
          filename: file.name,
          pages: null,
          chunks: null,
          createdAt: new Date().toISOString(),
          jobId: response.jobId,
        },
        ...documents.filter((document) => document.id !== response.documentId),
      ]);
      return response;
    } catch {
      throw new Error('No se pudo subir el PDF. Comprueba que el backend esté disponible.');
    }
  }

  async delete(documentId: string): Promise<void> {
    const localOnly = environment.useMock && !this.live;
    try {
      if (!localOnly) {
        await firstValueFrom(this.http.delete(this.apiUrl(`/documents/${documentId}`)));
      }
      this.documentsState.update((documents) =>
        documents.filter((document) => document.id !== documentId),
      );
      if (this.selectedState() === documentId) {
        this.selectedState.set(null);
      }
    } catch {
      throw new Error('No se pudo eliminar el documento. Inténtalo de nuevo.');
    }
  }

  select(documentId: string | null): void {
    this.selectedState.set(documentId);
  }

  private apiUrl(path: string): string {
    return `${environment.apiBaseUrl}${environment.apiPrefix}${path}`;
  }
}
