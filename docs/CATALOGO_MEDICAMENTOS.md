# Catálogo de Medicamentos - Guía de Configuración

Esta guía explica cómo configurar y usar el sistema de catálogo de medicamentos con búsqueda por código de barras.

## Configuración Rápida

### 1. Variables de Entorno (.env)

Agrega las siguientes variables a tu archivo `.env`:

```bash
# API de Códigos de Barras (Opcional - Funciona sin ella)
BARCODE_API_PROVIDER=upcitemdb
BARCODE_API_URL=https://api.upcitemdb.com/prod/trial/lookup
BARCODE_API_KEY=tu-api-key-aqui
```

### 2. Obtener API Key (Gratis)

**Opción A: UPCitemdb (Recomendada)**
- Visita: https://www.upcitemdb.com/api
- Crea una cuenta gratuita
- Plan gratuito: 100 búsquedas/día
- Copia tu API key y agrégala al `.env`

**Opción B: Sin API Externa**
- El sistema funciona sin API externa
- Solo podrás usar medicamentos agregados manualmente al catálogo
- Ideal si tienes catálogo completo o quieres control total

## Uso desde la App Móvil

### Endpoints Disponibles

#### 1. Búsqueda Híbrida por Código de Barras

```http
POST /api/mobile/catalog/lookup-barcode
Authorization: Bearer {token}
Content-Type: application/json

{
  "barcode": "7501006726350",
  "company_id": 1
}
```

**Respuestas:**

**Encontrado en catálogo local:**
```json
{
  "found": true,
  "source": "local",
  "in_catalog": true,
  "product": {
    "id": 123,
    "sku": "7501006726350",
    "name": "Paracetamol 500mg",
    "active_ingredient": "Paracetamol",
    "presentation": "Tabletas",
    "current_stock": 45,
    "cost_price": 25.50,
    "selling_price": 35.00
  }
}
```

**Encontrado en API externa:**
```json
{
  "found": true,
  "source": "external",
  "in_catalog": false,
  "product": {
    "barcode": "7501006726350",
    "name": "Paracetamol 500mg Tabletas",
    "brand": "Genomma Lab",
    "manufacturer": "Genomma Lab México",
    "category": "Salud y Belleza"
  },
  "suggestion": "Este producto no está en tu catálogo. ¿Deseas agregarlo?"
}
```

**No encontrado:**
```json
{
  "found": false,
  "source": null,
  "error": "Producto no encontrado",
  "suggestion": "Puedes agregar este medicamento manualmente al catálogo"
}
```

#### 2. Agregar Medicamento al Catálogo

```http
POST /api/mobile/catalog/products
Authorization: Bearer {token}
Content-Type: application/json

{
  "company_id": 1,
  "sku": "7501006726350",
  "name": "Paracetamol 500mg",
  "description": "Analgésico y antipirético",
  "active_ingredient": "Paracetamol",
  "presentation": "Tabletas",
  "laboratory_name": "Genomma Lab",
  "is_controlled": false,
  "cost_price": 25.50,
  "selling_price": 35.00,
  "min_stock_level": 20
}
```

**Campos opcionales:**
- `description`
- `laboratory_name` (se creará automáticamente si no existe)
- `therapeutic_group`
- `sanitary_registration`
- `profit_margin`
- `unit_measure` (default: "PZA")

#### 3. Actualizar Medicamento

```http
PUT /api/mobile/catalog/products/{product_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "cost_price": 28.00,
  "selling_price": 38.00,
  "min_stock_level": 30
}
```

## Flujo de Trabajo Recomendado

### Escenario 1: Producto Nuevo
1. Usuario escanea código de barras en la app
2. App llama a `/catalog/lookup-barcode`
3. Si `found: false`, mostrar formulario para agregar manualmente
4. Si `found: true, source: external`, mostrar datos y botón "Agregar a catálogo"
5. App llama a `/catalog/products` (POST) con los datos

### Escenario 2: Producto Ya Registrado
1. Usuario escanea código de barras
2. App llama a `/catalog/lookup-barcode`
3. Si `found: true, in_catalog: true`, mostrar datos del producto
4. Permitir al usuario:
   - Ver stock actual
   - Actualizar precios
   - Agregar al inventario (POS)

### Escenario 3: Agregar Stock
1. Usuario escanea código de barras
2. App verifica que existe en catálogo
3. Usuario ingresa cantidad, lote, fecha de caducidad
4. App llama al endpoint de compras para agregar stock

## Administración Web (Opcional)

Aunque la app móvil es el punto principal de interacción, puedes crear interfaces web para:

### Listado de Medicamentos
```
GET /medicamentos/catalogo
```
- Tabla con todos los medicamentos
- Filtros: nombre, laboratorio, ingrediente activo
- Búsqueda por código de barras

### Importación Masiva
```
POST /medicamentos/importar
```
- Subir archivo CSV con medicamentos
- Formato: sku,nombre,principio_activo,presentacion,laboratorio,precio

## Solución de Problemas

### "Barcode API not configured"
- La API externa no está configurada en `.env`
- El sistema funcionará solo con catálogo local
- No es un error crítico

### "Token expirado" en la app
- Los tokens JWT expiran después de 72 horas (configurable)
- El usuario debe hacer login nuevamente

### "Ya existe un producto con este código de barras"
- El SKU debe ser único por empresa
- Si quieres reemplazarlo, elimina el producto existente primero

### Límite de API alcanzado
- UPCitemdb free tier: 100 requests/día
- Considera upgrade a plan pago o usar solo catálogo local
- Los productos ya buscados se guardan en catálogo local

## Mejores Prácticas

1. **Usa la API externa como respaldo**: Agrega medicamentos comunes manualmente
2. **Verifica datos de API**: Los datos externos pueden no ser específicos para medicamentos
3. **Mantén actualizado el catálogo local**: Reduce dependencia de la API externa
4. **Configura stock mínimo**: Para alertas de reposición
5. **Usa lotes y fechas de caducidad**: Gestión FEFO (First Expire, First Out)

## Próximos Pasos

Una vez configurado el sistema, puedes:
1. Importar catálogo inicial de medicamentos comunes
2. Configurar laboratorios frecuentes
3. Entrenar a usuarios en escaneo desde la app
4. Monitorear stock y caducidades
