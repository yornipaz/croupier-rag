import type { components } from './schema';

export type DocumentResource = components['schemas']['DocumentSchema'];
export type UploadDocumentResponse = components['schemas']['UploadDocumentResponse'];
export type JobEvent = components['schemas']['JobSchema'];
export type JobStatus = JobEvent['status'];
