"""
CONTROLADORES Y ENDPOINTS B2B - FARMACIA & INSUMOS MEDICOS
Manejo de Stock Atomico, Roles RBAC, Edicion en Carro y Metricas B2B
"""
from django.shortcuts import render
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from django_filters.rest_framework import DjangoFilterBackend
from datetime import date, timedelta
from django.contrib.auth.models import User

from .models import Insumo, Carro, CarroItem, SolicitudAbastecimiento, SolicitudDetalle
from .serializers import InsumoSerializer, CarroItemSerializer, SolicitudAbastecimientoSerializer

def catalog_view(request):
    return render(request, 'store/catalog.html')

def cart_view(request):
    return render(request, 'store/cart.html')

def login_view(request):
    return render(request, 'store/login.html')

def dashboard_view(request):
    return render(request, 'store/dashboard.html')


class IsGestorBodega(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, 'profile', None)
        return request.user.is_superuser or request.user.is_staff or (profile and profile.role == 'GESTOR_BODEGA')


# 1. CATALOGO CON STOCK DINAMICO SEGUN LO RESERVADO EN EL CARRO
class InsumoListCreateAPI(generics.ListCreateAPIView):
    queryset = Insumo.objects.all().order_by('nombre_comercial')
    serializer_class = InsumoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['categoria', 'lote']

    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [IsGestorBodega()]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        user_cart = {}
        if request.user.is_authenticated:
            carro, _ = Carro.objects.get_or_create(user=request.user)
            for item in carro.items.all():
                user_cart[item.insumo_id] = item.cantidad

        for item_data in response.data:
            insumo_id = item_data['id']
            base_stock = item_data['stock_cajas']
            in_cart = user_cart.get(insumo_id, 0)
            item_data['in_cart'] = in_cart
            item_data['available_stock'] = max(0, base_stock - in_cart)

        return response


class InsumoDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    queryset = Insumo.objects.all()
    serializer_class = InsumoSerializer
    permission_classes = [IsGestorBodega]


