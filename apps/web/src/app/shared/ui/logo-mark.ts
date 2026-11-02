import { Component, input } from '@angular/core';

@Component({
  selector: 'app-logo-mark',
  template: `
    <span
      class="inline-flex items-center justify-center rounded-full border border-accent/40 bg-accent-soft/30 text-accent shadow-sm"
      [style.width.px]="size()"
      [style.height.px]="size()"
      aria-hidden="true"
    >
      <svg
        [attr.width]="size() * 0.56"
        [attr.height]="size() * 0.56"
        viewBox="0 0 32 32"
        fill="none"
      >
        <path
          d="M22.4 7.9c-1.8-1.6-4.1-2.5-6.7-2.5-5.4 0-9.1 4.1-9.1 10s3.7 10 9.2 10c2.7 0 5-1 6.8-2.8l-2.4-2.8c-1.1 1.2-2.6 1.9-4.2 1.9-3.1 0-5-2.4-5-6.2 0-3.8 1.9-6.1 5-6.1 1.6 0 3 .6 4.2 1.8z"
          fill="currentColor"
        />
        <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-opacity=".35" stroke-width="1" />
      </svg>
    </span>
  `,
})
export class LogoMark {
  readonly size = input(32);
}
