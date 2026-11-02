import { Component, inject } from '@angular/core';

import { DocumentCatalogService } from '../../core/services/document-catalog.service';
import { Icon } from '../../shared/ui/icon';
import { DocumentsPanel } from './components/documents-panel';

@Component({
  selector: 'app-documents-page',
  imports: [DocumentsPanel, Icon],
  host: { class: 'block h-full' },
  templateUrl: './documents-page.html',
})
export class DocumentsPage {
  private readonly catalog = inject(DocumentCatalogService);
  protected readonly documents = this.catalog.documents;
}
