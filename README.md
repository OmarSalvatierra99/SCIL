# SCIL - Sistema de Cruce de Información Laboral

Sistema de auditoría para detectar inconsistencias en relaciones laborales y cruces de horarios entre entes públicos.

## Descripción

SCIL es una herramienta de auditoría diseñada para analizar archivos Excel que contienen información de relaciones laborales y horarios, identificando patrones sospechosos y inconsistencias que puedan requerir investigación.

### Características principales

- **Análisis de Patrones Laborales**: Detecta inconsistencias en relaciones laborales
- **Análisis de Cruces de Horarios**: Identifica solapamientos de horarios docentes
- **Sistema de Logging**: Logs detallados y rotativos de todas las operaciones
- **Base de Datos Histórica**: Mantiene histórico completo de análisis
- **Detección de Duplicados**: Evita procesar la misma información múltiples veces
- **Interfaz Web**: Dashboard intuitivo para visualizar resultados
- **Exportación CSV**: Exporta resultados para análisis externo

## Estructura del Proyecto

```
SCIL/
├── app_new.py              # Aplicación principal (punto de entrada)
├── config.py               # Configuración centralizada
├── requirements.txt        # Dependencias Python
├── .env.example           # Ejemplo de variables de entorno
├── README.md              # Este archivo
│
├── src/                   # Código fuente
│   ├── database/          # Gestión de base de datos
│   │   └── manager.py     # DatabaseManager
│   ├── processors/        # Procesadores de análisis
│   │   ├── base.py        # Clase base común
│   │   ├── patterns.py    # Análisis de patrones
│   │   └── schedules.py   # Análisis de horarios
│   ├── utils/             # Utilidades
│   │   └── logger.py      # Sistema de logging
│   └── web/               # Aplicación web
│       └── routes.py      # Rutas Flask
│
├── logs/                  # Logs del sistema (auto-generado)
│   ├── scil.log          # Log principal
│   ├── scil_errors.log   # Solo errores
│   ├── database.log      # Operaciones de BD
│   ├── patternsprocessor.log
│   └── schedulesprocessor.log
│
├── data/                  # Base de datos (auto-generado)
│   └── scil.db           # SQLite database
│
├── uploads/               # Archivos temporales (auto-generado)
├── static/                # Archivos estáticos (CSS, imágenes)
└── templates/             # Plantillas HTML
```

## Instalación

### Requisitos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)

### Pasos de instalación

1. **Clonar el repositorio**
   ```bash
   git clone <url-del-repositorio>
   cd SCIL
   ```

2. **Crear entorno virtual (recomendado)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno (opcional)**
   ```bash
   cp .env.example .env
   # Editar .env con tus configuraciones
   ```

5. **Ejecutar la aplicación**
   ```bash
   python app_new.py
   ```

6. **Acceder al sistema**
   - Abrir navegador en: `http://localhost:4050`
   - Contraseña por defecto: `scil2024`

## Uso

### 1. Análisis de Patrones Laborales

Detecta inconsistencias en relaciones laborales entre entes.

**Formato del archivo Excel:**
- Cada hoja representa un ente (formato: `ENTE_descripcion`)
- Columnas requeridas:
  - `RFC`: RFC del empleado
  - `NOMBRE`: Nombre completo
  - `PUESTO`: Puesto desempeñado
  - `FECHA_INGRESO`: Fecha de inicio de relación
  - `FECHA_EGRESO`: Fecha de fin de relación (vacío si activo)

**Patrones detectados:**

| Tipo | Severidad | Descripción |
|------|-----------|-------------|
| `SOLAPE_ENTRE_ENTES` | 5 (Crítica) | Relaciones simultáneas en diferentes entes |
| `SOLAPE_MISMO_ENTE` | 5 (Crítica) | Periodos solapados en el mismo ente |
| `EGRESO_ANTES_INGRESO` | 5 (Crítica) | Fecha de egreso anterior al ingreso |
| `DUPLICADO_MISMO_ENTE` | 4 (Alta) | Registros duplicados exactos |
| `RELACION_ACTIVA_SIN_EGRESO` | 3 (Media) | Relaciones sin fecha de egreso |

### 2. Análisis de Cruces de Horarios

Detecta solapamientos de horarios entre instituciones educativas.

**Formato del archivo Excel:**
- Cada hoja representa un ente (formato: `ENTE_descripcion`)
- Columnas requeridas:
  - `RFC`: RFC del docente
  - `NOMBRE`: Nombre completo
  - `DIA`: Día de la semana
  - `HORA_ENTRADA`: Hora de entrada (HH:MM)
  - `HORA_SALIDA`: Hora de salida (HH:MM)
  - `PLANTEL`: Nombre del plantel (opcional)
  - `FECHA_INGRESO`: Fecha de inicio (opcional)
  - `FECHA_EGRESO`: Fecha de fin (opcional)

