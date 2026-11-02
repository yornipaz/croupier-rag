# ADR 0002 — Recuperación híbrida con RRF y BM25 de FastEmbed

- **Estado:** aceptado
- **Fecha:** 2026-11-01

## Contexto

Los manuales técnicos mezclan lenguaje natural con términos exactos (referencias, códigos de
modelo, nombres de conectores). Una búsqueda puramente densa recupera bien paráfrasis, pero puede
perder coincidencias literales; una búsqueda puramente léxica falla ante sinónimos. Necesitamos
combinar ambas señales sin introducir otro servicio ni un modelo de re-ranking pesado.

## Decisión

1. **Denso + sparse en Qdrant.** Cada chunk se indexa con dos vectores nombrados: `dense`
   (FastEmbed multilingüe) y `sparse` (BM25). El sparse usa `Modifier.IDF` en Qdrant para que el
   IDF se calcule sobre el corpus indexado y no sobre un vocabulario fijo.
2. **Fusión RRF en el servidor.** `hybrid_search` envía dos `Prefetch` (uno por vector) y
   `FusionQuery(fusion=Fusion.RRF)`. RRF combina rankings, no puntuaciones crudas, así que no exige
   calibrar la escala de similitud coseno frente a BM25. Es robusto cuando cambia el modelo denso o
   el tamaño del corpus.
3. **BM25 con FastEmbed.** `SparseTextEmbedding(model_name="Qdrant/bm25", language="spanish")`
   aporta stemming y stopwords en español, funciona en local, no requiere red en query time una vez
   cacheado y produce vectores sparse compatibles con Qdrant. Evita añadir Elasticsearch/OpenSearch
   solo para léxico.
4. **Ranks para debug.** Qdrant devuelve el score RRF fusionado, pero no los ranks componentes. Para
   poder explicar cada resultado, `hybrid_search` ejecuta en un único `query_batch_points` la consulta
   fusionada y dos consultas densa/sparse; con ellas calcula `denseRank` y `sparseRank` sin introducir
   lógica de fusión en la aplicación.

## Consecuencias

- La recuperación es una sola llamada HTTP a Qdrant (batch de tres queries) y mantiene el ranking
  final en el servidor.
- El coste es calcular dos prefetch adicionales por búsqueda. Es aceptable para manuales y permite
  mostrar el debug; si el coste importa, se puede separar el modo debug en otra ruta.
- BM25 depende del idioma configurado (`SPARSE_EMBEDDING_LANGUAGE`, por defecto `spanish`). Cambiarlo
  exige reindexar la colección.
- RRF no produce puntuaciones interpretables como probabilidad; el umbral defensivo debe aplicarse
  sobre el score fusionado (o sobre el mejor score denso) de forma explícita en retrieval.
