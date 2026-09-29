from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Insumo, CategoriaInsumo, Carro, CarroItem, SolicitudAbastecimiento, SolicitudDetalle, UserProfile

# Helper: verifica si el usuario es administrador / gestor de bodega
def is_admin_user(user):
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile and profile.role == 'GESTOR_BODEGA'

# 1. Catálogo principal
def catalog_view(request):
    insumos = Insumo.objects.all().select_related('categoria').order_by('id')
    categorias = CategoriaInsumo.objects.all()
    carro_count = 0
    if request.user.is_authenticated:
        carro, _ = Carro.objects.get_or_create(user=request.user)
        carro_count = sum(item.cantidad for item in carro.items.all())
    return render(request, 'store/catalog.html', {
        'insumos': insumos,
        'categorias': categorias,
        'carro_count': carro_count,
        'is_admin': is_admin_user(request.user)
    })

# 2. Ver Carrito
def cart_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    carro, _ = Carro.objects.get_or_create(user=request.user)
    items = carro.items.select_related('insumo').all()
    total = sum(item.cantidad * item.insumo.precio_caja for item in items)
    return render(request, 'store/cart.html', {
        'items': items,
        'total': total,
        'is_admin': is_admin_user(request.user)
    })

# 3. Agregar al Carrito (soporta cantidad elegida)
def add_to_cart_view(request, insumo_id):
    if not request.user.is_authenticated:
        return redirect('login')
    insumo = get_object_or_404(Insumo, id=insumo_id)
    
    try:
        cantidad = int(request.POST.get('cantidad', 1))
        if cantidad < 1:
            cantidad = 1
    except (ValueError, TypeError):
        cantidad = 1

    carro, _ = Carro.objects.get_or_create(user=request.user)
    item, created = CarroItem.objects.get_or_create(carro=carro, insumo=insumo)
    
    if created:
        item.cantidad = min(cantidad, insumo.stock_cajas)
    else:
        item.cantidad = min(item.cantidad + cantidad, insumo.stock_cajas)
    item.save()
    messages.success(request, f"Se agregaron {cantidad} unidad(es) de {insumo.nombre_comercial}.")
    return redirect('catalog')

# 4. Actualizar cantidad en el carrito
def update_cart_view(request, item_id):
    if not request.user.is_authenticated:
        return redirect('login')
    item = get_object_or_404(CarroItem, id=item_id, carro__user=request.user)
    if request.method == 'POST':
        try:
            nueva_cantidad = int(request.POST.get('cantidad', 1))
            if nueva_cantidad > 0:
                item.cantidad = min(nueva_cantidad, item.insumo.stock_cajas)
                item.save()
            else:
                item.delete()
        except (ValueError, TypeError):
            pass
    return redirect('cart')

# 5. Quitar item del carrito
def remove_from_cart_view(request, item_id):
    if not request.user.is_authenticated:
        return redirect('login')
    item = get_object_or_404(CarroItem, id=item_id, carro__user=request.user)
    item.delete()
    messages.info(request, "Producto eliminado del carrito.")
    return redirect('cart')

# 6. Checkout / Pago con control de concurrencia (select_for_update)
@transaction.atomic
def checkout_view(request):
    if not request.user.is_authenticated:
        return redirect('login')

    carro = Carro.objects.filter(user=request.user).first()
    if not carro or not carro.items.exists():
        messages.warning(request, "Tu carro de compras está vacío.")
        return redirect('cart')

    items_carro = list(carro.items.all())
    # Validación de stock bloqueando filas temporalmente para evitar compras simultáneas
    for item in items_carro:
        insumo = Insumo.objects.select_for_update().get(id=item.insumo.id)
        if insumo.stock_cajas < item.cantidad:
            if insumo.stock_cajas == 0:
                messages.error(request, f"'{insumo.nombre_comercial}' se agotó recién en otra compra. Ajusta tu carro.")
            else:
                messages.error(request, f"Stock insuficiente para '{insumo.nombre_comercial}': solo quedan {insumo.stock_cajas} cajas.")
            return redirect('cart')

    # Crear solicitud pagada
    solicitud = SolicitudAbastecimiento.objects.create(user=request.user, estado='PAGADO')
    for item in items_carro:
        insumo = Insumo.objects.select_for_update().get(id=item.insumo.id)
        insumo.stock_cajas -= item.cantidad
        insumo.save()
        SolicitudDetalle.objects.create(
            solicitud=solicitud,
            insumo=insumo,
            cantidad=item.cantidad,
            precio_unitario_historico=insumo.precio_caja,
            lote_historico=insumo.lote
        )

    carro.items.all().delete()
    messages.success(request, f"¡Compra procesada con éxito! N° Solicitud #{solicitud.id}")
    return redirect('catalog')