**Patrones detectados:**

| Tipo | Severidad | Descripción |
|------|-----------|-------------|
| `SOLAPE_HORARIO_ENTRE_ENTES` | 5 (Crítica) | Horarios simultáneos en diferentes entes |
| `HORARIO_INCOHERENTE` | 5 (Crítica) | Hora de salida anterior a entrada |
| `SOLAPE_HORARIO_MISMO_ENTE` | 4 (Alta) | Horarios solapados en el mismo ente |
| `HORARIO_FALTANTE` | 3 (Media) | Datos incompletos de horario |
| `RELACION_ACTIVA_SIN_EGRESO` | 2 (Baja) | Docente sin fecha de egreso |

### 3. Exportación de Resultados

Los resultados pueden exportarse en formato CSV para análisis adicional:
- Desde el dashboard, hacer clic en "Exportar a CSV"
- El archivo incluye: RFC, Tipo de patrón, Severidad, Entes, Descripción, Fecha

## Configuración

### Variables de entorno

Crear archivo `.env` con las siguientes variables:

```bash
# Entorno (development/production)
SCIL_ENV=development

# Seguridad
SCIL_SECRET_KEY=tu_clave_secreta_aqui
SCIL_PASSWORD=tu_contraseña_personalizada

# Servidor
SCIL_HOST=0.0.0.0
SCIL_PORT=4050
SCIL_DEBUG=False

# Logging
SCIL_LOG_LEVEL=INFO

# Paginación
SCIL_RESULTS_PER_PAGE=20
```

### Archivos de configuración

Editar `config.py` para configuraciones avanzadas:
- Rutas de directorios
- Límites de archivos
- Configuración de base de datos
- Parámetros de logging

## Logs

El sistema genera logs detallados en el directorio `logs/`:

- **scil.log**: Log principal con todas las operaciones
- **scil_errors.log**: Solo errores críticos
- **database.log**: Operaciones de base de datos
- **patternsprocessor.log**: Procesamiento de patrones
- **schedulesprocessor.log**: Procesamiento de horarios

### Características de logging:

- Rotación automática (10MB por archivo, 5 backups)
- Formato estandarizado con timestamps
- Niveles: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Logs tanto en archivo como en consola

## Base de Datos

SQLite database ubicada en `data/scil.db`

### Tablas principales:

**resultados**
- Almacena todos los hallazgos detectados
- Incluye hash único para evitar duplicados
- Clasificación por tipo de análisis

**archivos_procesados**
- Histórico de archivos analizados
- Estadísticas de procesamiento
- Timestamps de procesamiento

## Desarrollo

### Arquitectura

El sistema sigue una arquitectura modular:

1. **Capa de Presentación** (`src/web/routes.py`): Maneja requests HTTP
2. **Capa de Procesamiento** (`src/processors/`): Lógica de análisis
3. **Capa de Datos** (`src/database/`): Persistencia de datos
4. **Capa de Utilidades** (`src/utils/`): Funciones comunes

### Extender funcionalidad

Para agregar un nuevo tipo de análisis:

1. Crear nuevo procesador en `src/processors/` heredando de `BaseProcessor`
2. Implementar métodos `procesar_archivo()` y `detectar_columnas()`
3. Agregar rutas en `src/web/routes.py`
4. Actualizar templates HTML según necesidad

## Seguridad

- Autenticación basada en contraseña (configurable)
- Validación de tipos de archivo
- Límite de tamaño de archivos (32MB por defecto)
- Sesiones seguras con secret key
- Archivos temporales eliminados después de procesamiento
- Logs de accesos y operaciones

## Troubleshooting

### Error: "No se encontró columna RFC"
- Verificar que el archivo Excel tiene una columna con "RFC" en el nombre
- Revisar que la hoja no esté vacía

### Error: "Error inicializando base de datos"
- Verificar permisos de escritura en directorio `data/`
- Revisar logs en `logs/database.log`

### Error: "Error procesando archivo"
- Verificar formato del archivo Excel (.xlsx)
- Revisar logs específicos del procesador
- Validar que las columnas necesarias existen

### Los logs no se crean
- Verificar permisos de escritura en directorio `logs/`
- Revisar configuración de `SCIL_LOG_LEVEL` en `.env`

## Licencia

[Especificar licencia]

## Contacto

[Información de contacto]

## Changelog

### v2.0.0 (2025-11-19)
- Refactorización completa de la arquitectura
- Sistema de logging profesional
- Configuración centralizada
- Estructura modular mejorada
- Base de datos optimizada
- Eliminación de código duplicado

### v1.0.0 (2025-01-07)
- Versión inicial
- Análisis de patrones laborales
- Análisis de cruces de horarios
- Interfaz web básica
