import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ShellStateService {
  private readonly collapsedState = signal(false);
  private readonly mobileOpenState = signal(false);

  readonly sidebarCollapsed = this.collapsedState.asReadonly();
  readonly mobileSidebarOpen = this.mobileOpenState.asReadonly();

  toggleSidebar(): void {
    this.collapsedState.update((value) => !value);
  }

  openMobile(): void {
    this.mobileOpenState.set(true);
  }

  closeMobile(): void {
    this.mobileOpenState.set(false);
  }

  toggleMobile(): void {
    this.mobileOpenState.update((value) => !value);
  }
}
