# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SASP (Sistema de Auditoría de Servicios Personales)** is a web-based audit platform for the Superior Audit Office of Tlaxcala (OFS). It analyzes labor data from public employees across government entities to detect patterns, duplications, and schedule overlaps by cross-referencing employee records across multiple "quincenas" (biweekly pay periods).

The system processes Excel files containing employee data from different government entities (state agencies and municipalities), identifies employees working in multiple entities during the same pay period, and generates audit reports for compliance review.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source venv/bin/activate  # On Linux/macOS
# or
venv\Scripts\activate     # On Windows

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
# Initialize database and seed with base data
python core/database.py

# Import catalogs (entities, municipalities, users) from Excel files
python importar_catalogos_scil.py
```

**Note:** The catalog import script expects Excel files in the `catalogos/` directory:
- `Estatales.xlsx` - State government entities
- `Municipales.xlsx` - Municipal entities
- `Usuarios_SASP_2025.xlsx` - System users

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

**Role-Based Access**: Users with `"TODOS"` in their `entes` field (like "odilia", "victor") see all entities; others only see assigned entities.

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

## Important File Locations

- **Database**: `scil.db` (SQLite, excluded from git)
- **Upload Template**: `static/Plantilla.xlsx` (downloadable Excel template for users)
- **Catalogs**: `catalogos/*.xlsx` (entity and user master data)
- **Templates**: `templates/*.html` (Jinja2 templates for all views)
- **Logs**: Application uses Python logging (INFO level by default)

## Environment Variables

- `SCIL_DB`: Path to SQLite database file (default: `scil.db`)
- `PORT`: Server port (default: 4050)

## Excel File Format

Input files must follow this structure:
- **Sheet name**: Entity name (matched against catalog)
- **Required columns**: `RFC`, `NOMBRE`, `PUESTO`, `FECHA_ALTA`, `FECHA_BAJA`
- **Optional columns**: `QNA1` through `QNA24` (biweekly period indicators)
- **Optional column**: `TOT_PERC` (total compensation)

Values in QNA columns indicate employment status:
- Non-empty/non-zero/not "NA" = active in that period
- Empty/0/"NA" = inactive

## Authentication

Default hardcoded users (for initial setup):
- Username: `odilia` / Password: `odilia2025` (full access)
- Username: `felipe` / Password: `felipe2025` (full access)

**Security Note**: Passwords are SHA-256 hashed before storage. Production deployment should use stronger authentication.

## Export Formats

Two export modes available via routes:
- `/exportar_por_ente?ente=<name>`: Single-entity Excel export
- `/exportar_general`: All entities with summary sheet
- Both support `?formato=json` for API access

Exported columns: RFC, Nombre, Puesto, Fecha Alta, Fecha Baja, Total Percepciones, Ente Origen, Entes Incompatibilidad, Quincenas, Estatus, Solventación

## Testing Approach

No automated test suite currently exists. Manual testing workflow:
1. Start server: `python app.py`
2. Navigate to http://localhost:4050
3. Login with test credentials
4. Upload sample Excel file (use `static/Plantilla.xlsx` as template)
5. Verify results appear in `/resultados`
6. Test solventación workflow on individual RFC
7. Test export functionality

## Production Deployment

The system is deployed at https://scil.omar-xyz.shop using:
- Gunicorn as WSGI server (see requirements.txt)
- Certbot for HTTPS (see requirements.txt)
- Environment-specific database path via `SCIL_DB`

## Code Style Notes

- Heavy use of helper functions with `_` prefix for internal utilities
- Spanish naming in database/domain layer (e.g., `entes`, `quincenas`, `solventaciones`)
- Text sanitization uses uppercase + accent removal for matching
- LRU caching (`@lru_cache`) used for frequently accessed catalog data
