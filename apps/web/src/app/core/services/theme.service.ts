import { Injectable, effect, signal } from '@angular/core';

const STORAGE_KEY = 'croupier.theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly darkState = signal(this.initialPreference());
  readonly dark = this.darkState.asReadonly();

  constructor() {
    effect(() => {
      const dark = this.darkState();
      document.documentElement.classList.toggle('dark', dark);
      document.documentElement.dataset['theme'] = dark ? 'dark' : 'light';
      localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light');
    });
  }

  toggle(): void {
    this.darkState.update((value) => !value);
  }

  private initialPreference(): boolean {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'dark') {
      return true;
    }
    if (stored === 'light') {
      return false;
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true;
  }
}
