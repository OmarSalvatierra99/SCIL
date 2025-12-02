# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SASP (Sistema de Auditoría de Servicios Personales)** is an institutional audit platform for the Superior Audit Office of Tlaxcala (OFS). It analyzes labor data from public employees across government entities, detecting schedule conflicts, duplicate records, and overlapping work periods (quincenas) for compliance auditing.

Live: https://scil.omar-xyz.shop

## Development Commands

### Environment Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Development server (default port 4050)
python app.py

# Production with Gunicorn
gunicorn -w 4 -b 0.0.0.0:4050 app:app
```

### Database Management
```bash
# Initialize database with base tables
python -c "from core.database import DatabaseManager; db = DatabaseManager(); db.poblar_datos_iniciales()"

# Import catalogs (entities, municipalities, users)
python importar_catalogos_scil.py

# Migrate database structure (with backup)
python migrar_bd.py

# Clean/reset data
python limpiar_datos.py
```

## Architecture

### Core Components

**app.py** - Main Flask application
- Route handlers for authentication, file uploads, results, and exports
- Session-based authentication with role-based permissions
- Template rendering with Jinja2 filters for quincenal data

**core/database.py** - DatabaseManager class
- SQLite database operations and schema management
- Entity normalization (converts siglas/nombres to unique claves)
- User authentication with SHA256 password hashing
- Cross-reference detection queries

**core/data_processor.py** - DataProcessor class
- Excel file parsing and validation
- Quincenal (QNA) conflict detection across entities
- Individual employee record extraction

### Database Schema

**registros_laborales** - Individual employee records by entity
- Primary key: (rfc, ente) - prevents duplicate entries per entity
- Fields: nombre, puesto, fecha_ingreso, fecha_egreso, monto, qnas (JSON)
- Auto-updates on conflict using ON CONFLICT DO UPDATE

**solventaciones** - Audit resolution tracking
- Primary key: (rfc, ente)
- Tracks estado (status) and comentario (notes) per RFC+entity combination

**entes** and **municipios** - Entity catalogs
- Hierarchical NUM field (e.g., "1.2", "1.2.3") for institutional ordering
- Unique CLAVE field (e.g., "ENTE_1_2", "MUN_1") for database references
- SIGLAS field for display names

**usuarios** - User accounts
- SHA256 hashed passwords
- Comma-separated entes field for access control
- Special keywords: "TODOS", "TODOS LOS ENTES", "TODOS LOS MUNICIPIOS"

### Key Concepts

**Quincenas (QNA)** - Biweekly pay periods
- 24 periods per year (QNA1-QNA24)
- Stored as JSON: `{"QNA1": value, "QNA2": value, ...}`
- System detects overlapping active periods across entities

**Entity Normalization**
- Users and uploads may use SIGLAS (e.g., "SEGOB"), NOMBRE, or CLAVE
- `normalizar_ente_clave()` converts any identifier to unique CLAVE
- `_ente_display()` converts back to human-readable SIGLAS for templates

**Conflict Detection Algorithm** (in `_filtrar_duplicados_reales()`)
1. Group all registros_laborales by RFC
2. For each RFC, collect QNA sets per entity
3. Find intersections between entity QNA sets
4. Only report if same QNA exists in 2+ entities (real temporal overlap)

**Permission System**
- Superusers (odilia, luis, felipe): Full access to all entities
- Regular users: Access filtered by `entes` field
- `_allowed_all()` evaluates special permissions (ALL, ENTES, MUNICIPIOS)
- `_ente_match()` validates user access to specific entity records

### Excel Upload Format

Expected structure (Plantilla.xlsx):
- One sheet per entity (sheet name = SIGLAS or entity identifier)
- Required columns: RFC, NOMBRE, PUESTO, FECHA_ALTA, FECHA_BAJA
- QNA columns: QNA1, QNA2, ..., QNA24 (values indicate active status)
- Optional: TOT_PERC (total percepciones/salary)

Valid QNA active indicators: Any non-empty value except "0", "0.0", "NO", "N/A", "NA", "NONE"

### Export Functionality

**General Export** (`/exportar_general`)
- All conflicts across all accessible entities
- Two sheets: "Duplicidades_Generales" + "Resumen_por_Ente"

**Entity-Specific Export** (`/exportar_por_ente?ente=<siglas>`)
- Filtered to single entity
- Shows only conflicts involving that entity
- Includes Estatus and Solventación fields

Output columns: RFC, Nombre, Puesto, Fecha Alta, Fecha Baja, Total Percepciones, Ente Origen, Entes Incompatibilidad, Quincenas, Estatus, Solventación

## Important Implementation Details

### Session Management
- Session keys: `autenticado`, `usuario`, `nombre`, `entes`
- `@app.before_request` verifies authentication for all routes except login/static
- Returns JSON error for AJAX requests, redirects otherwise

### Catalog Imports
- Excel files in `catalogos/`: Estatales.xlsx, Municipales.xlsx, Usuarios_SASP_2025.xlsx
- Import script regenerates all catalog entries (DELETE + INSERT)
- NUM-based hierarchical sorting for institutional order preservation

### Database Optimization
- `@lru_cache` on `_entes_cache()` for fast entity lookups
- Unified entes+municipios queries using UNION ALL
- ON CONFLICT clauses prevent duplicate constraint violations

### Frontend-Backend Communication
- AJAX endpoints return JSON with `{"error": "..."}` or `{"mensaje": "..."}`
- File uploads sent as multipart/form-data with `files[]` array
- Estado updates use POST with JSON body: `{rfc, estado, comentario, ente}`

## Development Notes

- All entity references internally use CLAVE (e.g., "ENTE_1_2"), not SIGLAS
- Always call `normalizar_ente_clave()` before database writes
- Use `_ente_display()` for template rendering
- Quincenal data is stored as JSON TEXT, parsed with `json.loads()` on retrieval
- Hierarchical NUM sorting requires custom key function (see `orden_por_num()` in app.py:411)
- When modifying conflict detection, test with multi-entity, multi-QNA scenarios

## Common Gotchas

1. **Entity Matching**: User permissions may use SIGLAS while database uses CLAVE - always normalize
2. **QNA Intersection Logic**: Must verify `len(entes_en_qna) > 1` to confirm real conflict
3. **Solventaciones per Entity**: Each RFC can have different status per entity (not global)
4. **Excel Sheet Names**: Must match exact SIGLAS in catalog or will be skipped with warning
5. **Hierarchical Sorting**: String sorting breaks NUM order (use tuple of ints, see `orden_jerarquico()`)
