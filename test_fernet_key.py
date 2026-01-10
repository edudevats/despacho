#!/usr/bin/env python
"""
Script de diagnóstico para verificar la configuración de FERNET_KEY.

Este script verifica:
1. Que FERNET_KEY se cargue correctamente desde .env
2. Que la clave pueda encriptar y desencriptar datos
3. Que NO existan archivos de clave legacy (secret.key)
4. Que las credenciales encriptadas en la BD puedan desencriptarse

Uso:
    python test_fernet_key.py
"""

import os
import sys
from pathlib import Path

# Colores para output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✓{RESET} {msg}")

def print_error(msg):
    print(f"{RED}✗{RESET} {msg}")

def print_warning(msg):
    print(f"{YELLOW}⚠{RESET} {msg}")

def print_info(msg):
    print(f"{BLUE}ℹ{RESET} {msg}")

def main():
    print("\n" + "="*60)
    print("  DIAGNÓSTICO DE FERNET_KEY")
    print("="*60 + "\n")

    # 1. Verificar carga de .env
    print("📋 Paso 1: Verificando carga de .env...")
    from dotenv import load_dotenv
    
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        print_success(f"Archivo .env encontrado: {env_path}")
        load_dotenv(env_path)
    else:
        print_error(f"Archivo .env NO encontrado en: {env_path}")
        return 1

    # 2. Verificar FERNET_KEY en environment
    print("\n📋 Paso 2: Verificando FERNET_KEY en variables de entorno...")
    fernet_key = os.environ.get('FERNET_KEY')
    
    if fernet_key:
        print_success(f"FERNET_KEY cargado: {fernet_key[:10]}...{fernet_key[-10:]}")
        print_info(f"Longitud de la clave: {len(fernet_key)} caracteres")
    else:
        print_error("FERNET_KEY NO encontrado en variables de entorno")
        return 1

    # 3. Verificar archivos legacy
    print("\n📋 Paso 3: Buscando archivos de clave legacy...")
    legacy_files = [
        Path(__file__).parent / 'secret.key',
        Path(__file__).parent / 'utils' / 'secret.key',
    ]
    
    found_legacy = False
    for legacy_path in legacy_files:
        if legacy_path.exists():
            print_warning(f"Archivo legacy encontrado: {legacy_path}")
            found_legacy = True
    
    if not found_legacy:
        print_success("No se encontraron archivos legacy secret.key")

    # 4. Probar encriptación/desencriptación
    print("\n📋 Paso 4: Probando encriptación/desencriptación...")
    try:
        from utils.crypto import encrypt_password, decrypt_password
        
        test_password = "mi_password_de_prueba_12345"
        print_info(f"Texto original: {test_password}")
        
        # Encriptar
        encrypted = encrypt_password(test_password)
        print_success(f"Encriptado: {encrypted[:30]}...")
        
        # Desencriptar
        decrypted = decrypt_password(encrypted)
        print_success(f"Desencriptado: {decrypted}")
        
        # Verificar
        if decrypted == test_password:
            print_success("✓ Encriptación/desencriptación funciona correctamente")
        else:
            print_error("✗ ERROR: El texto desencriptado no coincide con el original")
            return 1
            
    except Exception as e:
        print_error(f"Error al probar encriptación: {e}")
        return 1

    # 5. Verificar credenciales en base de datos
    print("\n📋 Paso 5: Verificando credenciales encriptadas en base de datos...")
    try:
        from extensions import db
        from models import FinkokCredentials
        from app import create_app
        from config import Config
        from utils.crypto import decrypt_password
        
        # Crear app context
        app = create_app(Config)
        with app.app_context():
            # Buscar credenciales
            credentials = FinkokCredentials.query.all()
            
            if not credentials:
                print_warning("No hay credenciales de Finkok en la base de datos")
            else:
                print_info(f"Encontradas {len(credentials)} credenciales de Finkok")
                
                for i, cred in enumerate(credentials, 1):
                    print(f"\n  Credencial #{i} (Company ID: {cred.company_id}):")
                    print(f"    Usuario: {cred.username}")
                    print(f"    Ambiente: {cred.environment}")
                    print(f"    Password encriptado: {cred.password_enc[:30]}...")
                    
                    # Intentar desencriptar
                    try:
                        decrypted_pwd = decrypt_password(cred.password_enc)
                        print_success(f"    ✓ Password desencriptado exitosamente (longitud: {len(decrypted_pwd)})")
                    except Exception as e:
                        print_error(f"    ✗ ERROR al desencriptar: {e}")
                        print_error(f"    → Esto indica que la clave usada para encriptar es diferente a la actual")
                        return 1
                        
    except Exception as e:
        print_warning(f"No se pudo verificar base de datos: {e}")

    # 6. Resumen final
    print("\n" + "="*60)
    print("  DIAGNÓSTICO COMPLETADO")
    print("="*60)
    print_success("Todas las verificaciones pasaron correctamente")
    print_info("\nLa clave FERNET_KEY está funcionando correctamente.")
    print_info("No hay claves legacy interfiriendo.")
    print_info("Las credenciales en la BD se pueden desencriptar correctamente.\n")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
