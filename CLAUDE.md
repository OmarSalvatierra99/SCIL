# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SCIL (SASP)** — Sistema de Auditoría de Servicios Personales
Personnel Services Audit System for the Superior Audit Office of Tlaxcala (OFS).

This is a Flask-based institutional audit platform that analyzes labor data from public employees across multiple government entities to detect:
- **Schedule conflicts**: Same employee working in multiple entities during the same pay periods (quincenas)
- **Data duplications**: Repeated employee records across different government entities
- **Pattern analysis**: Historical comparison and institutional reporting

**Live deployment**: https://scil.omar-xyz.shop

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (port 4050)
python app.py

# Database migration (if needed)
python migrar_bd.py
```

## Architecture

### Core Structure

```
scil/
├── app.py                          # Main Flask application
├── core/
│   ├── database.py                 # SQLite database manager
│   └── data_processor.py           # Excel processing & conflict detection
├── templates/                      # Jinja2 HTML templates
├── static/                         # CSS, JS, Plantilla.xlsx
├── catalogos/                      # Entity catalogs (Excel)
│   ├── Estatales.xlsx             # State entities catalog
│   ├── Municipales.xlsx           # Municipal entities catalog
│   └── Usuarios_SASP_2025.xlsx    # Users with permissions
├── migrar_bd.py                   # Database migration script
├── importar_catalogos_scil.py     # Import entity catalogs to DB
├── limpiar_datos.py               # Data cleanup utilities
└── scil.db                        # SQLite database (gitignored)
```

### Database Schema

**Core Tables:**
- `registros_laborales`: Individual employee records (RFC + entity unique)
  - Fields: rfc, ente, nombre, puesto, fecha_ingreso, fecha_egreso, monto, qnas (JSON)
  - Constraint: UNIQUE(rfc, ente)
- `solventaciones`: Audit status and comments per RFC+entity
  - Fields: rfc, ente, estado, comentario
- `laboral`: Legacy table (deprecated, being phased out)

**Catalog Tables:**
- `entes`: State-level government entities (using NUM hierarchical ordering)
- `municipios`: Municipal entities
- `usuarios`: User accounts with entity-level permissions

**Key Design:**
- Entity normalization: All entities have `clave` (unique key), `siglas` (abbreviation), and `nombre` (full name)
- QNA system: 24 pay periods per year (QNA1-QNA24 representing biweekly periods)
- Permission system: Users can access "TODOS" (all), specific entities, or "TODOS LOS ENTES"/"TODOS LOS MUNICIPIOS"

## Core Modules

### app.py (Main Application)

**Key Routes:**
- `GET /` - Login page
- `GET /dashboard` - Main dashboard
- `POST /upload_laboral` - Upload Excel files with employee data
- `GET /resultados` - Display conflict analysis by entity
- `GET /resultados/<rfc>` - Detailed view of specific employee
- `GET /exportar_por_ente?ente=X` - Export conflicts for specific entity
- `GET /exportar_general` - Export all conflicts
- `GET /catalogos` - View entity catalogs

**Authentication Middleware:**
- `@app.before_request` checks session authentication
- Superusers: odilia, luis, felipe (full access)
- Regular users: entity-scoped permissions

**Important Helper Functions:**
- `_allowed_all(entes_usuario)`: Determines permission scope (ALL/ENTES/MUNICIPIOS)
- `_ente_match(ente_usuario, clave_lista)`: Permission validation
- `_filtrar_duplicados_reales(resultados)`: Filters only real conflicts (QNA intersections)
- `_construir_filas_export(resultados)`: Builds export rows with conflict details

### core/database.py

**DatabaseManager** - Main DB interface:

```python
db = DatabaseManager("scil.db")

# Saving individual records (upsert by RFC+ente)
db.guardar_registros_individuales(registros)

# Query real conflicts (same RFC in multiple entities with QNA overlap)
cruces = db.obtener_cruces_reales()

# Get employee details
info = db.obtener_resultados_por_rfc(rfc)

