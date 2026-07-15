# Lazyreader web application

The Vite build is emitted to `web/dist/`. The Python wheel must package that
directory unchanged and serve `index.html` as the fallback for `/library`,
`/read/:id`, and `/settings/storage`. Asset URLs are rooted at the runtime
origin.

## HTTP contract

- `GET /api/articles` → `{ articles: ArticleSummary[] }`
- `POST /api/articles` with `{ source_url, url?, markdown? }`
- `GET /api/articles/:id` → `{ article, job }`
- `POST /api/articles/:id/trash`, `/restore`, `/retry`
- `DELETE /api/articles/:id` permanently purges a trashed article
- `GET /api/articles/:id/events` sends a snapshot-first SSE stream
- `GET /api/articles/:id/timings` returns the ready audio manifest unless the
  manifest or `timings_url` is included in the article response

The client accepts snake-case persisted records and camel-case fixtures. A
ready article provides either an inline manifest or an audio URL plus timing
manifest URL. The timing manifest contains `audio`, `duration`, `revision`, and
monotonic `words: [{ index, text, start, end }]`.

`Play` stays disabled until the entire revisioned audio response has entered
Cache Storage and the browser can decode it. Pipeline progress and browser
download progress are intentionally separate.
