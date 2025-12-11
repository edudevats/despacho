# SAT Accounting App

Aplicación web para sincronizar y gestionar facturas del SAT (Sistema de Administración Tributaria).

## Características

- ✅ Sincronización automática con el SAT usando FIEL
- ✅ Descarga de facturas emitidas y recibidas
- ✅ Almacenamiento local de XMLs
- ✅ Clasificación automática de ingresos/egresos
- ✅ Múltiples empresas
- ✅ Protección contra duplicados
- ✅ Reintentos automáticos en descargas fallidas

## Estructura del Proyecto

```
sat/working/
├── app.py                  # Aplicación Flask principal
├── models.py              # Modelos de base de datos (User, Company, Invoice, Movement)
├── config.py              # Configuración
├── requirements.txt       # Dependencias
│
├── services/
│   └── sat_service.py     # Servicio para comunicación con SAT
│
├── templates/             # Templates HTML
│   ├── login.html
│   ├── dashboard.html
│   ├── companies.html
│   ├── sync.html
│   └── ...
│
├── instance/
│   └── sat_app.db         # Base de datos SQLite
│
├── facturas/              # XMLs descargados
│   └── {empresa}/
│       └── {uuid}.xml
│
└── scripts/               # Scripts de utilidad (ver scripts/README.md)
```

## Instalación

1. **Crear entorno virtual**:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

2. **Instalar dependencias**:
```bash
pip install -r requirements.txt
```

3. **Ejecutar migraciones** (solo primera vez):
```bash
python scripts/migrate_db.py
python scripts/add_duplicate_protections.py
```

4. **Iniciar aplicación**:
```bash
python app.py
```

5. **Acceder**: http://127.0.0.1:5000
   - Usuario: `admin`
   - Contraseña: `admin`

## Uso

### 1. Agregar Empresa

1. Ve a "Empresas"
2. Click en "Agregar Nueva Empresa"
3. Ingresa RFC y nombre

### 2. Sincronizar Facturas

1. Click en "Sincronizar" para la empresa
2. Sube archivos FIEL (.cer y .key)
3. Ingresa contraseña FIEL
4. Selecciona rango de fechas
5. Click en "Sincronizar"

### 3. Ver Movimientos

Ve a "Movimientos" para ver ingresos y egresos clasificados automáticamente.

## Modelos de Datos

### Invoice
- UUID (único)
- Datos básicos: fecha, total, subtotal, impuestos
- Tipo: I=Ingreso, E=Egreso, P=Pago
- Emisor y receptor (RFC y nombre)
- Forma de pago, método de pago, uso CFDI
- Descripción del concepto
- XML completo

### Movement
- Relación 1:1 con Invoice
- Tipo: INCOME o EXPENSE
- Monto y descripción
- Clasificación automática según:
  - Factura EMITIDA tipo I → INCOME
  - Factura EMITIDA tipo E → EXPENSE
  - Factura RECIBIDA tipo I → EXPENSE
  - Factura RECIBIDA tipo E → INCOME

## Protecciones Contra Duplicados

El sistema garantiza:
- ✅ UUID único en facturas (constraint de BD)
- ✅ Un solo movimiento por factura (índice único)
- ✅ Verificación antes de guardar XMLs
- ✅ Sincronizaciones repetidas no crean duplicados

Ver documentación completa en: [protecciones_duplicados.md]

## Scripts de Mantenimiento

Ver `scripts/README.md` para lista completa de scripts de utilidad.

Los más comunes:
- `verify_duplicate_protections.py` - Verificar integridad de datos
- `load_invoices_from_folder.py` - Recargar desde XMLs guardados

## Troubleshooting

### Error: "type 'Code' is not supported"
✅ **Solucionado** - La versión actual convierte objetos Code a strings automáticamente.

### Facturas sin movimientos
```bash
python scripts/create_missing_movements.py
```

### XMLs guardados pero no en BD
```bash
python scripts/load_invoices_from_folder.py
```

### Verificar integridad
```bash
python scripts/verify_duplicate_protections.py
```

## Tecnologías

- **Backend**: Flask, SQLAlchemy
- **Base de Datos**: SQLite
- **SAT Integration**: satcfdi
- **Autenticación**: Flask-Login

## Notas

- Los archivos XML son la **fuente de verdad** - siempre se guardan primero
- La base de datos se puede reconstruir desde los XMLs
- Respalda regularmente `instance/sat_app.db` y `facturas/`

## Licencia

Uso interno - ABYS TECHNOLOGIES SOLUTIONS
