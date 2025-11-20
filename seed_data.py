"""
Script para poblar la base de datos con datos de demostración
Sistema con jerarquía de 4 niveles: Despacho -> Organizaciones -> Sucursales -> POS
Ejecutar con: python seed_data.py o flask seed-db
"""
from app import create_app, db
from app.models import (
    Usuario, Organizacion, Sucursal,
    CategoriaIngreso, CategoriaEgreso,
    Ingreso, Egreso, Proveedor
)
from datetime import datetime, date, timedelta
from decimal import Decimal
import random


def seed_database():
    """Pobla la base de datos con datos de demostración"""

    app = create_app('development')

    with app.app_context():
        # Limpiar base de datos existente
        print("Limpiando base de datos...")
        db.drop_all()
        db.create_all()

        print("\n" + "="*60)
        print("Creando datos de demostración - Estructura de 4 niveles")
        print("="*60)

        # =====================================================
        # NIVEL 1: ADMIN DEL DESPACHO CONTABLE
        # =====================================================
        print("\n[1/7] Creando Administrador del Despacho...")
        admin = Usuario(
            username='admin',
            email='admin@despachocontable.com',
            nombre_completo='Administrador del Despacho',
            rol='admin_despacho',
            organizacion_id=None,
            sucursal_id=None,
            activo=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("   [OK] Usuario admin creado")

        # =====================================================
        # NIVEL 2: ORGANIZACIONES
        # =====================================================
        print("\n[2/7] Creando Organizaciones...")
        organizaciones_data = [
            {
                'nombre': 'Grupo Médico del Norte',
                'razon_social': 'Grupo Médico del Norte SA de CV',
                'rfc': 'GMN030101ABC',
                'direccion': 'Av. Constitución 1500, Col. Centro, Monterrey, NL',
                'telefono': '81-8888-0001',
                'email': 'contacto@grupomedico-norte.com'
            },
            {
                'nombre': 'Clínicas del Sur',
                'razon_social': 'Clínicas del Sur SA de CV',
                'rfc': 'CDS040202XYZ',
                'direccion': 'Blvd. Insurgentes Sur 2000, Col. Jardines, CDMX',
                'telefono': '55-5555-0002',
                'email': 'info@clinicasdelsur.com'
            }
        ]

        organizaciones = []
        for data in organizaciones_data:
            org = Organizacion(**data)
            db.session.add(org)
            organizaciones.append(org)

        db.session.commit()
        print(f"   [OK] {len(organizaciones)} organizaciones creadas")

        # Crear usuarios principales de cada organización
        usuarios_org = []
        for i, org in enumerate(organizaciones):
            usuario = Usuario(
                username=f'org{i+1}',
                email=f'admin@org{i+1}.com',
                nombre_completo=f'Director General - {org.nombre}',
                rol='principal_organizacion',
                organizacion_id=org.id,
                sucursal_id=None,
                activo=True
            )
            usuario.set_password('org123')
            db.session.add(usuario)
            usuarios_org.append(usuario)

        db.session.commit()
        print(f"   [OK] {len(usuarios_org)} directores de organización creados")

        # =====================================================
        # NIVEL 3: SUCURSALES (2 por organización)
        # =====================================================
        print("\n[3/7] Creando Sucursales...")
        sucursales_data = [
            # Organización 1: Grupo Médico del Norte
            {
                'nombre': 'Sucursal Centro',
                'razon_social': 'Grupo Médico del Norte - Centro',
                'rfc': 'GMN030101CT1',
                'direccion': 'Av. Hidalgo 123, Col. Centro, Monterrey, NL',
                'telefono': '81-8888-1001',
                'email': 'centro@grupomedico-norte.com',
                'organizacion': organizaciones[0]
            },
            {
                'nombre': 'Sucursal Valle',
                'razon_social': 'Grupo Médico del Norte - Valle',
                'rfc': 'GMN030101VL2',
                'direccion': 'Av. Valle Oriente 456, Col. Del Valle, San Pedro, NL',
                'telefono': '81-8888-1002',
                'email': 'valle@grupomedico-norte.com',
                'organizacion': organizaciones[0]
            },
            # Organización 2: Clínicas del Sur
            {
                'nombre': 'Sucursal Polanco',
                'razon_social': 'Clínicas del Sur - Polanco',
                'rfc': 'CDS040202PL1',
                'direccion': 'Av. Polanco 789, Col. Polanco, CDMX',
                'telefono': '55-5555-2001',
                'email': 'polanco@clinicasdelsur.com',
                'organizacion': organizaciones[1]
            },
            {
                'nombre': 'Sucursal Roma',
                'razon_social': 'Clínicas del Sur - Roma',
                'rfc': 'CDS040202RM2',
                'direccion': 'Av. Álvaro Obregón 321, Col. Roma, CDMX',
                'telefono': '55-5555-2002',
                'email': 'roma@clinicasdelsur.com',
                'organizacion': organizaciones[1]
            }
        ]

        sucursales = []
        for data in sucursales_data:
            org = data.pop('organizacion')
            sucursal = Sucursal(organizacion_id=org.id, **data)
            db.session.add(sucursal)
            sucursales.append(sucursal)

        db.session.commit()
        print(f"   [OK] {len(sucursales)} sucursales creadas")

        # Crear usuarios principales de cada sucursal y usuarios POS
        usuarios_sucursales = []
        for i, sucursal in enumerate(sucursales):
            # Usuario Principal de Sucursal
            usuario_principal = Usuario(
                username=f'sucursal{i+1}',
                email=f'admin@sucursal{i+1}.com',
                nombre_completo=f'Gerente - {sucursal.nombre}',
                rol='principal_sucursal',
                organizacion_id=sucursal.organizacion_id,
                sucursal_id=sucursal.id,
                activo=True
            )
            usuario_principal.set_password('sucursal123')
            db.session.add(usuario_principal)
            usuarios_sucursales.append(usuario_principal)

            # Usuarios POS (2 por sucursal)
            for j in range(2):
                usuario_pos = Usuario(
                    username=f'pos{i+1}_{j+1}',
                    email=f'pos{j+1}@sucursal{i+1}.com',
                    nombre_completo=f'Recepción {j+1} - {sucursal.nombre}',
                    rol='secundario_pos',
                    organizacion_id=sucursal.organizacion_id,
                    sucursal_id=sucursal.id,
                    puede_registrar_ingresos=True,
                    puede_registrar_egresos=j == 0,  # Solo POS 1 puede registrar egresos
                    puede_editar_movimientos=False,
                    puede_eliminar_movimientos=False,
                    puede_ver_reportes=False,
                    activo=True
                )
                usuario_pos.set_password('pos123')
                db.session.add(usuario_pos)
                usuarios_sucursales.append(usuario_pos)

        db.session.commit()
        print(f"   [OK] {len(sucursales)} gerentes de sucursal creados")
        print(f"   [OK] {len(sucursales) * 2} usuarios POS creados")

        # =====================================================
        # CATEGORÍAS (Nivel Organización + Nivel Sucursal)
        # =====================================================
        print("\n[4/7] Creando Categorías...")

        # Categorías a nivel ORGANIZACIÓN (compartidas por todas las sucursales)
        categorias_ingreso_org = [
            {'nombre': 'Consultas Generales', 'descripcion': 'Consultas médicas generales'},
            {'nombre': 'Urgencias', 'descripcion': 'Atención de urgencias médicas'},
            {'nombre': 'Cirugías', 'descripcion': 'Procedimientos quirúrgicos'}
        ]

        categorias_egreso_org = [
            {'nombre': 'Nómina', 'descripcion': 'Pago de salarios y prestaciones'},
            {'nombre': 'Servicios Públicos', 'descripcion': 'Luz, agua, internet, teléfono'},
            {'nombre': 'Arrendamiento', 'descripcion': 'Renta de inmuebles'}
        ]

        # Crear categorías organizacionales
        for org in organizaciones:
            for cat_data in categorias_ingreso_org:
                cat = CategoriaIngreso(
                    organizacion_id=org.id,
                    sucursal_id=None,
                    nombre=cat_data['nombre'],
                    descripcion=cat_data['descripcion']
                )
                db.session.add(cat)

            for cat_data in categorias_egreso_org:
                cat = CategoriaEgreso(
                    organizacion_id=org.id,
                    sucursal_id=None,
                    nombre=cat_data['nombre'],
                    descripcion=cat_data['descripcion']
                )
                db.session.add(cat)

        db.session.commit()
        print(f"   [OK] Categorías organizacionales creadas (compartidas)")

        # Categorías a nivel SUCURSAL (específicas de cada sucursal)
        categorias_ingreso_sucursal = [
            {'nombre': 'Tratamientos Especializados', 'descripcion': 'Tratamientos específicos de esta sucursal'},
            {'nombre': 'Otros Servicios', 'descripcion': 'Servicios diversos'}
        ]

        categorias_egreso_sucursal = [
            {'nombre': 'Materiales e Insumos', 'descripcion': 'Compra de materiales médicos'},
            {'nombre': 'Mantenimiento', 'descripcion': 'Mantenimiento de instalaciones'},
            {'nombre': 'Gastos Varios', 'descripcion': 'Gastos diversos de la sucursal'}
        ]

        # Crear categorías específicas de cada sucursal
        for sucursal in sucursales:
            for cat_data in categorias_ingreso_sucursal:
                cat = CategoriaIngreso(
                    organizacion_id=None,
                    sucursal_id=sucursal.id,
                    nombre=cat_data['nombre'],
                    descripcion=cat_data['descripcion']
                )
                db.session.add(cat)

            for cat_data in categorias_egreso_sucursal:
                cat = CategoriaEgreso(
                    organizacion_id=None,
                    sucursal_id=sucursal.id,
                    nombre=cat_data['nombre'],
                    descripcion=cat_data['descripcion']
                )
                db.session.add(cat)

        db.session.commit()
        print(f"   [OK] Categorías específicas de sucursales creadas")

        # =====================================================
        # PROVEEDORES (Nivel Organización - compartidos)
        # =====================================================
        print("\n[5/7] Creando Proveedores...")

        proveedores_data = [
            # Proveedores para Organización 1
            {
                'organizacion': organizaciones[0],
                'rfc': 'MED010101ABC',
                'razon_social': 'Distribuidora Médica del Norte SA de CV',
                'nombre_comercial': 'MediNorte',
                'email': 'ventas@medinorte.com',
                'telefono': '81-1111-2222'
            },
            {
                'organizacion': organizaciones[0],
                'rfc': 'LAB020202XYZ',
                'razon_social': 'Laboratorios Especializados SA de CV',
                'nombre_comercial': 'LabEsp',
                'email': 'contacto@labesp.com',
                'telefono': '81-3333-4444'
            },
            # Proveedores para Organización 2
            {
                'organizacion': organizaciones[1],
                'rfc': 'SUM030303DEF',
                'razon_social': 'Suministros Médicos del Sur SA de CV',
                'nombre_comercial': 'SumMed Sur',
                'email': 'ventas@summedsur.com',
                'telefono': '55-6666-7777'
            },
            {
                'organizacion': organizaciones[1],
                'rfc': 'EQU040404GHI',
                'razon_social': 'Equipamiento Hospitalario SA de CV',
                'nombre_comercial': 'EquiHospital',
                'email': 'info@equihospital.com',
                'telefono': '55-8888-9999'
            }
        ]

        for prov_data in proveedores_data:
            org = prov_data.pop('organizacion')
            proveedor = Proveedor(
                organizacion_id=org.id,
                validado=True,
                en_lista_negra=False,
                activo=True,
                **prov_data
            )
            db.session.add(proveedor)

        db.session.commit()
        print(f"   [OK] {len(proveedores_data)} proveedores creados")

        # =====================================================
        # MOVIMIENTOS (Ingresos y Egresos)
        # =====================================================
        print("\n[6/7] Generando movimientos de ejemplo...")

        hoy = date.today()
        fecha_inicio = hoy - timedelta(days=90)

        total_ingresos = 0
        total_egresos = 0

        for sucursal in sucursales:
            # Obtener categorías disponibles para esta sucursal
            # (organizacionales + específicas de sucursal)
            cats_ingreso = CategoriaIngreso.query.filter(
                db.or_(
                    CategoriaIngreso.organizacion_id == sucursal.organizacion_id,
                    CategoriaIngreso.sucursal_id == sucursal.id
                )
            ).all()

            cats_egreso = CategoriaEgreso.query.filter(
                db.or_(
                    CategoriaEgreso.organizacion_id == sucursal.organizacion_id,
                    CategoriaEgreso.sucursal_id == sucursal.id
                )
            ).all()

            # Obtener usuarios de esta sucursal
            usuarios = Usuario.query.filter_by(sucursal_id=sucursal.id).all()

            # Generar ingresos (50 por sucursal)
            for _ in range(50):
                dias_atras = random.randint(0, 90)
                fecha = fecha_inicio + timedelta(days=dias_atras)

                ingreso = Ingreso(
                    sucursal_id=sucursal.id,
                    usuario_id=random.choice(usuarios).id,
                    categoria_id=random.choice(cats_ingreso).id,
                    fecha=fecha,
                    monto=Decimal(str(random.randint(500, 8000))),
                    metodo_pago=random.choice(['efectivo', 'transferencia', 'tarjeta']),
                    notas='Movimiento de demostración'
                )
                db.session.add(ingreso)
                total_ingresos += 1

            # Generar egresos (30 por sucursal)
            for _ in range(30):
                dias_atras = random.randint(0, 90)
                fecha = fecha_inicio + timedelta(days=dias_atras)

                egreso = Egreso(
                    sucursal_id=sucursal.id,
                    usuario_id=random.choice(usuarios).id,
                    categoria_id=random.choice(cats_egreso).id,
                    fecha=fecha,
                    monto=Decimal(str(random.randint(200, 5000))),
                    metodo_pago=random.choice(['efectivo', 'transferencia', 'tarjeta']),
                    notas='Movimiento de demostración'
                )
                db.session.add(egreso)
                total_egresos += 1

        db.session.commit()
        print(f"   [OK] {total_ingresos} ingresos generados")
        print(f"   [OK] {total_egresos} egresos generados")

        # =====================================================
        # RESUMEN FINAL
        # =====================================================
        print("\n[7/7] Resumen de datos creados:")
        print(f"   • 1 Admin Despacho")
        print(f"   • {len(organizaciones)} Organizaciones")
        print(f"   • {len(sucursales)} Sucursales")
        print(f"   • {len(usuarios_org)} Directores de Organización")
        print(f"   • {len(sucursales)} Gerentes de Sucursal")
        print(f"   • {len(sucursales) * 2} Usuarios POS")
        print(f"   • Categorías (org + sucursal)")
        print(f"   • {len(proveedores_data)} Proveedores")
        print(f"   • {total_ingresos} Ingresos")
        print(f"   • {total_egresos} Egresos")

        print("\n" + "="*60)
        print("BASE DE DATOS POBLADA EXITOSAMENTE")
        print("="*60)
        print("\nUSUARIOS DE DEMOSTRACIÓN:")
        print("="*60)
        print("\n1. ADMIN DEL DESPACHO:")
        print("   Usuario: admin")
        print("   Password: admin123")
        print("   Acceso: Global a todas las organizaciones (solo lectura)")

        print("\n2. DIRECTORES DE ORGANIZACIÓN:")
        print("   Usuario: org1 / Password: org123")
        print("   Usuario: org2 / Password: org123")
        print("   Acceso: Todas las sucursales de su organización")

        print("\n3. GERENTES DE SUCURSAL:")
        print("   Usuario: sucursal1 / Password: sucursal123")
        print("   Usuario: sucursal2 / Password: sucursal123")
        print("   Usuario: sucursal3 / Password: sucursal123")
        print("   Usuario: sucursal4 / Password: sucursal123")
        print("   Acceso: Solo su sucursal")

        print("\n4. USUARIOS POS:")
        print("   Usuario: pos1_1 / Password: pos123  (puede ingresos y egresos)")
        print("   Usuario: pos1_2 / Password: pos123  (solo ingresos)")
        print("   Usuario: pos2_1 / Password: pos123  (puede ingresos y egresos)")
        print("   Usuario: pos2_2 / Password: pos123  (solo ingresos)")
        print("   ... (8 usuarios POS en total)")
        print("   Acceso: Solo registro en su sucursal")
        print("="*60)
        print("\nESTRUCTURA DE JERARQUÍA:")
        print("="*60)
        for org in organizaciones:
            print(f"\n{org.nombre} (RFC: {org.rfc})")
            suc_org = [s for s in sucursales if s.organizacion_id == org.id]
            for suc in suc_org:
                print(f"  |- {suc.nombre} (RFC: {suc.rfc})")
                users_suc = Usuario.query.filter_by(sucursal_id=suc.id).all()
                for user in users_suc:
                    print(f"      |- {user.nombre_completo} ({user.rol})")
        print("="*60 + "\n")


if __name__ == '__main__':
    seed_database()
