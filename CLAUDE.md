# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SASP (Sistema de Auditoría de Servicios Personales) / SCIL is an institutional audit platform for analyzing labor data from public employees across government entities in Tlaxcala, Mexico. Built for the Superior Audit Office (OFS).

**Core Purpose**: Detect schedule conflicts, duplicate employee records, and overlapping work periods (quincenas/QNAs) across different government entities for compliance auditing.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Development mode (with debug enabled)
python3 app.py
# Default: http://0.0.0.0:4050

# Production mode (using Gunicorn)
gunicorn -w 4 -b 0.0.0.0:4050 app:app
```

### Database Operations
```bash
# Initialize database with base data (users, entes catalog)
python3 -c "from core.database import DatabaseManager; db = DatabaseManager('scil.db'); db.poblar_datos_iniciales()"

# Access SQLite database directly
sqlite3 scil.db
```

## Architecture

### Application Structure

**Flask Monolith Pattern**: Single-file Flask application (`app.py`) with modular core components.

```
app.py                    # Main Flask app with all routes and business logic
├── core/
│   ├── database.py       # DatabaseManager - all SQLite operations
│   └── data_processor.py # DataProcessor - Excel file parsing and QNA conflict detection
├── templates/            # Jinja2 HTML templates
├── static/              # CSS, JS, template files
├── catalogos/           # Excel catalogs (Estatales.xlsx, Municipales.xlsx, Usuarios_SASP_2025.xlsx)
├── uploads/             # Temporary file storage
└── scil.db              # SQLite database (main data store)
```

### Key Components

**1. DatabaseManager** (`core/database.py`)
- Single source of truth for all database operations
- Uses SQLite with `sqlite3.Row` factory for dict-like access
- Main tables:
  - `registros_laborales`: Individual employee records (unique by RFC+ENTE)
  - `solventaciones`: Audit status and comments per RFC+ENTE
  - `entes` / `municipios`: Government entity catalogs
  - `usuarios`: User authentication and permissions

**2. DataProcessor** (`core/data_processor.py`)
- Processes Excel files with employee data
- Each sheet = one government entity (sheet name must match entity catalog)
- Detects QNA (biweekly period) conflicts across entities
- Expected columns: `RFC`, `NOMBRE`, `PUESTO`, `FECHA_ALTA`, `FECHA_BAJA`, `QNA1-QNA24`, `TOT_PERC`

**3. Conflict Detection Logic** (critical for auditing)
- An employee has a conflict when their RFC appears in multiple entities during the SAME quincena
- QNAs are biweekly periods (24 per year): QNA1, QNA2, ..., QNA24
- Conflict = intersection of active QNAs across different entities
- Non-conflict = same RFC in multiple entities but NO overlapping QNAs

### Data Flow

1. **Upload** → User uploads Excel files via `/upload_laboral`
2. **Parse** → `DataProcessor.extraer_registros_individuales()` reads all sheets
3. **Store** → `DatabaseManager.guardar_registros_individuales()` inserts/updates records
4. **Detect** → `DatabaseManager.obtener_cruces_reales()` finds QNA intersections
5. **Filter** → `_filtrar_duplicados_reales()` in app.py removes false positives
6. **Display** → `/resultados` shows conflicts grouped by entity

### Permission System

**Superusers** (hardcoded in app.py:215-218):
- Users: `odilia`, `luis`, `felipe`
- Access: ALL entities and municipalities

**Regular Users**:
- Permissions stored in `usuarios.entes` (comma-separated)
- Can use special keywords:
  - `TODOS`: Access all entities and municipalities
  - `TODOS LOS ENTES`: Only state entities
  - `TODOS LOS MUNICIPIOS`: Only municipalities
  - Specific entity: By clave, sigla, or nombre (e.g., `ENTE_1_2`, `SEGOB`)

Permission logic in `_allowed_all()` and `_ente_match()` functions.

### Entity Normalization

**Critical Pattern**: The system has TWO entity catalogs (`entes` and `municipios`) but treats them as unified:

- Each entity has: `num` (hierarchical order), `clave` (unique key), `siglas` (abbreviation), `nombre` (full name)
- Normalization functions:
  - `normalizar_ente_clave()`: Returns unique CLAVE for any input (sigla/nombre/clave)
  - `normalizar_ente()`: Returns full NOMBRE
  - Always normalize before database operations to ensure consistency

**Cache Pattern**: `_entes_cache()` uses `@lru_cache` to avoid repeated DB queries.

## Important Implementation Details

### QNA (Quincena) Handling

- QNAs are stored as JSON in `registros_laborales.qnas`: `{"QNA1": value, "QNA2": value, ...}`
- Active status determined by `_es_activo()`: any non-empty, non-zero, non-"NO" value
- Must validate exactly 24 QNAs per file (QNA1-QNA24)
- Ordering filter: `ordenar_quincenas` Jinja2 filter sorts QNA1, QNA2, ..., QNA10, QNA11 correctly

### Solventaciones (Audit Status)

- Three states: "Solventado", "No Solventado", "Sin valoración"
- Stored PER entity (RFC + ENTE combination)
- Can have different status for same RFC across entities
- Fields: `estado`, `comentario`, `catalogo` (predefined reasons), `otro_texto` (custom text)

### Export Logic

**Critical**: `_construir_filas_export()` must:
1. Calculate ONLY QNAs with real intersection (not all QNAs)
2. Filter out "N/A" quincenas (no temporal overlap)
3. Load real comments from `solventaciones` table (not from cache)
4. Format: "Activo en Todo el Ejercicio" if all 24 QNAs overlap

### Authentication

- Passwords stored as SHA256 hashes
- Session-based authentication with Flask sessions
- Middleware: `verificar_autenticacion()` runs before every request
- Exempt endpoints: `login`, `static`

## Common Patterns

### Working with Entities

```python
# Always normalize before DB operations
clave_ente = db_manager.normalizar_ente_clave(user_input)

# Display to user
display_name = _ente_display(clave_ente)

# Check permissions
if _ente_match(user_ente, [target_ente]):
    # User has access
```

### Processing Excel Files

```python
# DataProcessor expects file-like objects or FileStorage
files = request.files.getlist("files")
registros, alertas = data_processor.extraer_registros_individuales(files)

# Always check alertas for:
# - "ente_no_encontrado": Sheet name not in catalog
# - "columnas_faltantes": Missing required columns
```

### Database Transactions

All DB operations use context managers implicitly via `_connect()`:
```python
conn = db_manager._connect()
cur = conn.cursor()
# ... operations ...
conn.commit()
conn.close()
```

## Configuration

- Database path: `SCIL_DB` environment variable (default: `scil.db`)
- Port: `PORT` environment variable (default: 4050)
- Secret key: Hardcoded as `"ofs_sasp_2025"` (change for production)
- Debug mode: Enabled in `app.run()` for development

## Testing Considerations

- Test files should be Excel (.xlsx) with valid entity names as sheet names
- Entity names must match entries in `entes` or `municipios` tables
- Use `catalogos/` directory for reference catalogs
- Template available at `/descargar-plantilla` route

## Critical Business Rules

1. **No false positives**: Only report conflicts with actual QNA intersections
2. **Entity hierarchy**: Respect `num` field for ordering (1.2.3 before 1.10)
3. **RFC uniqueness**: RFC+ENTE combination must be unique (enforced at DB level)
4. **Permission isolation**: Users must never see entities they lack permission for
5. **Audit trail**: All solventaciones must track `actualizado` timestamp
