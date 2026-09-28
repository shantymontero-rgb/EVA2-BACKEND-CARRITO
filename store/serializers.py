"""
SERIALIZADORES - SISTEMA B2B FARMACEUTICO
Incluye Custom Claims en JWT (Rol y Perfil) y Serializadores de Insumos y Ordenes
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Insumo, CarroItem, SolicitudAbastecimiento, SolicitudDetalle, UserProfile

# Custom JWT Token Serializer con Claims de Rol
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        profile = getattr(user, 'profile', None)
        role = profile.role if profile else ('GESTOR_BODEGA' if user.is_staff or user.is_superuser else 'INSTITUCION_MEDICA')
        
        token['username'] = user.username
        token['role'] = role
        token['is_staff'] = user.is_staff
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        profile = getattr(self.user, 'profile', None)
        role = profile.role if profile else ('GESTOR_BODEGA' if self.user.is_staff or self.user.is_superuser else 'INSTITUCION_MEDICA')
        data['username'] = self.user.username
        data['role'] = role
        return data


class InsumoSerializer(serializers.ModelSerializer):
    categoria_display = serializers.CharField(source='get_categoria_display', read_only=True)

    class Meta:
        model = Insumo
        fields = [
            'id', 'nombre_comercial', 'principio_activo', 'lote', 
            'fecha_vencimiento', 'categoria', 'categoria_display', 
            'precio_caja', 'stock_cajas'
        ]


class CarroItemSerializer(serializers.ModelSerializer):
    insumo_nombre = serializers.CharField(source='insumo.nombre_comercial', read_only=True)
    principio_activo = serializers.CharField(source='insumo.principio_activo', read_only=True)
    lote = serializers.CharField(source='insumo.lote', read_only=True)
    precio_caja = serializers.DecimalField(source='insumo.precio_caja', max_digits=12, decimal_places=0, read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CarroItem
        fields = ['id', 'insumo', 'insumo_nombre', 'principio_activo', 'lote', 'precio_caja', 'cantidad', 'subtotal']

    def get_subtotal(self, obj):
        return obj.cantidad * obj.insumo.precio_caja


class SolicitudDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudDetalle
        fields = ['id', 'insumo', 'nombre_historico', 'lote_historico', 'precio_unitario_historico', 'cantidad']


class SolicitudAbastecimientoSerializer(serializers.ModelSerializer):
    detalles = SolicitudDetalleSerializer(many=True, read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    cliente_username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = SolicitudAbastecimiento
        fields = ['id', 'user', 'cliente_username', 'estado', 'estado_display', 'total', 'detalles', 'created_at', 'updated_at']
