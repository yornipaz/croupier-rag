import { NgClass } from '@angular/common';
import { Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';

import type { JobEvent } from '../../../core/api/documents.types';
import {
  DocumentCatalogService,
  type DocumentOption,
} from '../../../core/services/document-catalog.service';
import { environment } from '../../../../environments/environment';
import { Icon } from '../../../shared/ui/icon';
import { JobTimeline } from './job-timeline';

interface DocumentStatus {
  label: string;
  tone: 'success' | 'accent' | 'danger' | 'muted';
}

@Component({
  selector: 'app-documents-panel',
  imports: [Icon, JobTimeline, NgClass],
  templateUrl: './documents-panel.html',
})
export class DocumentsPanel {
  private readonly router = inject(Router);
  private readonly catalog = inject(DocumentCatalogService);

  protected readonly documents = this.catalog.documents;
  protected readonly loading = this.catalog.loading;
  protected readonly catalogError = this.catalog.error;
  protected readonly maxUploadMb = environment.maxUploadMb;

  protected readonly dragging = signal(false);
  protected readonly uploading = signal(false);
  protected readonly uploadError = signal<string | null>(null);
  protected readonly deleteError = signal<string | null>(null);
  protected readonly activeJobId = signal<string | null>(null);
  protected readonly activeJobName = signal<string | null>(null);
  protected readonly pendingDelete = signal<DocumentOption | null>(null);
  protected readonly deletingId = signal<string | null>(null);
  protected readonly failedDocuments = signal<Record<string, string>>({});
  private readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');

  constructor() {
    void this.catalog.load();
  }

  protected selectFile(): void {
    this.fileInput()?.nativeElement.click();
  }

  protected onFileInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    void this.handleFiles(input.files);
    input.value = '';
  }

  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(true);
  }

  protected onDragLeave(event: DragEvent): void {
    if (event.currentTarget === event.target) {
      this.dragging.set(false);
    }
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    void this.handleFiles(event.dataTransfer?.files ?? null);
  }

  protected ask(document: DocumentOption): void {
    this.catalog.select(document.id);
    void this.router.navigate(['/chat']);
  }

  protected requestDelete(document: DocumentOption): void {
    this.deleteError.set(null);
    this.pendingDelete.set(document);
  }

  protected cancelDelete(): void {
    this.pendingDelete.set(null);
  }

  protected confirmDelete(): void {
    const document = this.pendingDelete();
    if (!document) {
      return;
    }
    this.deletingId.set(document.id);
    this.deleteError.set(null);
    void this.catalog
      .delete(document.id)
      .then(() => {
        if (this.activeJobId() === document.jobId) {
          this.dismissTimeline();
        }
        this.pendingDelete.set(null);
        this.failedDocuments.update((documents) => {
          const next = { ...documents };
          delete next[document.id];
          return next;
        });
      })
      .catch((error: unknown) => {
        this.deleteError.set(
          error instanceof Error ? error.message : 'No se pudo eliminar el documento.',
        );
      })
      .finally(() => this.deletingId.set(null));
  }

  protected refresh(): void {
    void this.catalog.load(true);
  }

  protected dismissTimeline(): void {
    this.activeJobId.set(null);
    this.activeJobName.set(null);
  }

  protected onJobFinished(job: JobEvent): void {
    this.failedDocuments.update((documents) => {
      const next = { ...documents };
      if (job.status === 'FAILED') {
        next[job.docId] = job.error ?? 'La ingesta falló.';
      } else {
        delete next[job.docId];
      }
      return next;
    });
    void this.catalog.load(true);
  }

  protected statusFor(document: DocumentOption): DocumentStatus {
    if (this.failedDocuments()[document.id]) {
      return { label: 'Error', tone: 'danger' };
    }
    if ((document.chunks ?? 0) > 0) {
      return { label: 'Indexado', tone: 'success' };
    }
    if (document.jobId) {
      return { label: 'Procesando', tone: 'accent' };
    }
    return { label: 'Pendiente', tone: 'muted' };
  }

  protected statusClasses(document: DocumentOption): string {
    switch (this.statusFor(document).tone) {
      case 'success':
        return 'text-success';
      case 'accent':
        return 'text-accent';
      case 'danger':
        return 'text-danger';
      default:
        return 'text-muted';
    }
  }

  protected failureReason(document: DocumentOption): string | null {
    return this.failedDocuments()[document.id] ?? null;
  }

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(new Date(value));
  }

  private async handleFiles(files: FileList | null): Promise<void> {
    const file = files?.item(0);
    if (!file) {
      return;
    }
    this.uploadError.set(null);
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      this.uploadError.set('Solo se aceptan archivos PDF.');
      return;
    }
    if (file.size > this.maxUploadMb * 1024 * 1024) {
      this.uploadError.set(`El PDF supera el máximo de ${this.maxUploadMb} MB.`);
      return;
    }
    this.uploading.set(true);
    try {
      const response = await this.catalog.upload(file);
      this.activeJobId.set(response.jobId);
      this.activeJobName.set(file.name);
      await this.catalog.load(true);
    } catch (error) {
      this.uploadError.set(error instanceof Error ? error.message : 'No se pudo subir el PDF.');
    } finally {
      this.uploading.set(false);
    }
  }
}
