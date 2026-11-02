import { InjectionToken, inject } from '@angular/core';

import { environment } from '../../../environments/environment';
import { HttpChatApi } from './http-chat-api';
import { MockChatApi } from './mock-chat-api';
import type { ChatApiContract } from './chat-api.types';

export {
  type ChatApiContract,
  type ChatAskRequest,
  type ChatDebug,
  type ChatDebugHit,
  type ChatImage,
  type ChatResponse,
  type ChatSource,
  type ChatTurn,
  type DocumentResource,
} from './chat-api.types';

export const ChatApi = new InjectionToken<ChatApiContract>('ChatApi', {
  providedIn: 'root',
  factory: () => inject(environment.useMock ? MockChatApi : HttpChatApi),
});
