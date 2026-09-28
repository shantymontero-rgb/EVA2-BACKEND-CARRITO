"""
MODULO DE MODELOS - SISTEMA B2B FARMACEUTICO Y MEDICO
Evaluacion 2: Modelos con CHOICES, Relacion 1:1 de Carro y Transacciones
"""
from django.db import models
from django.contrib.auth.models import User
import uuid

# 1. Perfil de Usuario con Rol para Claims JWT
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('INSTITUCION_MEDICA', 'Institucion Medica (Cliente)'),
        ('GESTOR_BODEGA', 'Gestor de Bodega Farmaceutica (Admin)'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='INSTITUCION_MEDICA')
    institucion_nombre = models.CharField(max_length=150, blank=True, default='')

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


# 2. Insumos Medicos y Farmacos con Lote y Vencimiento
class Insumo(models.Model):
    CATEGORY_CHOICES = [
        ('QUIRURGICO', 'Material Quirurgico'),
        ('MEDICAMENTO', 'Medicamentos & Farmacos'),
        ('EQUIPAMIENTO', 'Equipamiento Clinico'),
    ]

    nombre_comercial = models.CharField(max_length=180)
    principio_activo = models.CharField(max_length=180, blank=True)
    lote = models.CharField(max_length=60)
    fecha_vencimiento = models.DateField()
    categoria = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='MEDICAMENTO')
    precio_caja = models.DecimalField(max_digits=12, decimal_places=0)
    stock_cajas = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.nombre_comercial} (Lote: {self.lote}) - Stock: {self.stock_cajas}"


# 3. Carro Persistente (Relacion 1:1 con Usuario)
class Carro(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='carro_activo')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carro de {self.user.username}"


class CarroItem(models.Model):
    carro = models.ForeignKey(Carro, on_delete=models.CASCADE, related_name='items')
    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('carro', 'insumo')

    def __str__(self):
        return f"{self.cantidad} cajas de {self.insumo.nombre_comercial}"


# 4. Solicitud de Abastecimiento Historica y Detalle
class SolicitudAbastecimiento(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Validacion'),
        ('PAGADO', 'Pagado y Autorizado'),
        ('ENTREGADO', 'Entregado en Clinica'),
        ('CANCELADO', 'Cancelado / Quiebre Frio'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='solicitudes')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    total = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Solicitud {str(self.id)[:8]} - {self.user.username} ({self.get_estado_display()})"


class SolicitudDetalle(models.Model):
    solicitud = models.ForeignKey(SolicitudAbastecimiento, on_delete=models.CASCADE, related_name='detalles')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    nombre_historico = models.CharField(max_length=180)
    lote_historico = models.CharField(max_length=60)
    precio_unitario_historico = models.DecimalField(max_digits=12, decimal_places=0)
    cantidad = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.cantidad}x {self.nombre_historico} en orden {str(self.solicitud.id)[:8]}"
