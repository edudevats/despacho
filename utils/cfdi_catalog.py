# Catalog of "Uso CFDI" 4.0 keys
# Source: SAT Anexo 20 and official catalogs

CFDI_USAGE_CATALOG = {
    # --- Gastos (G) ---
    'G01': {
        'description': 'Adquisición de mercancías',
        'category': 'Gasto Operativo',
        'tax_implication': 'Deducible si es costo de venta',
        'guide': 'Compras de inventario destinado a la venta.'
    },
    'G02': {
        'description': 'Devoluciones, descuentos o bonificaciones',
        'category': 'Gasto Operativo',
        'tax_implication': 'Deducción (Nota de Crédito)',
        'guide': 'Cuando emites una nota de crédito relacionada con mercancía.'
    },
    'G03': {
        'description': 'Gastos en general',
        'category': 'Gasto Operativo',
        'tax_implication': 'Deducible',
        'guide': 'Para gastos operativos deducibles (papelería, luz, renta, servicios). Es la más común.'
    },

    # --- Inversiones (I) ---
    'I01': {
        'description': 'Construcciones',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Edificios o ampliaciones.'
    },
    'I02': {
        'description': 'Mobiliario y equipo de oficina por inversiones',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Escritorios, sillas, archiveros.'
    },
    'I03': {
        'description': 'Equipo de transporte',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable (con tope)',
        'guide': 'Automóviles, camiones de carga.'
    },
    'I04': {
        'description': 'Equipo de cómputo y accesorios',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Laptops, servidores, impresoras.'
    },
    'I05': {
        'description': 'Dados, troqueles, moldes, matrices y herramental',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Herramientas especializadas de manufactura.'
    },
    'I06': {
        'description': 'Comunicaciones telefónicas',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Infraestructura telefónica (conmutadores grandes).'
    },
    'I07': {
        'description': 'Comunicaciones satelitales',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Equipo de recepción satelital.'
    },
    'I08': {
        'description': 'Otra maquinaria y equipo',
        'category': 'Inversión (Activo Fijo)',
        'tax_implication': 'Depreciable',
        'guide': 'Maquinaria que no entra en las categorías anteriores.'
    },



    # --- Especiales ---
    'S01': {
        'description': 'Sin efectos fiscales',
        'category': 'Especial',
        'tax_implication': 'No Deducible',
        'guide': 'Cuando el gasto no es deducible, para facturas al público en general, o si eres residente en el extranjero.'
    },
    'CP01': {
        'description': 'Pagos',
        'category': 'Especial',
        'tax_implication': 'Administrativo',
        'guide': 'Exclusiva para el Complemento de Recepción de Pagos.'
    },
    'CN01': {
        'description': 'Nómina',
        'category': 'Especial',
        'tax_implication': 'Deducible (Nómina)',
        'guide': 'Exclusiva para recibos de Nómina.'
    }
}

def get_cfdi_usage_info(code):
    """
    Returns the dictionary info for a given Uso CFDI code.
    Fallback to generic unknown if not found.
    """
    if not code:
        return None
    return CFDI_USAGE_CATALOG.get(code, {
        'description': 'Desconocido',
        'category': 'Desconocido',
        'tax_implication': 'Desconocido',
        'guide': ''
    })
