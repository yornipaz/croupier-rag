import { Component, OnDestroy, computed, input, signal } from '@angular/core';

import type { ChatImage } from '../../../core/api/chat-api.types';
import { FocusTrap } from '../../../shared/ui/focus-trap';
import { Icon } from '../../../shared/ui/icon';

@Component({
  selector: 'app-figure-viewer',
  imports: [FocusTrap, Icon],
  host: {
    '(document:keydown.escape)': 'onEscape()',
  },
  templateUrl: './figure-viewer.html',
  styleUrl: './figure-viewer.css',
})
export class FigureViewer implements OnDestroy {
  readonly image = input.required<ChatImage>();

  protected readonly open = signal(false);
  protected readonly loading = signal(false);
  protected readonly failed = signal(false);
  protected readonly hasPageCrop = computed(() =>
    /\/documents\/[^/]+\/pages\/\d+\/crop/.test(this.image().url),
  );
  protected readonly viewerSrc = computed(() => this.cropUrl() ?? this.image().url);
  protected readonly cropUrl = computed(() => {
    if (!this.hasPageCrop()) {
      return null;
    }
    try {
      const url = new URL(this.image().url, window.location.origin);
      url.searchParams.set('highlight', 'true');
      return url.toString();
    } catch {
      return null;
    }
  });

  private previousOverflow = '';

  openViewer(): void {
    this.open.set(true);
    this.failed.set(false);
    this.loading.set(this.cropUrl() !== null);
    this.previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }

  close(): void {
    this.open.set(false);
    this.loading.set(false);
    this.failed.set(false);
    document.body.style.overflow = this.previousOverflow;
  }

  ngOnDestroy(): void {
    if (this.open()) {
      document.body.style.overflow = this.previousOverflow;
    }
  }

  protected onEscape(): void {
    if (this.open()) {
      this.close();
    }
  }

  protected onImageLoad(): void {
    this.loading.set(false);
  }

  protected onImageError(): void {
    this.loading.set(false);
    this.failed.set(true);
  }
}
