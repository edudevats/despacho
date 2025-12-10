# Scripts de Utilidad

Esta carpeta contiene scripts de mantenimiento y utilidades para la aplicación SAT.

## Scripts de Configuración Inicial

### migrate_db.py
**Uso**: Una sola vez después de actualizar el modelo de base de datos
**Descripción**: Agrega las nuevas columnas a la tabla `invoice` (issuer_name, receiver_name, forma_pago, metodo_pago, uso_cfdi, descripcion)

```bash
python scripts/migrate_db.py
```

### add_duplicate_protections.py
**Uso**: Una sola vez para agregar índices únicos
**Descripción**: Crea índice único en `movement.invoice_id` para evitar movimientos duplicados

```bash
python scripts/add_duplicate_protections.py
```

---

## Scripts de Mantenimiento

### verify_duplicate_protections.py
**Uso**: Periódico (cuando se sospeche de problemas)
**Descripción**: Verifica que no haya duplicados en facturas, movimientos o archivos XML

```bash
python scripts/verify_duplicate_protections.py
```

### create_missing_movements.py
**Uso**: Solo si hay facturas sin movimientos
**Descripción**: Crea movimientos (INCOME/EXPENSE) para facturas que no tienen uno asociado

```bash
python scripts/create_missing_movements.py
```

---

## Scripts de Recuperación de Datos

### load_invoices_from_folder.py
**Uso**: Para cargar/recargar facturas desde los XMLs guardados
**Descripción**: Lee todos los XMLs de la carpeta `facturas/` y los carga en la base de datos. Útil para recuperación tras problemas.

```bash
python scripts/load_invoices_from_folder.py
```

### update_existing_invoices.py
**Uso**: Solo si hay facturas con campos incompletos
**Descripción**: Actualiza facturas existentes leyendo los datos desde los XMLs guardados

```bash
python scripts/update_existing_invoices.py
```

---

## Scripts de Limpieza (Legacy)

### clean_code_fields.py
**Uso**: Solo si hay datos con formato antiguo ("I - Ingreso" en vez de "I")
**Descripción**: Limpia campos que tienen el formato completo y los convierte a solo código

```bash
python scripts/clean_code_fields.py
```

---

## Notas Importantes

- ⚠️ **Backup antes de ejecutar**: Siempre respalda `instance/sat_app.db` antes de ejecutar scripts de mantenimiento
- ✅ **Orden recomendado** (solo primera vez):
  1. `migrate_db.py`
  2. `add_duplicate_protections.py`
  3. `load_invoices_from_folder.py` (si hay XMLs previos)
  4. `verify_duplicate_protections.py` (para verificar)

- 🔄 **Scripts seguros de re-ejecutar**:
  - `verify_duplicate_protections.py` - Solo verifica, no modifica
  - `load_invoices_from_folder.py` - Actualiza duplicados, no los crea

- ⚠️ **Scripts que modifican datos**:
  - `clean_code_fields.py`
  - `create_missing_movements.py`
  - `update_existing_invoices.py`
