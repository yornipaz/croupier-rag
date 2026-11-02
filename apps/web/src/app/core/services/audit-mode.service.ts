import { Injectable, effect, signal } from '@angular/core';

const STORAGE_KEY = 'croupier.auditor';

@Injectable({ providedIn: 'root' })
export class AuditModeService {
  private readonly enabledState = signal(localStorage.getItem(STORAGE_KEY) === 'true');
  private readonly drawerOpenState = signal(false);

  readonly enabled = this.enabledState.asReadonly();
  readonly drawerOpen = this.drawerOpenState.asReadonly();

  constructor() {
    effect(() => {
      localStorage.setItem(STORAGE_KEY, String(this.enabledState()));
      if (!this.enabledState()) {
        this.drawerOpenState.set(false);
      }
    });
  }

  toggle(): void {
    this.enabledState.update((value) => {
      const next = !value;
      this.drawerOpenState.set(next);
      return next;
    });
  }

  openDrawer(): void {
    if (this.enabledState()) {
      this.drawerOpenState.set(true);
    }
  }

  closeDrawer(): void {
    this.drawerOpenState.set(false);
  }
}
