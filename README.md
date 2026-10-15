# Servicio de Arriendo de Maquinaria

Backend y sitio web desarrollado con Django, Django REST Framework y PostgreSQL.

**Autor:** Mario Sanzana  
**Sección:** AP-N4-C1

## Requisitos

- Python 3.14 o compatible con las versiones de `requirements.txt`.
- PostgreSQL instalado y en ejecución.
- Una base de datos PostgreSQL llamada `arriendo_maquinaria`.

## Instalación local

### 1. Crear el entorno virtual

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

En Linux o macOS:

```bash
python -m venv env
source env/bin/activate
```

### 2. Instalar las dependencias

```powershell
python -m pip install -r requirements.txt
```

### 3. Crear el archivo de variables de entorno

En PowerShell:

```powershell
Copy-Item .env.example .env
```

En Linux o macOS:

```bash
cp .env.example .env
```

Edita `.env` y reemplaza los valores de ejemplo. No subas este archivo a GitHub.

### 4. Configurar PostgreSQL

Crea la base si todavía no existe:

```sql
CREATE DATABASE arriendo_maquinaria;
```

Configura en `.env` el nombre de la base, usuario, contraseña, host y puerto:

```dotenv
POSTGRES_DB=arriendo_maquinaria
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_contraseña
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 5. Ejecutar las migraciones

```powershell
python manage.py migrate
```

Opcionalmente, carga las maquinarias de ejemplo:

```powershell
python populate_db.py
```

### 6. Iniciar el servidor

```powershell
python manage.py runserver
```

Sitio web: `http://127.0.0.1:8000/`  
Swagger: `http://127.0.0.1:8000/api/docs/`

## Pruebas

```powershell
python manage.py test
```

## Pago simulado con Webpay Plus

Los contratos pendientes incluyen el botón **Pagar reserva con Webpay**. La
configuración predeterminada usa el ambiente de integración de Transbank, sin
dinero real. Para probar un pago aprobado usa:

- VISA `4051885600446623`, CVV `123` y cualquier vencimiento futuro.
- En la autenticación bancaria: RUT `11.111.111-1` y clave `123`.

El retorno de Webpay se valida por estado, código de respuesta, monto, orden de
compra y sesión antes de marcar el contrato como `PAGADO` y reservar la flota.
Ejecuta las migraciones antes de probarlo:

```powershell
python manage.py migrate
```

Para producción configura `WEBPAY_ENVIRONMENT=production`,
`WEBPAY_COMMERCE_CODE` y `WEBPAY_API_KEY` con las credenciales del comercio.

## API principal

- `GET /api/maquinarias/`
- `GET|POST|PATCH|DELETE /api/carro-arriendo/`
- `POST /api/contratos/checkout/`
- `GET /api/mis-contratos/`
- `PATCH /api/contratos/{id}/estado/`
- `POST /api/token/`
- `POST /api/token/refresh/`

El proyecto no usa Django Admin como interfaz de negocio. La gestión se realiza desde el panel propio del Ejecutivo.
