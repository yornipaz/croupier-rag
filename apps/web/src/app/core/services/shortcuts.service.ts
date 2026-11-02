import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ShortcutsService {
  private readonly openState = signal(false);
  readonly open = this.openState.asReadonly();

  toggle(): void {
    this.openState.update((value) => !value);
  }

  close(): void {
    this.openState.set(false);
  }
}
