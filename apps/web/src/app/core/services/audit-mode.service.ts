import { Injectable, effect, signal } from '@angular/core';

const STORAGE_KEY = 'croupier.auditor';

@Injectable({ providedIn: 'root' })
export class AuditModeService {
  private readonly enabledState = signal(localStorage.getItem(STORAGE_KEY) === 'true');
  readonly enabled = this.enabledState.asReadonly();

  constructor() {
    effect(() => {
      localStorage.setItem(STORAGE_KEY, String(this.enabledState()));
    });
  }

  toggle(): void {
    this.enabledState.update((value) => !value);
  }
}
