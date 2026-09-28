from django.shortcuts import render
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from django_filters.rest_framework import DjangoFilterBackend
from datetime import date, timedelta
from django.contrib.auth.models import User

from .models import Insumo, CategoriaInsumo, Carro, CarroItem, SolicitudAbastecimiento, SolicitudDetalle
from .serializers import InsumoSerializer, CarroItemSerializer, SolicitudAbastecimientoSerializer

# Vistas de renderizado HTML
def catalog_view(request):
    return render(request, 'store/catalog.html')

def cart_view(request):
    return render(request, 'store/cart.html')

def login_view(request):
    return render(request, 'store/login.html')

def dashboard_view(request):
    return render(request, 'store/dashboard.html')


# Permiso exclusivo para Gestor de Bodega
class IsGestorBodega(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, 'profile', None)
        return request.user.is_superuser or request.user.is_staff or (profile and profile.role == 'GESTOR_BODEGA')


# Catalogo publico con calculo de stock disponible
class InsumoListCreateAPI(generics.ListCreateAPIView):
    queryset = Insumo.objects.select_related('categoria').all().order_by('nombre_comercial')
    serializer_class = InsumoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['categoria__codigo', 'lote']

    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [IsGestorBodega()]

    def list(self, request, *args, **kwargs):
        cat_param = request.query_params.get('categoria')
        queryset = self.filter_queryset(self.get_queryset())
        if cat_param:
            queryset = queryset.filter(categoria__codigo=cat_param)

        serializer = self.get_serializer(queryset, many=True)
        data = list(serializer.data)

        # Descuenta visualmente lo que el usuario ya reservo en su carro
        user_cart = {}
        if request.user.is_authenticated:
            carro, _ = Carro.objects.get_or_create(user=request.user)
            for item in carro.items.all():
                user_cart[item.insumo_id] = item.cantidad

        for item_data in data:
            insumo_id = item_data['id']
            base_stock = item_data['stock_cajas']
            in_cart = user_cart.get(insumo_id, 0)
            item_data['in_cart'] = in_cart
            item_data['available_stock'] = max(0, base_stock - in_cart)

        return Response(data, status=status.HTTP_200_OK)


# Detalle y modificacion de insumo (solo admin)
class InsumoDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    queryset = Insumo.objects.all()
    serializer_class = InsumoSerializer
    permission_classes = [IsGestorBodega]


# Manejo del carro de compras (obtener items y agregar)
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
        # Valida cantidad y existencia sin descontar de la bodega todavia
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
        current_in_cart = 0 if created else item.cantidad
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


# Modificar cantidad o eliminar un item especifico del carro
class CarroItemDetailAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
            return Response({'error': f'Supera el stock fisico ({item.insumo.stock_cajas} disp.)'}, status=status.HTTP_400_BAD_REQUEST)

        item.cantidad = new_qty
        item.save()
        return Response({'message': 'Cantidad actualizada'}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        try:
            item = CarroItem.objects.get(pk=pk, carro__user=request.user)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CarroItem.DoesNotExist:
            return Response({'error': 'Item no encontrado'}, status=status.HTTP_404_NOT_FOUND)


# Checkout: descuento atomico de stock al confirmar el pago
class ConfirmarSolicitudCheckoutAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        carro, _ = Carro.objects.get_or_create(user=request.user)
        items = list(carro.items.select_related('insumo').select_for_update().all())

        if not items:
            return Response({'error': 'La solicitud esta vacia'}, status=status.HTTP_400_BAD_REQUEST)

        # Valida que todos tengan stock antes de proceder
        for item in items:
            if item.insumo.stock_cajas < item.cantidad:
                return Response({
                    'error': f'Stock insuficiente para "{item.insumo.nombre_comercial}". Stock: {item.insumo.stock_cajas}'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Crea orden en estado PAGADO
        solicitud = SolicitudAbastecimiento.objects.create(
            user=request.user,
            estado='PAGADO'
        )

        # Guarda snapshot historico y descuenta inventario
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
        return Response({'message': 'Solicitud procesada con exito.', 'solicitud': serializer.data}, status=status.HTTP_201_CREATED)


# Historial de compras del usuario autenticado
class MisSolicitudesAPI(generics.ListAPIView):
    serializer_class = SolicitudAbastecimientoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SolicitudAbastecimiento.objects.filter(user=self.request.user).order_by('-created_at')


# Cambio de estado de orden y reposicion automatica ante CANCELADO
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

        # Si se cancela una orden pagada, se devuelve el stock a bodega
        if nuevo_estado == 'CANCELADO' and solicitud.estado == 'PAGADO':
            for det in solicitud.detalles.select_related('insumo').all():
                insumo = det.insumo
                insumo.stock_cajas += det.cantidad
                insumo.save()

        solicitud.estado = nuevo_estado
        solicitud.save()
        return Response({'message': f'Estado: {solicitud.get_estado_display()}', 'estado': solicitud.estado}, status=status.HTTP_200_OK)


# Metricas del dashboard: riesgo de vencimiento, stock critico, recaudacion y alcance
class BodegaDashboardStatsAPI(APIView):
    permission_classes = [IsGestorBodega]

    def get(self, request):
        insumos = Insumo.objects.all()
        total_insumos = insumos.count()
        insumos_criticos = insumos.filter(stock_cajas__lte=5)
        
        # Metrica: insumos con vencimiento a menos de 1 ano
        fecha_umbral = date.today() + timedelta(days=365)
        insumos_vencimiento_proximo = insumos.filter(fecha_vencimiento__lte=fecha_umbral)
        tasa_riesgo_vencimiento = round((insumos_vencimiento_proximo.count() / total_insumos * 100), 1) if total_insumos > 0 else 0

        # Total recaudado en ordenes pagadas o entregadas
        solicitudes = SolicitudAbastecimiento.objects.filter(estado__in=['PAGADO', 'ENTREGADO'])
        total_recaudado = sum(s.total for s in solicitudes)
        
        # Metrica: alcance de clientes con carros activos
        carro_items = CarroItem.objects.all()
        carro_users_count = carro_items.values('carro__user').distinct().count()
        total_clientes = User.objects.filter(profile__role='INSTITUCION_MEDICA').count()
        reach = round((carro_users_count / total_clientes * 100), 1) if total_clientes > 0 else 0

        return Response({
            'total_insumos': total_insumos,
            'criticos_count': insumos_criticos.count(),
            'insumos_criticos': InsumoSerializer(insumos_criticos, many=True).data,
            'vencimiento_proximo_count': insumos_vencimiento_proximo.count(),
            'tasa_riesgo_vencimiento': tasa_riesgo_vencimiento,
            'total_solicitudes': SolicitudAbastecimiento.objects.count(),
            'total_recaudado': total_recaudado,
            'reach_percentage': reach,
            'carro_users_count': carro_users_count,
            'total_instituciones': total_clientes
        }, status=status.HTTP_200_OK)
