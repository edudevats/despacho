"""
Modelos de base de datos del Sistema de Contaduría Multi-Nivel
Jerarquía: Despacho → Organización → Sucursal → POS
"""
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal


class Organizacion(db.Model):
    """
    Modelo de Organización
    Agrupa múltiples sucursales bajo una misma entidad comercial
    """
    __tablename__ = 'organizaciones'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    razon_social = db.Column(db.String(200))
    rfc = db.Column(db.String(13), unique=True)
    direccion = db.Column(db.Text)
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))
    activa = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    sucursales = db.relationship('Sucursal', backref='organizacion', lazy='dynamic',
                                cascade='all, delete-orphan')
    usuarios_organizacion = db.relationship('Usuario',
                                           foreign_keys='Usuario.organizacion_id',
                                           backref='organizacion', lazy='dynamic')
    categorias_ingreso = db.relationship('CategoriaIngreso',
                                        foreign_keys='CategoriaIngreso.organizacion_id',
                                        backref='organizacion', lazy='dynamic')
    categorias_egreso = db.relationship('CategoriaEgreso',
                                       foreign_keys='CategoriaEgreso.organizacion_id',
                                       backref='organizacion', lazy='dynamic')
    proveedores = db.relationship('Proveedor', backref='organizacion', lazy='dynamic',
                                 cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Organizacion {self.nombre}>'


class Sucursal(db.Model):
    """
    Modelo de Sucursal (antes Clínica)
    Pertenece a una Organización y agrupa usuarios POS
    """
    __tablename__ = 'sucursales'

    id = db.Column(db.Integer, primary_key=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizaciones.id'), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    razon_social = db.Column(db.String(200))
    rfc = db.Column(db.String(13), unique=True)
    direccion = db.Column(db.Text)
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))
    activa = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    usuarios = db.relationship('Usuario',
                              foreign_keys='Usuario.sucursal_id',
                              backref='sucursal', lazy='dynamic',
                              cascade='all, delete-orphan')
    categorias_ingreso = db.relationship('CategoriaIngreso',
                                        foreign_keys='CategoriaIngreso.sucursal_id',
                                        backref='sucursal', lazy='dynamic')
    categorias_egreso = db.relationship('CategoriaEgreso',
                                       foreign_keys='CategoriaEgreso.sucursal_id',
                                       backref='sucursal', lazy='dynamic')
    ingresos = db.relationship('Ingreso', backref='sucursal', lazy='dynamic',
                              cascade='all, delete-orphan')
    egresos = db.relationship('Egreso', backref='sucursal', lazy='dynamic',
                             cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Sucursal {self.nombre}>'


class Usuario(db.Model, UserMixin):
    """
    Modelo de Usuario con soporte multi-rol jerárquico
    Roles: admin_despacho, principal_organizacion, principal_sucursal, secundario_pos
    """
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre_completo = db.Column(db.String(200))

    # Rol: 'admin_despacho', 'principal_organizacion', 'principal_sucursal', 'secundario_pos'
    rol = db.Column(db.String(30), nullable=False, index=True)

    # Foreign Keys (nullable según rol)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizaciones.id'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)

    # Permisos granulares para usuarios secundarios (POS)
    puede_registrar_ingresos = db.Column(db.Boolean, default=True)
    puede_registrar_egresos = db.Column(db.Boolean, default=True)
    puede_editar_movimientos = db.Column(db.Boolean, default=False)
    puede_eliminar_movimientos = db.Column(db.Boolean, default=False)
    puede_ver_reportes = db.Column(db.Boolean, default=False)

    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime)

    # Relaciones
    ingresos_registrados = db.relationship('Ingreso', backref='usuario_registro',
                                          lazy='dynamic')
    egresos_registrados = db.relationship('Egreso', backref='usuario_registro',
                                         lazy='dynamic')
    auditorias = db.relationship('Auditoria', backref='usuario', lazy='dynamic')

    def set_password(self, password):
        """Establece el hash de la contraseña"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica la contraseña"""
        return check_password_hash(self.password_hash, password)

    def es_admin_despacho(self):
        """Verifica si el usuario es administrador del despacho"""
        return self.rol == 'admin_despacho'

    def es_principal_organizacion(self):
        """Verifica si el usuario es principal de organización"""
        return self.rol == 'principal_organizacion'

    def es_principal_sucursal(self):
        """Verifica si el usuario es principal de sucursal"""
        return self.rol == 'principal_sucursal'

    def es_secundario_pos(self):
        """Verifica si el usuario es secundario (punto de venta)"""
        return self.rol == 'secundario_pos'

    def __repr__(self):
        return f'<Usuario {self.username} - {self.rol}>'