# Audit status management
db.actualizar_solventacion(rfc, estado, comentario, ente)
solventaciones = db.get_solventaciones_por_rfc(rfc)

# Entity catalogs
entes = db.listar_entes()
municipios = db.listar_municipios()
clave = db.normalizar_ente_clave(etiqueta)  # sigla/nombre -> clave
```

**Key Methods:**
- `guardar_registros_individuales(registros)`: Upserts employee records (INSERT or UPDATE)
- `obtener_cruces_reales()`: Returns employees working in multiple entities
- `get_solventaciones_por_rfc(rfc)`: Gets audit status map by entity
- Catalog helpers: `get_mapa_siglas()`, `get_mapa_claves_inverso()`

### core/data_processor.py

**DataProcessor** - Excel file processing and conflict detection:

```python
processor = DataProcessor()

# Extract all individual records from uploaded files
registros, alertas = processor.extraer_registros_individuales(files)

# Process and detect conflicts (legacy method)
resultados, alertas = processor.procesar_archivos(files)
```

**Processing Logic:**
1. Reads Excel files where each sheet name = entity (ente/municipio)
2. Validates required columns: RFC, NOMBRE, PUESTO, FECHA_ALTA, FECHA_BAJA, QNA1-QNA24
3. Normalizes entity names using catalog (siglas/nombre → clave)
4. Detects conflicts: same RFC active in multiple entities during the same QNA
5. Returns individual records + alerts for missing entities/columns

**Conflict Detection:**
- `_cruces_quincenales(entes_rfc)`: Detects employees with overlapping QNAs across entities
- `_es_activo(valor)`: Determines if a QNA cell indicates active employment
- Only reports conflicts when QNA periods actually intersect

## Common Development Tasks

### Running the Application

```bash
# Development mode (debug enabled, port 4050)
python app.py

# Production mode with Gunicorn
gunicorn -w 4 -b 0.0.0.0:4050 app:app

# Production with SSL (if using certbot)
gunicorn -w 4 -b 0.0.0.0:4050 --certfile=/path/to/cert.pem --keyfile=/path/to/key.pem app:app
```

### Database Operations

```bash
# Initialize/reset database
python -c "from core.database import DatabaseManager; DatabaseManager('scil.db')"

# Migrate to new schema (with backup)
python migrar_bd.py

# Import entity catalogs from Excel
python importar_catalogos_scil.py

# Direct SQL access
sqlite3 scil.db
```

**Common Queries:**
```sql
-- View all conflicts
SELECT rfc, COUNT(DISTINCT ente) as num_entes
FROM registros_laborales
GROUP BY rfc
HAVING num_entes > 1;

-- Check audit status
SELECT r.rfc, r.nombre, s.estado, s.comentario
FROM registros_laborales r
LEFT JOIN solventaciones s ON r.rfc = s.rfc AND r.ente = s.ente
WHERE s.estado IS NOT NULL;

