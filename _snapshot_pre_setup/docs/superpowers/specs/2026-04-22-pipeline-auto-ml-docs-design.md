# Diseño: Pipeline CLI + Auto-ML Loop + Documentación (HTML/PDF)

## Objetivo (actualizado)

Unificar el flujo de trabajo en un único CLI cross-platform (Windows PowerShell + Linux server) para:

1) Descargar/actualizar histórico de mercados (principalmente crypto)
2) Ejecutar pipelines completos (scan → backtest → dataset → train → calibrate → report) incorporando `TIMING_MODE=expansion` por defecto
3) Operar un loop de autoalimentación ML (con control de versiones/manifest)
4) Generar documentación técnica (HTML y “PDF-like” vía HTML) de comandos y artefactos

## Requisitos

- Sin dependencias nuevas: usar `argparse` (stdlib) y librerías ya presentes.
- Comandos de una línea compatibles con PowerShell.
- Paths consistentes con el repo actual (usa `settings.DATA_DIR`).
- No escribir secretos en logs.
- Artefactos reproducibles: manifests con inputs/outputs y hashes.

## No-Goals (MVP)

- Programación de jobs (cron/systemd/Task Scheduler) queda como docs + ejemplos, no automatización completa.
- Entrenamiento deep learning: se limita a los modelos ya soportados (logreg/stack).
- UI/Frontend: fuera de alcance.

## CLI propuesto

Archivo principal:

- `scripts/naira_pipeline.py`

Subcomandos (MVP):

- `download` : descarga histórico desde provider (binance/ccxt) para símbolos/timeframes.
- `update` : incremental (si el provider lo permite; si no, re-descarga con ventana).
- `scan` : corre scan batch (contra motor local o vía API).
- `backtest` : corre backtests batch y guarda reportes.
- `dataset build` : llama al endpoint o función existente para construir dataset.
- `model train` : entrena modelo por símbolo o stack (usa endpoints existentes).
- `model calibrate` : calibra thresholds/curvas (usa endpoints existentes).
- `report` : compila reportes (json/csv/markdown) con métricas clave.
- `docs` : genera documentación HTML (y opcional export “PDF-like”).

Subcomandos “utility”:

- `env` : imprime variables importantes y rutas.
- `universe` : imprime universo de símbolos por asset+tramo.

## Estructura de artefactos

Base: `backend/data/`

- History: `backend/data/history/<provider>/<symbol>/<timeframe>.csv`
- Reports: `backend/data/reports/<YYYY-MM-DD>/<job_id>/...`
- Manifests: `backend/data/reports/<YYYY-MM-DD>/<job_id>/manifest.json`
- Docs generated: `docs/generated/pipeline.html` y `docs/generated/pipeline.pdf.html`

## Manifests (reproducibilidad)

Cada comando que escribe outputs genera manifest:

Campos mínimos:
- `job_id`, `created_at`, `command`, `args`
- `inputs`: list de archivos leídos + sha256 + size
- `outputs`: list de archivos escritos + sha256 + size
- `git`: branch + `HEAD` (si hay git disponible)
- `env`: provider, timeframes, symbols_count, etc.

## Auto-ML loop (MVP seguro)

Secuencia recomendada:

1) `download` o `update` (histórico)
2) `dataset build` (features + labels)
3) `model train` (por símbolo o stack)
4) `model calibrate` (umbral y calibración)
5) `scan --mode multi --timing-mode expansion` para producir señales “ejecutables” (gates ya aplican)
6) `report` (resumen + drift simple + buckets por timing/entry_kind)

## Documentación

Generar HTML auto-contenido (sin dependencias externas):

- Tabla de comandos y ejemplos (PowerShell y Linux)
- Rutas de archivos producidos
- Troubleshooting (rate-limit, vacíos, permisos)
- Checklist de “primer run”

El “PDF” en MVP es HTML con CSS para impresión:
- `docs/generated/pipeline.pdf.html` (imprimible a PDF desde navegador o wkhtmltopdf si el usuario quiere)

## Testing mínimo

- Unit tests del parser/CLI:
  - parse de args por subcomando
  - paths resueltos correctamente
  - manifest writer genera sha256 y lista outputs