class CategoriaIngreso(db.Model):
    """
    Catálogo de Categorías de Ingresos
    Puede ser de nivel Organización (compartida) o Sucursal (personalizada)
    """
    __tablename__ = 'categorias_ingreso'

    id = db.Column(db.Integer, primary_key=True)
    # Nivel Organización (categorías base compartidas)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizaciones.id'), nullable=True)
    # Nivel Sucursal (categorías personalizadas)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)

    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    ingresos = db.relationship('Ingreso', backref='categoria', lazy='dynamic')

    __table_args__ = (
        # Una categoría debe pertenecer a organización O sucursal, no ambas
        db.CheckConstraint(
            '(organizacion_id IS NOT NULL AND sucursal_id IS NULL) OR '
            '(organizacion_id IS NULL AND sucursal_id IS NOT NULL)',
            name='check_categoria_ingreso_nivel'
        ),
    )

    def __repr__(self):
        return f'<CategoriaIngreso {self.nombre}>'


class CategoriaEgreso(db.Model):
    """
    Catálogo de Categorías de Egresos
    Puede ser de nivel Organización (compartida) o Sucursal (personalizada)
    """
    __tablename__ = 'categorias_egreso'

    id = db.Column(db.Integer, primary_key=True)
    # Nivel Organización (categorías base compartidas)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizaciones.id'), nullable=True)
    # Nivel Sucursal (categorías personalizadas)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)

    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    egresos = db.relationship('Egreso', backref='categoria', lazy='dynamic')

    __table_args__ = (
        # Una categoría debe pertenecer a organización O sucursal, no ambas
        db.CheckConstraint(
            '(organizacion_id IS NOT NULL AND sucursal_id IS NULL) OR '
            '(organizacion_id IS NULL AND sucursal_id IS NOT NULL)',
            name='check_categoria_egreso_nivel'
        ),
    )

    def __repr__(self):
        return f'<CategoriaEgreso {self.nombre}>'


class Ingreso(db.Model):
    """
    Modelo de Ingresos
    Registra todos los ingresos de cada sucursal
    """
    __tablename__ = 'ingresos'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias_ingreso.id'),
                            nullable=False)

    fecha = db.Column(db.Date, nullable=False, index=True)
    monto = db.Column(db.Numeric(12, 2), nullable=False)

    # Método de pago: 'efectivo', 'transferencia', 'tarjeta'
    metodo_pago = db.Column(db.String(20), nullable=False)

    notas = db.Column(db.Text)

    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_ingreso_sucursal_fecha', 'sucursal_id', 'fecha'),
    )

    def __repr__(self):
        return f'<Ingreso {self.id} - ${self.monto}>'


class Egreso(db.Model):
    """
    Modelo de Egresos
    Registra todos los egresos de cada sucursal con opción de comprobante
    """
    __tablename__ = 'egresos'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias_egreso.id'),
                            nullable=False)

    fecha = db.Column(db.Date, nullable=False, index=True)
    monto = db.Column(db.Numeric(12, 2), nullable=False)

    # Método de pago
    metodo_pago = db.Column(db.String(20), nullable=False)

    # Comprobante (imagen o PDF)
    comprobante_filename = db.Column(db.String(255))
    comprobante_path = db.Column(db.String(500))

    notas = db.Column(db.Text)

    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_egreso_sucursal_fecha', 'sucursal_id', 'fecha'),
    )

    def __repr__(self):
        return f'<Egreso {self.id} - ${self.monto}>'


class Auditoria(db.Model):
    """
    Modelo de Auditoría
    Registra todas las acciones importantes en el sistema
    """
    __tablename__ = 'auditoria'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)

    # Tipo de acción: 'login', 'create', 'update', 'delete', 'export'
    accion = db.Column(db.String(50), nullable=False)

    # Tabla afectada: 'ingreso', 'egreso', 'usuario', 'sucursal', etc.
    tabla = db.Column(db.String(50))
    registro_id = db.Column(db.Integer)

    # Detalles en formato JSON
    detalles = db.Column(db.Text)

    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))

    fecha = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<Auditoria {self.accion} - {self.fecha}>'


