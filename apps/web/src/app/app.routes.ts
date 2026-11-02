import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    redirectTo: 'chat',
  },
  {
    path: 'chat',
    loadComponent: () => import('./features/chat/chat-page').then((module) => module.ChatPage),
  },
  {
    path: 'documents',
    loadComponent: () =>
      import('./features/documents/documents-page').then((module) => module.DocumentsPage),
  },
  {
    path: '**',
    redirectTo: 'chat',
  },
];