-- Entity hierarchy (ordered by NUM)
SELECT num, siglas, nombre FROM entes ORDER BY num;
```

### Excel File Format

Upload files must follow this structure:
- **Sheet names**: Must match entity siglas/nombre/clave from catalogs
- **Required columns**: RFC, NOMBRE, PUESTO, FECHA_ALTA, FECHA_BAJA
- **QNA columns**: QNA1, QNA2, ..., QNA24 (any non-empty value = active)
- **Optional column**: TOT_PERC (total compensation)

Download template: `/descargar-plantilla` → `static/Plantilla.xlsx`

### Adding New Entities

1. Edit catalog files: `catalogos/Estatales.xlsx` or `catalogos/Municipales.xlsx`
2. Required fields: NUM (hierarchical), CLAVE (unique), NOMBRE, SIGLAS
3. Run: `python importar_catalogos_scil.py`
4. Restart application

### Managing Users

Users are stored in `catalogos/Usuarios_SASP_2025.xlsx`:
- **Columns**: NOMBRE, USUARIO, CLAVE, ENTES
- **ENTES**: Comma-separated entity siglas or special values:
  - `TODOS` = full access (all entities + municipalities)
  - `TODOS LOS ENTES` = only state entities
  - `TODOS LOS MUNICIPIOS` = only municipalities

Import users: `python importar_catalogos_scil.py`

## Data Flow

1. **Upload**: User uploads Excel files via `/upload_laboral`
2. **Extract**: `DataProcessor.extraer_registros_individuales()` parses files
3. **Normalize**: Entity names converted to claves using catalogs
4. **Store**: `DatabaseManager.guardar_registros_individuales()` upserts records
5. **Analysis**: `/resultados` queries conflicts with `obtener_cruces_reales()`
6. **Filter**: `_filtrar_duplicados_reales()` keeps only real QNA intersections
7. **Display**: Results grouped by entity, showing only permitted records
8. **Export**: Excel reports with conflict details, QNA periods, and audit status

## Permission System

**Hierarchy:**
1. Superusers (odilia, luis, felipe): See all entities
2. `TODOS`: See all state entities + municipalities
3. `TODOS LOS ENTES`: See only state entities
4. `TODOS LOS MUNICIPIOS`: See only municipalities
5. Specific entities: See only assigned entities

**Permission Logic** (see `_allowed_all()` in app.py):
- Checked on `/resultados` display
- Enforced on export endpoints
- Validates using `_ente_match()` for flexible matching (clave/siglas/nombre)

## Key Concepts

### QNA System
- **QNA** = "Quincena" (biweekly pay period)
- 24 periods per year: QNA1 (Jan 1-15), QNA2 (Jan 16-31), ..., QNA24 (Dec 16-31)
- Conflict = same employee active in different entities during same QNA

### Entity Normalization
- Three identifiers: `clave` (primary key), `siglas` (short), `nombre` (full)
- Users can reference entities by any identifier
- System normalizes all to `clave` for DB operations
- Example: "ACUAMANALA" (sigla) → "MUN_1" (clave)

### Conflict Detection
Not all multi-entity employees are conflicts:
- RFC in 2+ entities but different QNAs → NO conflict
- RFC in 2+ entities with overlapping QNAs → CONFLICT
- Filter: `_filtrar_duplicados_reales()` ensures QNA intersection exists

### Audit Status (Solventaciones)
- **Estado**: "Solventado" / "No Solventado" / "Sin valoración"
- **Comentario**: Freeform explanation
- **Scope**: Per RFC + entity (same employee can have different status per entity)

## Environment Variables

```bash
# Database path (default: scil.db in project root)
export SCIL_DB=/path/to/scil.db

# Flask port (default: 4050)
export PORT=4050
```

## Troubleshooting

**"Hoja no encontrada en catálogo de entes"**
- Sheet name doesn't match any entity in catalogs
- Check spelling/capitalization
- Run `python importar_catalogos_scil.py` to refresh catalogs

**No conflicts showing despite uploads**
- Check if QNA columns have actual values (not empty/0/N/A)
- Verify same RFC exists in multiple entities with overlapping QNAs
- Review `registros_laborales` table directly

**Permission denied for entity**
- User's ENTES field doesn't include entity or special permission
- Update `catalogos/Usuarios_SASP_2025.xlsx` and re-import

**Database locked errors**
- SQLite limitation with concurrent writes
- Ensure only one upload operation at a time
- Consider switching to PostgreSQL for production if needed

## Code Conventions

- **Entity references**: Always normalize to `clave` before DB operations
- **RFC validation**: 10-13 uppercase alphanumeric characters
- **Date format**: YYYY-MM-DD (stored as TEXT)
- **QNA storage**: JSON dict in `qnas` column: `{"QNA1": value, "QNA3": value}`
- **Display helpers**: Use `_ente_display()`, `_ente_sigla()` for user-facing names
- **Logging**: Uses Python logging module, INFO level by default
