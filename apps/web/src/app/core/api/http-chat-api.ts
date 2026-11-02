import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import type { ChatApiContract, ChatAskRequest, ChatResponse } from './chat-api.types';

@Injectable({ providedIn: 'root' })
export class HttpChatApi implements ChatApiContract {
  private readonly http = inject(HttpClient);

  async ask(request: ChatAskRequest, options?: { debug?: boolean }): Promise<ChatResponse> {
    const url = `${environment.apiBaseUrl}${environment.apiPrefix}/chat/ask`;
    try {
      const response = await firstValueFrom(
        this.http.post<ChatResponse>(url, request, {
          params: options?.debug ? { debug: true } : {},
        }),
      );
      return {
        ...response,
        images: response.images.map((image) => ({
          ...image,
          url: this.absoluteUrl(image.url),
        })),
      };
    } catch (error) {
      throw this.toUserError(error);
    }
  }

  private absoluteUrl(url: string): string {
    if (/^https?:\/\//i.test(url) || url.startsWith('data:')) {
      return url;
    }
    const base = environment.apiBaseUrl
      ? new URL(environment.apiBaseUrl, window.location.origin).toString().replace(/\/$/, '')
      : window.location.origin;
    if (url.startsWith('/')) {
      return `${base}${url}`;
    }
    return new URL(url, `${base}/`).toString();
  }

  private toUserError(error: unknown): Error {
    if (error instanceof HttpErrorResponse) {
      const payload = error.error as { error?: { message?: string } } | null | undefined;
      if (error.status === 0) {
        return new Error('No se pudo conectar con la API. Revisa que el backend esté levantado.');
      }
      if (payload?.error?.message) {
        return new Error(payload.error.message);
      }
      return new Error(`La consulta falló con HTTP ${error.status}.`);
    }
    return error instanceof Error ? error : new Error('La consulta falló.');
  }
}
