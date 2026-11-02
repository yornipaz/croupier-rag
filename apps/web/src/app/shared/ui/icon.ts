import { Component, input } from '@angular/core';

export type IconName =
  | 'menu'
  | 'panel-left'
  | 'plus'
  | 'chat'
  | 'document'
  | 'sun'
  | 'moon'
  | 'audit'
  | 'send'
  | 'spark'
  | 'shield'
  | 'refresh'
  | 'check'
  | 'expand'
  | 'arrow-up-right'
  | 'arrow-right'
  | 'chevron-left'
  | 'chevron-right'
  | 'close'
  | 'clock'
  | 'layers'
  | 'warning'
  | 'external';

@Component({
  selector: 'app-icon',
  host: { class: 'inline-flex shrink-0' },
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      [attr.stroke-width]="strokeWidth()"
      stroke="currentColor"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @switch (name()) {
        @case ('menu') {
          <path d="M4 6h16M4 12h16M4 18h16" />
        }
        @case ('panel-left') {
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M9 4v16" />
        }
        @case ('plus') {
          <path d="M12 5v14M5 12h14" />
        }
        @case ('chat') {
          <path d="M21 12a8 8 0 0 1-8 8H6l-3 2v-5a8 8 0 1 1 18-5Z" />
          <path d="M8 12h.01M12 12h.01M16 12h.01" />
        }
        @case ('document') {
          <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
          <path d="M14 3v6h6M8 13h8M8 17h6" />
        }
        @case ('sun') {
          <circle cx="12" cy="12" r="4" />
          <path
            d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"
          />
        }
        @case ('moon') {
          <path d="M20.5 14.4A8.5 8.5 0 0 1 9.6 3.5a8.5 8.5 0 1 0 10.9 10.9Z" />
        }
        @case ('audit') {
          <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
          <circle cx="12" cy="12" r="2.7" />
        }
        @case ('send') {
          <path d="M22 2 11 13" />
          <path d="M22 2 15 22l-4-9-9-4Z" />
        }
        @case ('spark') {
          <path d="m12 3 1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z" />
          <path d="M19 15l.7 1.8L21.5 18l-1.8.7L19 20.5l-.7-1.8L16.5 18l1.8-.7Z" />
        }
        @case ('shield') {
          <path d="M12 3l7 3v5c0 4.3-3 7.4-7 9-4-1.6-7-4.7-7-9V6z" />
          <path d="M9 12l2 2 4-4" />
        }
        @case ('refresh') {
          <path d="M20 12a8 8 0 1 1-2.3-5.7" />
          <path d="M20 4v5h-5" />
        }
        @case ('check') {
          <path d="m5 12 4 4L19 6" />
        }
        @case ('expand') {
          <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />
          <path d="m3 8 5-5M21 8l-5-5M3 16l5 5M21 16l-5 5" />
        }
        @case ('arrow-up-right') {
          <path d="M7 17 17 7M8 7h9v9" />
        }
        @case ('arrow-right') {
          <path d="M5 12h14M13 6l6 6-6 6" />
        }
        @case ('chevron-left') {
          <path d="m15 18-6-6 6-6" />
        }
        @case ('chevron-right') {
          <path d="m9 18 6-6-6-6" />
        }
        @case ('close') {
          <path d="M6 6l12 12M18 6 6 18" />
        }
        @case ('clock') {
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        }
        @case ('layers') {
          <path d="m12 3 9 5-9 5-9-5Z" />
          <path d="m3 13 9 5 9-5" />
        }
        @case ('warning') {
          <path
            d="M10.3 4.2 2.7 18a1.7 1.7 0 0 0 1.5 2.5h15.6a1.7 1.7 0 0 0 1.5-2.5L13.7 4.2a1.9 1.9 0 0 0-3.4 0Z"
          />
          <path d="M12 9v4M12 17h.01" />
        }
        @case ('external') {
          <path d="M14 3h7v7M10 14 21 3" />
          <path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" />
        }
      }
    </svg>
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly size = input(18);
  readonly strokeWidth = input(1.8);
}
