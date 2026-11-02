import type { components } from './schema';

export type ChatAskRequest = components['schemas']['ChatAskRequest'];
export type ChatResponse = components['schemas']['ChatResponse'];
export type ChatSource = components['schemas']['SourceSchema'];
export type ChatImage = components['schemas']['ChatImageSchema'];
export type ChatTurn = components['schemas']['ChatTurnSchema'];
export type ChatDebug = components['schemas']['ChatDebugSchema'];
export type ChatDebugHit = components['schemas']['ChatDebugHitSchema'];
export type DocumentResource = components['schemas']['DocumentSchema'];

export interface ChatApiContract {
  ask(request: ChatAskRequest, options?: { debug?: boolean }): Promise<ChatResponse>;
}