# 2. CARRO DE INSUMOS CON EDICION Y CONTEO DE UNIDADES
class CarroInsumosAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_carro(self, user):
        carro, _ = Carro.objects.get_or_create(user=user)
        return carro

    def get(self, request):
        carro = self.get_carro(request.user)
        items = carro.items.select_related('insumo').all()
        serializer = CarroItemSerializer(items, many=True)
        total = sum(item.cantidad * item.insumo.precio_caja for item in items)
        total_items_count = sum(item.cantidad for item in items)
        return Response({
            'items': serializer.data,
            'total_items_count': total_items_count,
            'monto_total': total
        }, status=status.HTTP_200_OK)

    def post(self, request):
        carro = self.get_carro(request.user)
        insumo_id = request.data.get('insumo')
        try:
            cantidad = int(request.data.get('cantidad', 1))
        except (ValueError, TypeError):
            return Response({'error': 'Cantidad no valida'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            insumo = Insumo.objects.get(id=insumo_id)
        except Insumo.DoesNotExist:
            return Response({'error': 'Insumo no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        item, created = CarroItem.objects.get_or_create(carro=carro, insumo=insumo)
        current_in_cart = 0 if created else (item.cantidad)
        total_solicitado = current_in_cart + cantidad

        if total_solicitado > insumo.stock_cajas:
            disp = max(0, insumo.stock_cajas - current_in_cart)
            return Response({'error': f'Stock insuficiente. Disponibles: {disp}. Ya tienes {current_in_cart} en el carro.'}, status=status.HTTP_400_BAD_REQUEST)

        item.cantidad = total_solicitado
        item.save()

        total_items = sum(i.cantidad for i in carro.items.all())
        return Response({
            'message': f'Insumo reservado. Tienes {item.cantidad} cajas de este insumo.',
            'total_items_count': total_items
        }, status=status.HTTP_201_CREATED)


class CarroItemDetailAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    # PUT: Edicion interactiva de la cantidad de cajas en el carro
    def put(self, request, pk):
        try:
            item = CarroItem.objects.get(pk=pk, carro__user=request.user)
        except CarroItem.DoesNotExist:
            return Response({'error': 'Item no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            new_qty = int(request.data.get('cantidad', 1))
        except (ValueError, TypeError):
            return Response({'error': 'Cantidad no valida'}, status=status.HTTP_400_BAD_REQUEST)

        if new_qty <= 0:
            item.delete()
            return Response({'message': 'Item eliminado del carro'}, status=status.HTTP_200_OK)

        if new_qty > item.insumo.stock_cajas:
            return Response({'error': f'Supera el stock fisico en bodega ({item.insumo.stock_cajas} disp.)'}, status=status.HTTP_400_BAD_REQUEST)

        item.cantidad = new_qty
        item.save()
        return Response({'message': 'Cantidad actualizada con exito'}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        try:
            item = CarroItem.objects.get(pk=pk, carro__user=request.user)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CarroItem.DoesNotExist:
            return Response({'error': 'Item no encontrado'}, status=status.HTTP_404_NOT_FOUND)


# 3. CHECKOUT ATOMICO Y TRANSACCION
class ConfirmarSolicitudCheckoutAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        carro, _ = Carro.objects.get_or_create(user=request.user)
        items = list(carro.items.select_related('insumo').select_for_update().all())

        if not items:
            return Response({'error': 'La solicitud esta vacia'}, status=status.HTTP_400_BAD_REQUEST)

        for item in items:
            if item.insumo.stock_cajas < item.cantidad:
                return Response({
                    'error': f'Stock insuficiente para "{item.insumo.nombre_comercial}". Stock: {item.insumo.stock_cajas}'
                }, status=status.HTTP_400_BAD_REQUEST)

        total_solicitud = sum(item.cantidad * item.insumo.precio_caja for item in items)
        solicitud = SolicitudAbastecimiento.objects.create(
            user=request.user,
            estado='PAGADO',
            total=total_solicitud
        )

        for item in items:
            SolicitudDetalle.objects.create(
                solicitud=solicitud,
                insumo=item.insumo,
                nombre_historico=item.insumo.nombre_comercial,
                lote_historico=item.insumo.lote,
                precio_unitario_historico=item.insumo.precio_caja,
                cantidad=item.cantidad
            )
            item.insumo.stock_cajas -= item.cantidad
            item.insumo.save()

        carro.items.all().delete()
        serializer = SolicitudAbastecimientoSerializer(solicitud)
        return Response({'message': 'Solicitud pagada y procesada.', 'solicitud': serializer.data}, status=status.HTTP_201_CREATED)


class MisSolicitudesAPI(generics.ListAPIView):
    serializer_class = SolicitudAbastecimientoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SolicitudAbastecimiento.objects.filter(user=self.request.user).order_by('-created_at')


class CambiarEstadoSolicitudAPI(APIView):
    permission_classes = [IsGestorBodega]

    @transaction.atomic
    def patch(self, request, pk):
        try:
            solicitud = SolicitudAbastecimiento.objects.select_for_update().get(pk=pk)
        except SolicitudAbastecimiento.DoesNotExist:
            return Response({'error': 'Solicitud no encontrada'}, status=status.HTTP_404_NOT_FOUND)

        nuevo_estado = request.data.get('estado')
        if nuevo_estado not in dict(SolicitudAbastecimiento.ESTADO_CHOICES):
            return Response({'error': 'Estado invalido'}, status=status.HTTP_400_BAD_REQUEST)

        if nuevo_estado == 'CANCELADO' and solicitud.estado == 'PAGADO':
            for det in solicitud.detalles.select_related('insumo').all():
                insumo = det.insumo
                insumo.stock_cajas += det.cantidad
                insumo.save()

        solicitud.estado = nuevo_estado
        solicitud.save()
        return Response({'message': f'Estado: {solicitud.get_estado_display()}', 'estado': solicitud.estado}, status=status.HTTP_200_OK)


# 4. DASHBOARD CON NUEVA METRICA DE RIESGO DE VENCIMIENTO
class BodegaDashboardStatsAPI(APIView):
    permission_classes = [IsGestorBodega]

    def get(self, request):
        insumos = Insumo.objects.all()
        total_insumos = insumos.count()
        insumos_criticos = insumos.filter(stock_cajas__lte=5)
        
        # Nueva Metrica: Lotes con vencimiento menor a 1 ano (365 dias)
        fecha_umbral = date.today() + timedelta(days=365)
        insumos_vencimiento_proximo = insumos.filter(fecha_vencimiento__lte=fecha_umbral)
        tasa_riesgo_vencimiento = round((insumos_vencimiento_proximo.count() / total_insumos * 100), 1) if total_insumos > 0 else 0

        solicitudes = SolicitudAbastecimiento.objects.all()
        total_recaudado = sum(s.total for s in solicitudes.filter(estado__in=['PAGADO', 'ENTREGADO']))
        
        carro_items = CarroItem.objects.all()
        carro_users_count = carro_items.values('carro__user').distinct().count()
        total_medicos = User.objects.filter(profile__role='INSTITUCION_MEDICA').count()
        reach = round((carro_users_count / total_medicos * 100), 1) if total_medicos > 0 else 0

        return Response({
            'total_insumos': total_insumos,
            'criticos_count': insumos_criticos.count(),
            'insumos_criticos': InsumoSerializer(insumos_criticos, many=True).data,
            'vencimiento_proximo_count': insumos_vencimiento_proximo.count(),
            'tasa_riesgo_vencimiento': tasa_riesgo_vencimiento,
            'total_solicitudes': solicitudes.count(),
            'total_recaudado': total_recaudado,
            'reach_percentage': reach,
            'carro_users_count': carro_users_count,
            'total_instituciones': total_medicos
        }, status=status.HTTP_200_OK)