# ==================== MÓDULOS FISCALES AVANZADOS ====================


class Proveedor(db.Model):
    """
    Catálogo de Proveedores con validación fiscal
    Compartidos a nivel de Organización
    """
    __tablename__ = 'proveedores'

    id = db.Column(db.Integer, primary_key=True)
    organizacion_id = db.Column(db.Integer, db.ForeignKey('organizaciones.id'), nullable=False)

    # Datos fiscales
    rfc = db.Column(db.String(13), nullable=False, index=True)
    razon_social = db.Column(db.String(200), nullable=False)
    nombre_comercial = db.Column(db.String(200))

    # Datos de contacto
    email = db.Column(db.String(120))
    telefono = db.Column(db.String(20))
    direccion = db.Column(db.Text)

    # Validación fiscal
    validado = db.Column(db.Boolean, default=False)
    en_lista_negra = db.Column(db.Boolean, default=False)  # EFOS/EDOS
    fecha_validacion = db.Column(db.DateTime)
    notas_validacion = db.Column(db.Text)

    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    facturas = db.relationship('FacturaCFDI', backref='proveedor', lazy='dynamic')

    __table_args__ = (
        db.Index('idx_proveedor_rfc', 'rfc'),
    )

    def __repr__(self):
        return f'<Proveedor {self.razon_social} - {self.rfc}>'


class FacturaCFDI(db.Model):
    """
    Facturas Digitales (CFDI/XML)
    Almacena información extraída de archivos XML de facturas
    """
    __tablename__ = 'facturas_cfdi'

    id = db.Column(db.Integer, primary_key=True)
    egreso_id = db.Column(db.Integer, db.ForeignKey('egresos.id'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)

    # Relación con Egreso (1:1)
    egreso = db.relationship('Egreso', backref=db.backref('factura_cfdi', uselist=False), foreign_keys=[egreso_id])

    # Datos del CFDI
    uuid = db.Column(db.String(36), unique=True, nullable=False, index=True)  # Folio Fiscal
    serie = db.Column(db.String(25))
    folio = db.Column(db.String(40))
    fecha_emision = db.Column(db.DateTime, nullable=False)
    fecha_timbrado = db.Column(db.DateTime)

    # Datos fiscales del emisor (proveedor)
    emisor_rfc = db.Column(db.String(13), nullable=False)
    emisor_nombre = db.Column(db.String(200))
    emisor_regimen = db.Column(db.String(10))

    # Datos fiscales del receptor (sucursal)
    receptor_rfc = db.Column(db.String(13), nullable=False)
    receptor_nombre = db.Column(db.String(200))
    receptor_uso_cfdi = db.Column(db.String(10))  # G03, etc.

    # Importes
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    descuento = db.Column(db.Numeric(12, 2), default=0)
    iva = db.Column(db.Numeric(12, 2), default=0)
    ieps = db.Column(db.Numeric(12, 2), default=0)
    isr_retenido = db.Column(db.Numeric(12, 2), default=0)
    iva_retenido = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False)

    # Tipo de comprobante: I (Ingreso), E (Egreso), T (Traslado), N (Nómina), P (Pago)
    tipo_comprobante = db.Column(db.String(1), nullable=False)

    # Método y forma de pago
    metodo_pago = db.Column(db.String(10))  # PUE, PPD
    forma_pago = db.Column(db.String(10))   # 01=Efectivo, 03=Transferencia, 04=Tarjeta

    # Moneda
    moneda = db.Column(db.String(3), default='MXN')
    tipo_cambio = db.Column(db.Numeric(10, 6), default=1)

    # Archivos
    xml_filename = db.Column(db.String(255))
    xml_path = db.Column(db.String(500))
    pdf_filename = db.Column(db.String(255))
    pdf_path = db.Column(db.String(500))

    # Estado de validación
    validado_sat = db.Column(db.Boolean, default=False)
    fecha_validacion_sat = db.Column(db.DateTime)
    estado_sat = db.Column(db.String(20))  # Vigente, Cancelada

    # Clasificación fiscal
    clasificacion_fiscal_id = db.Column(db.Integer,
                                       db.ForeignKey('clasificaciones_fiscales.id'))
    deducible = db.Column(db.Boolean, default=True)
    porcentaje_deducible = db.Column(db.Numeric(5, 2), default=100)

    notas = db.Column(db.Text)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<FacturaCFDI {self.uuid} - ${self.total}>'


