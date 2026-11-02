import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import {
  DocumentCatalogService,
  type DocumentOption,
} from '../../core/services/document-catalog.service';
import { Icon } from '../../shared/ui/icon';

@Component({
  selector: 'app-documents-page',
  imports: [Icon],
  host: { class: 'block h-full' },
  templateUrl: './documents-page.html',
})
export class DocumentsPage {
  private readonly router = inject(Router);
  private readonly catalog = inject(DocumentCatalogService);

  protected readonly documents = this.catalog.documents;
  protected readonly loading = this.catalog.loading;
  protected readonly error = this.catalog.error;
  protected readonly selectedId = this.catalog.selectedId;

  constructor() {
    void this.catalog.load();
  }

  protected ask(document: DocumentOption): void {
    this.catalog.select(document.id);
    void this.router.navigate(['/chat']);
  }

  protected retry(): void {
    void this.catalog.load(true);
  }

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(new Date(value));
  }
}
