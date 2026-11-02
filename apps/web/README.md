# Croupier Web

Interfaz Angular 22 para consultar manuales técnicos con respuestas trazables, fuentes e imágenes.

## Desarrollo

```bash
npm install
npm start
```

Abre `http://localhost:4200/chat`.

En desarrollo `src/environments/environment.ts` tiene `useMock: true`: la UI usa
`MockChatApi`, con latencia simulada, una respuesta con fuentes/imagen y otra con
estado "sin información suficiente". No necesita backend para demostrar el flujo.

## API real

- `environment.production.ts` usa `useMock: false`.
- `apiBaseUrl` y `apiPrefix` apuntan al backend (`http://localhost:8000/v1`). Si cambias
  `API_PREFIX` en el backend, actualiza `apiPrefix` y regenera el cliente.
- El cliente TypeScript se genera desde OpenAPI:

```bash
npm run gen:api
```

El script intenta `OPENAPI_URL`, `http://localhost:8000/openapi.json` y, si el
backend usa `API_PREFIX`, `http://localhost:8000/v1/openapi.json`.

## Calidad

```bash
npm run lint
npm run build
```

El proyecto usa Angular standalone, signals, Tailwind v4, `ngx-markdown`
(sanitizado) y componentes propios. La estructura está en:

```text
src/app/
  core/       # API, servicios de estado, shell y layout
  features/   # chat, documents, inspector
  shared/ui/  # iconos, logo y chips de fuentes
```

El lint ignora únicamente el archivo generado `src/app/core/api/schema.d.ts`.

## Nota de dependencias

`openapi-typescript` declara peer de TypeScript 5 mientras Angular 22 usa
TypeScript 6. El proyecto incluye `.npmrc` con `legacy-peer-deps=true` para que
`npm install` sea reproducible; la generación y el build se verificaron con esta
combinación.