class ClasificacionFiscal(db.Model):
    """
    Clasificaciones fiscales para doble etiquetado
    Mapeo entre categorías operativas y clasificaciones fiscales
    """
    __tablename__ = 'clasificaciones_fiscales'

    id = db.Column(db.Integer, primary_key=True)

    # Clasificación
    codigo = db.Column(db.String(20), unique=True, nullable=False)  # Ej: 'GASTO_GENERAL'
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)

    # Deducibilidad
    deducible = db.Column(db.Boolean, default=True)
    porcentaje_deducible = db.Column(db.Numeric(5, 2), default=100)

    # Requisitos
    requiere_factura = db.Column(db.Boolean, default=True)
    monto_max_efectivo = db.Column(db.Numeric(10, 2), default=2000)  # SAT México

    # Para ISR
    tipo_deduccion = db.Column(db.String(50))  # 'Inmediata', 'Inversión', 'No deducible'

    activa = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    facturas = db.relationship('FacturaCFDI', backref='clasificacion_fiscal', lazy='dynamic')

    def __repr__(self):
        return f'<ClasificacionFiscal {self.nombre} - {self.porcentaje_deducible}%>'


class ActivoFijo(db.Model):
    """
    Activos Fijos con depreciación automática
    """
    __tablename__ = 'activos_fijos'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)
    egreso_id = db.Column(db.Integer, db.ForeignKey('egresos.id'), nullable=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas_cfdi.id'), nullable=True)

    # Identificación
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    numero_serie = db.Column(db.String(100))
    numero_inventario = db.Column(db.String(50))

    # Valores
    valor_adquisicion = db.Column(db.Numeric(12, 2), nullable=False)
    valor_residual = db.Column(db.Numeric(12, 2), default=0)

    # Depreciación
    vida_util_anos = db.Column(db.Integer, nullable=False)  # Años de vida útil
    porcentaje_anual = db.Column(db.Numeric(5, 2), nullable=False)  # % depreciación anual
    metodo_depreciacion = db.Column(db.String(20), default='lineal')  # lineal, acelerada

    # Fechas
    fecha_adquisicion = db.Column(db.Date, nullable=False)
    fecha_inicio_depreciacion = db.Column(db.Date, nullable=False)
    fecha_fin_depreciacion = db.Column(db.Date)

    # Estado
    estado = db.Column(db.String(20), default='activo')  # activo, vendido, baja
    fecha_baja = db.Column(db.Date)
    motivo_baja = db.Column(db.Text)

    # Ubicación
    ubicacion = db.Column(db.String(200))
    responsable = db.Column(db.String(200))

    notas = db.Column(db.Text)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    depreciaciones = db.relationship('DepreciacionMensual', backref='activo',
                                    lazy='dynamic', cascade='all, delete-orphan')

    def calcular_depreciacion_mensual(self):
        """Calcula la depreciación mensual"""
        valor_depreciable = self.valor_adquisicion - self.valor_residual
        return (valor_depreciable * self.porcentaje_anual / 100) / 12

    def calcular_valor_actual(self):
        """Calcula el valor actual del activo"""
        total_depreciado = sum(d.monto for d in self.depreciaciones)
        return self.valor_adquisicion - total_depreciado

    def __repr__(self):
        return f'<ActivoFijo {self.nombre} - ${self.valor_adquisicion}>'


class DepreciacionMensual(db.Model):
    """
    Registro mensual de depreciación de activos
    """
    __tablename__ = 'depreciaciones_mensuales'

    id = db.Column(db.Integer, primary_key=True)
    activo_id = db.Column(db.Integer, db.ForeignKey('activos_fijos.id'), nullable=False)

    # Periodo
    ano = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)

    # Montos
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    valor_libro_inicio = db.Column(db.Numeric(12, 2))
    valor_libro_fin = db.Column(db.Numeric(12, 2))

    # Control
    calculado_automaticamente = db.Column(db.Boolean, default=True)
    fecha_calculo = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('activo_id', 'ano', 'mes',
                          name='unique_depreciacion_activo_periodo'),
        db.Index('idx_depreciacion_periodo', 'ano', 'mes'),
    )

    def __repr__(self):
        return f'<Depreciacion {self.ano}-{self.mes:02d} - ${self.monto}>'