# 7. Panel de Bodega (solo para el gestor)
def bodega_view(request):
    if not is_admin_user(request.user):
        return redirect('catalog')

    insumos = Insumo.objects.all()
    total_lotes = insumos.count()
    criticos_qs = insumos.filter(stock_cajas__lte=5)
    criticos_count = criticos_qs.count()

    hoy = timezone.now().date()
    un_ano_adelante = hoy + timedelta(days=365)
    riesgo_caducidad_qs = insumos.filter(fecha_vencimiento__lte=un_ano_adelante)
    riesgo_caducidad_count = riesgo_caducidad_qs.count()
    riesgo_caducidad_pct = int((riesgo_caducidad_count / total_lotes) * 100) if total_lotes > 0 else 0

    solicitudes_pagadas = SolicitudAbastecimiento.objects.filter(estado='PAGADO')
    total_recaudado = sum(s.total for s in solicitudes_pagadas)

    total_clientes = UserProfile.objects.filter(role='INSTITUCION_MEDICA').count()
    if total_clientes == 0:
        total_clientes = 1
    clientes_activos = solicitudes_pagadas.values('user').distinct().count()
    alcance_pct = int((clientes_activos / total_clientes) * 100) if total_clientes > 0 else 0

    return render(request, 'store/bodega.html', {
        'insumos_criticos': criticos_qs,
        'stock_critico_count': criticos_count,
        'riesgo_caducidad_count': riesgo_caducidad_count,
        'riesgo_caducidad_pct': riesgo_caducidad_pct,
        'total_lotes': total_lotes,
        'recaudacion_total': total_recaudado,
        'ordenes_pagadas_count': solicitudes_pagadas.count(),
        'alcance_pct': alcance_pct,
        'clientes_activos': clientes_activos,
        'total_clientes': total_clientes,
        'is_admin': True
    })

# 8. Registro de usuario simple (con prompt/mensaje de éxito)
def register_view(request):
    error = None
    if request.method == 'POST':
        nombre_usuario = request.POST.get('username', '').strip()
        clave = request.POST.get('password', '').strip()

        if not nombre_usuario or not clave:
            error = "Ingresa un usuario y una contraseña."
        elif User.objects.filter(username=nombre_usuario).exists():
            error = "Ese usuario ya existe, prueba con otro."
        else:
            nuevo_usuario = User.objects.create_user(username=nombre_usuario, password=clave)
            UserProfile.objects.create(
                user=nuevo_usuario,
                role='INSTITUCION_MEDICA',
                institucion_nombre=nombre_usuario
            )
            login(request, nuevo_usuario)
            messages.success(request, f"¡Bienvenido/a {nombre_usuario}! Tu cuenta ha sido creada exitosamente.")
            return redirect('catalog')

    return render(request, 'store/register.html', {'error': error})

# 9. Login y Logout
def login_view(request):
    error = None
    if request.method == 'POST':
        u = request.POST.get('username', '').strip()
        p = request.POST.get('password', '').strip()
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            messages.success(request, f"Sesión iniciada como {user.username}.")
            if is_admin_user(user):
                return redirect('bodega')
            return redirect('catalog')
        else:
            error = "Credenciales inválidas."
    return render(request, 'store/login.html', {'error': error})

def logout_view(request):
    logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect('login')

# 10. API REST para Swagger
class InsumoListAPI(APIView):
    """Retorna el listado de insumos y stock disponible"""
    def get(self, request):
        insumos = Insumo.objects.all().values('id', 'nombre_comercial', 'principio_activo', 'lote', 'stock_cajas', 'precio_caja')
        return Response(list(insumos))