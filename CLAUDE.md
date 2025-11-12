# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SASP (Sistema de Auditoría de Servicios Personales)** is a web-based audit platform for the Superior Audit Office of Tlaxcala (OFS). It analyzes labor data from public employees across government entities to detect patterns, duplications, and schedule overlaps by cross-referencing employee records across multiple "quincenas" (biweekly pay periods).

The system processes Excel files containing employee data from different government entities (state agencies and municipalities), identifies employees working in multiple entities during the same pay period, and generates audit reports for compliance review.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Development mode (default port 4050)
python app.py

# Production mode with Gunicorn
gunicorn --bind 0.0.0.0:4050 --workers 4 app:app
```

### Database Operations
```bash
# Initialize database schema and seed with default users
python core/database.py

# Import entity/user catalogs from catalogos/*.xlsx
python importar_catalogos_scil.py
```

Catalog files expected in `catalogos/`: `Estatales.xlsx`, `Municipales.xlsx`, `Usuarios_SASP_2025.xlsx`

## Architecture

### Core Components

**Flask Application (app.py)**
- Main web server and route handlers
- Session-based authentication with entity-level access control
- Handles file uploads, data processing, and report exports
- Uses SQLite database (`scil.db`) for persistence

**Database Manager (core/database.py)**
- SQLite database abstraction layer
- Manages 5 main tables: `laboral`, `solventaciones`, `usuarios`, `entes`, `municipios`
- Provides normalization functions for entity names/codes
- Handles deduplication using content hashing

**Data Processor (core/data_processor.py)**
- Parses Excel files with labor data (one sheet per entity)
- Performs "cruce quincenal" (biweekly cross-checking) to detect employees active in multiple entities during the same pay period
- Expected Excel columns: `RFC`, `NOMBRE`, `PUESTO`, `FECHA_ALTA`, `FECHA_BAJA`, plus `QNA1` through `QNA24` (for up to 24 biweekly periods)
- Generates structured results with employee duplications and incompatibilities

### Data Flow

1. **Upload Phase**: Users upload Excel files containing employee data from various entities
2. **Processing Phase**: `DataProcessor` reads sheets (one per entity), normalizes entity names against catalog, extracts employee records
3. **Cross-checking Phase**: System identifies employees working in multiple entities during same quincena (biweekly period)
4. **Storage Phase**: Results stored in `laboral` table with content-based deduplication
5. **Review Phase**: Auditors review findings, mark status (Solventado/No Solventado), add comments
6. **Export Phase**: Generate Excel reports filtered by entity or comprehensive general report

### Key Architectural Patterns

**Entity Normalization**: Entity names can be provided as `clave` (ENTE_00001), `siglas` (SEPE), or full name. The system normalizes these to a canonical `clave` for consistency.

**RFC-Centric Grouping**: All employee records are grouped by RFC (Mexican tax ID). Cross-entity analysis happens at the RFC level across quincenas.

**State Management**: Employee resolution status is tracked per RFC and per entity in the `solventaciones` table, allowing different resolutions for the same employee across different entities.

**Content Hashing**: Uses SHA-256 hashing of JSON-serialized results to prevent duplicate storage of identical analysis results.

**Role-Based Access**: Users with `"TODOS"` in their `entes` field (like "odilia", "luis", "felipe") see all entities; others only see assigned entities.

## Database Schema

**laboral**: Stores analysis results for employees with potential duplications
- `rfc`: Employee tax ID
- `datos`: JSON blob containing full analysis (entes, registros, quincenas, etc.)
- `hash_firma`: SHA-256 hash for deduplication
- `tipo_analisis`: Analysis type (CRUCE_ENTRE_ENTES_QNA, SIN_DUPLICIDAD)

**solventaciones**: Tracks resolution status per RFC per entity
- `rfc`, `ente`: Composite key
- `estado`: Status (Solventado, No Solventado, Sin valoración)
- `comentario`: Auditor's resolution notes

**entes**: Government entities catalog (state-level)
- `clave`: Primary key (e.g., ENTE_00001)
- `siglas`: Short acronym (e.g., SEPE)
- `nombre`: Full entity name
- `clasificacion`, `ambito`: Entity type metadata

**municipios**: Municipal entities catalog (similar structure to entes)

**usuarios**: System users with entity-based access control
- `entes`: Comma-separated list of entity codes or "TODOS" for full access

## Key Application Routes

- `/` - Login page (GET/POST)
- `/dashboard` - Main dashboard with upload interface
- `/upload_laboral` - Process Excel file uploads (POST)
- `/resultados` - View analysis results (filtered by user's entity access)
- `/resultados/<rfc>` - Detailed employee view with cross-entity activity
- `/solventacion/<rfc>` - Resolution workflow for marking status per entity
- `/actualizar_estado` - AJAX endpoint for updating resolution status (POST)
- `/exportar_por_ente?ente=<name>` - Single-entity Excel export
- `/exportar_general` - Comprehensive Excel export with summary sheet
- `/catalogos` - View loaded entities and municipalities

## Important File Locations

- **Database**: `scil.db` (SQLite, git-ignored)
- **Upload Template**: `static/Plantilla.xlsx` (downloadable template for users)
- **Catalogs**: `catalogos/*.xlsx` (master data for entities/users)
- **Templates**: `templates/*.html` (Jinja2 templates)

## Environment Variables

- `SCIL_DB`: Path to SQLite database file (default: `scil.db`)
- `PORT`: Server port (default: 4050)

## Excel File Format

Input files (see `static/Plantilla.xlsx` for template):
- **Sheet name**: Entity identifier (clave, sigla, or full name from catalog)
- **Required columns**: `RFC`, `NOMBRE`, `PUESTO`, `FECHA_ALTA`, `FECHA_BAJA`
- **Optional columns**: `QNA1`-`QNA24` (biweekly period flags), `TOT_PERC` (total compensation)
- **QNA values**: Non-empty/non-zero/"not NA" = active; empty/0/"NA" = inactive

## Authentication

Session-based authentication with SHA-256 password hashing. Default users (seeded by `core/database.py`):
- `odilia` / `odilia2025` (full access)
- `felipe` / `felipe2025` (full access)

Additional users imported via `importar_catalogos_scil.py` from `Usuarios_SASP_2025.xlsx`.

## Export Formats

Excel exports via `/exportar_por_ente?ente=<name>` (single entity) or `/exportar_general` (all entities with summary). Both support `?formato=json`.

Columns: RFC, Nombre, Puesto, Fecha Alta, Fecha Baja, Total Percepciones, Ente Origen, Entes Incompatibilidad, Quincenas, Estatus, Solventación

## Testing

No automated test suite. Manual testing: Start server (`python app.py`), login at http://localhost:4050, upload Excel file using `static/Plantilla.xlsx` template, verify results, test solventación workflow, and validate exports.

## Production Deployment

Deployed at https://scil.omar-xyz.shop with Gunicorn WSGI server and Certbot HTTPS. Use `SCIL_DB` environment variable for production database path.

## Code Conventions

- **Helper functions**: Prefix with `_` for internal utilities (e.g., `_sanitize_text`, `_ente_match`)
- **Domain naming**: Spanish terms in database/domain layer (`entes`, `quincenas`, `solventaciones`)
- **Text normalization**: Always uppercase + accent removal for entity matching
- **Caching**: `@lru_cache` decorators on catalog lookups (`_entes_cache()`)
- **Entity identifiers**: Functions accept clave/sigla/nombre and normalize to canonical `clave` via `normalizar_ente_clave()`
