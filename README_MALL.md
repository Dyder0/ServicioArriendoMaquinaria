# Servicio de Arriendo de Maquinaria

Aplicación Django + Django REST Framework con PostgreSQL para catálogo, carro persistente, contratos y gestión de flota.

## Puesta en marcha

```powershell
.\env\Scripts\python.exe -m pip install -r requirements.txt
.\env\Scripts\python.exe manage.py migrate
.\env\Scripts\python.exe populate_db.py
.\env\Scripts\python.exe manage.py runserver
```

La web queda en `http://127.0.0.1:8000/` y Swagger en `/api/docs/`.

## Usuarios y roles

- Los usuarios registrados en `/registro/` son `EMPRESA_CONSTRUCTORA`.
- Un usuario creado con `python manage.py createsuperuser` recibe el rol `EJECUTIVO_ARRIENDOS` y accede a `/panel/`. No se usa Django Admin.
- JWT: `POST /api/token/` y renovación en `POST /api/token/refresh/`.

## API principal

- `GET /api/maquinarias/`
- `GET|POST|DELETE /api/carro-arriendo/`
- `POST /api/contratos/checkout/`
- `GET /api/mis-contratos/`
- `PATCH /api/contratos/{id}/estado/`

Filtros del catálogo: `categoria`, `activo`, `precio_min`, `precio_max`, `semanal_min`, `semanal_max`, `search` y `ordering`. Para consultar disponibilidad por rango se pueden enviar `fecha_inicio` y `fecha_fin`.

## Pruebas

```powershell
.\env\Scripts\python.exe manage.py test
```