class CierrePeriodo(db.Model):
    """
    Cierre de periodos contables (Lock Dates)
    Evita modificaciones en periodos ya declarados
    """
    __tablename__ = 'cierres_periodo'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)

    # Periodo cerrado
    ano = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)

    # Control de cierre
    fecha_cierre = db.Column(db.DateTime, default=datetime.utcnow)
    cerrado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

    # Totales al cierre
    total_ingresos = db.Column(db.Numeric(12, 2))
    total_egresos = db.Column(db.Numeric(12, 2))
    total_iva_cobrado = db.Column(db.Numeric(12, 2))
    total_iva_pagado = db.Column(db.Numeric(12, 2))

    # Reapertura
    reabierto = db.Column(db.Boolean, default=False)
    fecha_reapertura = db.Column(db.DateTime)
    reabierto_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    motivo_reapertura = db.Column(db.Text)

    notas = db.Column(db.Text)

    # Relaciones
    cerrado_por = db.relationship('Usuario', foreign_keys=[cerrado_por_id])
    reabierto_por = db.relationship('Usuario', foreign_keys=[reabierto_por_id])

    __table_args__ = (
        db.UniqueConstraint('sucursal_id', 'ano', 'mes',
                          name='unique_cierre_sucursal_periodo'),
    )

    def __repr__(self):
        return f'<CierrePeriodo {self.ano}-{self.mes:02d} Sucursal:{self.sucursal_id}>'


class CentroCosto(db.Model):
    """
    Centros de Costo para prorrateo de gastos
    """
    __tablename__ = 'centros_costo'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)

    # Identificación
    codigo = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)

    # Jerarquía (opcional)
    centro_padre_id = db.Column(db.Integer, db.ForeignKey('centros_costo.id'))

    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    subcentros = db.relationship('CentroCosto', backref=db.backref('centro_padre', remote_side=[id]))

    __table_args__ = (
        db.UniqueConstraint('sucursal_id', 'codigo',
                          name='unique_centro_costo_sucursal'),
    )

    def __repr__(self):
        return f'<CentroCosto {self.codigo} - {self.nombre}>'


class ProrrateoGasto(db.Model):
    """
    Distribución de gastos entre centros de costo
    """
    __tablename__ = 'prorrateo_gastos'

    id = db.Column(db.Integer, primary_key=True)
    egreso_id = db.Column(db.Integer, db.ForeignKey('egresos.id'), nullable=False)
    centro_costo_id = db.Column(db.Integer, db.ForeignKey('centros_costo.id'), nullable=False)

    # Distribución
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    porcentaje = db.Column(db.Numeric(5, 2), nullable=False)

    notas = db.Column(db.Text)

    # Relaciones
    egreso = db.relationship('Egreso', backref='prorrateos')
    centro_costo = db.relationship('CentroCosto', backref='prorrateos')

    def __repr__(self):
        return f'<ProrrateoGasto Egreso:{self.egreso_id} - {self.porcentaje}%>'


class Inventario(db.Model):
    """
    Catálogo de productos/insumos para inventario
    """
    __tablename__ = 'inventarios'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)

    # Identificación
    codigo = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)

    # Clasificación
    categoria = db.Column(db.String(100))
    tipo = db.Column(db.String(20))  # 'insumo', 'producto', 'medicamento'

    # Unidad de medida
    unidad_medida = db.Column(db.String(20))  # 'pieza', 'caja', 'kg', 'litro'

    # Existencias
    stock_actual = db.Column(db.Numeric(10, 2), default=0)
    stock_minimo = db.Column(db.Numeric(10, 2), default=0)
    stock_maximo = db.Column(db.Numeric(10, 2))

    # Costos
    costo_unitario = db.Column(db.Numeric(10, 2))
    precio_venta = db.Column(db.Numeric(10, 2))

    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones
    movimientos = db.relationship('MovimientoInventario', backref='producto',
                                 lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('sucursal_id', 'codigo',
                          name='unique_inventario_sucursal'),
    )

    def __repr__(self):
        return f'<Inventario {self.codigo} - {self.nombre}>'


