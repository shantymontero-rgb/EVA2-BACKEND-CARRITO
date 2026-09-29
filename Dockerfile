# MediSupply - Plataforma B2B de Abastecimiento Clínico y Farmacéutico

Sistema backend transaccional y robusto desarrollado con **Django** y **PostgreSQL** para la gestión de compras clínicas al por mayor, control de existencias en bodega y trazabilidad hospitalaria.

---

## 1. Cumplimiento de Normalización (Tercera Forma Normal - 3FN)

El diseño del modelo relacional cumple estrictamente con las tres primeras formas normales:

1. **Primera Forma Normal (1FN):**
   - Atributos indivisibles y atómicos (precios unitarios, códigos de lote, identificadores).
   - No existen grupos repetitivos ni listas incrustadas.
2. **Segunda Forma Normal (2FN):**
   - Todas las tablas poseen una clave primaria (id autonumérico o código único).
   - Cada atributo depende funcionalmente y en su totalidad de la clave primaria.
3. **Tercera Forma Normal (3FN):**
   - **Desacoplamiento de Entidades:** La entidad \CategoriaInsumo\ se separó completamente de \Insumo\ mediante una llave foránea (\ForeignKey\), eliminando redundancia y dependencias transitivas.
   - **Patrón Snapshot en Solicitudes:** La entidad \SolicitudDetalle\ almacena el \precio_unitario_historico\ y el \lote_historico\ al momento del checkout. Si los precios o lotes cambian a futuro en catálogo, el registro contable y auditor histórico permanece inalterable.
   - **Eliminación de Columnas Redundantes:** El monto total de las órdenes no es un campo fijo en la base de datos; se computa dinámicamente (\@property def total\) agregando los subtotales de \SolicitudDetalle\.

---

## 2. Flujo Transaccional e Integridad de Stock

* **Carro Persistente:** Se modela vinculado \1:1\ al usuario. Agregar insumos al carro no descuenta inventario físico.
* **Control de Concurrencia y Atomicidad:** El checkout implementa \@transaction.atomic\ junto con \select_for_update()\ sobre los registros de insumos. Esto previene condiciones de carrera (*race conditions*) y asegura que el stock solo se reduzca al pasar formalmente a estado \PAGADO\.
* **Reposición Automática:** Si una orden es cancelada (\CANCELADO\), el sistema restituye de forma atómica las unidades correspondientes a bodega.

---

## 3. Seguridad y Control de Acceso (RBAC + JWT)

El sistema utiliza autenticación basada en tokens **JSON Web Tokens (JWT)** mediante \djangorestframework-simplejwt\:
* **Claims Personalizados:** El token incluye de forma segura los claims \ole\, \username\ y \is_staff\.
* **Roles Implementados:**
  - \GESTOR_BODEGA\: Administrador con acceso al panel analítico de abastecimiento (\/bodega/\), gestión de insumos y reportes de riesgo de vencimiento.
  - \INSTITUCION_MEDICA\: Comprador clínico institucional con acceso a catálogo, carro y generación de órdenes de abastecimiento.

---

## 4. Endpoints y Documentación Interactiva

* **Catálogo Principal:** \/\
* **Carro de Compras:** \/cart/\
* **Control de Bodega:** \/bodega/\ (con alias en \/dashboard/\)
* **Documentación Swagger / OpenAPI:** \/docs/\
* **Directiva Anti-404:** Manejo integral de rutas inexistentes redirigiendo a la raíz.

---

## 5. Instrucciones de Despliegue Local

1. **Instalar dependencias:**
   \\\ash
   pip install -r requirements.txt
   \\\
2. **Aplicar migraciones:**
   \\\ash
   python manage.py migrate
   \\\
3. **Iniciar el servidor:**
   \\\ash
   python manage.py runserver
   \\\
"@ | Set-Content -Path "README.md" -Encoding UTF8
Write-Host "README.md generado con exito." -ForegroundColor Green
# Crear Dockerfile
@"
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