class MovimientoInventario(db.Model):
    """
    Movimientos de inventario (entradas/salidas)
    """
    __tablename__ = 'movimientos_inventario'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventarios.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    egreso_id = db.Column(db.Integer, db.ForeignKey('egresos.id'))  # Si es compra

    # Tipo de movimiento
    tipo = db.Column(db.String(20), nullable=False)  # 'entrada', 'salida', 'ajuste'
    motivo = db.Column(db.String(100))  # 'compra', 'venta', 'uso', 'merma'

    # Cantidad
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    costo_unitario = db.Column(db.Numeric(10, 2))
    costo_total = db.Column(db.Numeric(12, 2))

    # Stock después del movimiento
    stock_resultante = db.Column(db.Numeric(10, 2), nullable=False)

    fecha_movimiento = db.Column(db.DateTime, default=datetime.utcnow)
    notas = db.Column(db.Text)

    # Relaciones
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return f'<MovimientoInventario {self.tipo} - {self.cantidad}>'


class Nomina(db.Model):
    """
    Registro de nómina y honorarios
    """
    __tablename__ = 'nominas'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=False)

    # Periodo
    ano = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    quincena = db.Column(db.Integer)  # 1 o 2, null si es mensual

    # Empleado
    empleado_nombre = db.Column(db.String(200), nullable=False)
    empleado_rfc = db.Column(db.String(13))
    empleado_nss = db.Column(db.String(11))
    puesto = db.Column(db.String(100))

    # Tipo de contratación
    tipo_contrato = db.Column(db.String(30))  # 'asalariado', 'honorarios', 'asimilados'

    # Percepciones
    sueldo_base = db.Column(db.Numeric(10, 2), default=0)
    horas_extra = db.Column(db.Numeric(10, 2), default=0)
    bonos = db.Column(db.Numeric(10, 2), default=0)
    otras_percepciones = db.Column(db.Numeric(10, 2), default=0)
    total_percepciones = db.Column(db.Numeric(10, 2), nullable=False)

    # Deducciones
    isr_retenido = db.Column(db.Numeric(10, 2), default=0)
    imss_trabajador = db.Column(db.Numeric(10, 2), default=0)
    otras_deducciones = db.Column(db.Numeric(10, 2), default=0)
    total_deducciones = db.Column(db.Numeric(10, 2), default=0)

    # Neto a pagar
    neto = db.Column(db.Numeric(10, 2), nullable=False)

    # Cuotas patronales (no deducibles del trabajador, pero costo para la empresa)
    imss_patronal = db.Column(db.Numeric(10, 2), default=0)

    # Pago
    fecha_pago = db.Column(db.Date)
    metodo_pago = db.Column(db.String(20))
    referencia_pago = db.Column(db.String(100))

    # CFDI de nómina (si aplica)
    uuid_nomina = db.Column(db.String(36))
    xml_nomina_path = db.Column(db.String(500))

    notas = db.Column(db.Text)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_nomina_periodo', 'sucursal_id', 'ano', 'mes'),
    )

    def __repr__(self):
        return f'<Nomina {self.empleado_nombre} {self.ano}-{self.mes:02d}>'


class AlertaFiscal(db.Model):
    """
    Alertas y banderas rojas para auditoría
    """
    __tablename__ = 'alertas_fiscales'

    id = db.Column(db.Integer, primary_key=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.id'), nullable=True)

    # Tipo de alerta
    tipo = db.Column(db.String(50), nullable=False)
    # Tipos: 'efectivo_excesivo', 'sin_factura', 'proveedor_lista_negra',
    #        'duplicado', 'anomalia_gasto', 'margen_bajo'

    # Severidad
    severidad = db.Column(db.String(20), default='media')  # 'baja', 'media', 'alta', 'critica'

    # Descripción
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)

    # Referencia al movimiento
    tabla_referencia = db.Column(db.String(50))
    registro_id = db.Column(db.Integer)

    # Montos involucrados
    monto = db.Column(db.Numeric(12, 2))

    # Estado
    estado = db.Column(db.String(20), default='pendiente')  # 'pendiente', 'revisada', 'resuelta', 'ignorada'
    fecha_revision = db.Column(db.DateTime)
    revisado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'))
    notas_revision = db.Column(db.Text)

    # Detección automática
    detectada_automaticamente = db.Column(db.Boolean, default=True)
    fecha_deteccion = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relaciones
    revisado_por = db.relationship('Usuario')

    def __repr__(self):
        return f'<AlertaFiscal {self.tipo} - {self.severidad}>'
