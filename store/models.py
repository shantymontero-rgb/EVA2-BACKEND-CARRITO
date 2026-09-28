from django.db import models
from django.contrib.auth.models import User
import uuid

# Perfil para asignar roles (GESTOR_BODEGA o INSTITUCION_MEDICA)
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('INSTITUCION_MEDICA', 'Institución Médica / Comprador'),
        ('GESTOR_BODEGA', 'Gestor de Bodega (Admin)'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='INSTITUCION_MEDICA')
    institucion_nombre = models.CharField(max_length=150, blank=True, default='')

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


# Categoria aislada para cumplir 3FN (evita dependencias transitivas)
class CategoriaInsumo(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, default='')

    def __str__(self):
        return self.nombre


# Catalogo de insumos medicos con control de stock y lote
class Insumo(models.Model):
    categoria = models.ForeignKey(CategoriaInsumo, on_delete=models.PROTECT, related_name='insumos')
    nombre_comercial = models.CharField(max_length=180)
    principio_activo = models.CharField(max_length=180, blank=True)
    lote = models.CharField(max_length=60)
    fecha_vencimiento = models.DateField()
    precio_caja = models.DecimalField(max_digits=12, decimal_places=0)
    stock_cajas = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.nombre_comercial} (Lote: {self.lote})"


# Carro persistente vinculado 1:1 con el usuario
class Carro(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='carro_activo')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carro de {self.user.username}"


# Items dentro del carro (relacion carro e insumo)
class CarroItem(models.Model):
    carro = models.ForeignKey(Carro, on_delete=models.CASCADE, related_name='items')
    insumo = models.ForeignKey(Insumo, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('carro', 'insumo')


# Orden historica de compra y ciclo de vida de la transaccion
class SolicitudAbastecimiento(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Validación'),
        ('PAGADO', 'Pagado y Autorizado'),
        ('ENTREGADO', 'Entregado en Clínica'),
        ('CANCELADO', 'Cancelado / Quiebre Frío'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='solicitudes')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Calculo dinamico para no duplicar datos (3FN)
    @property
    def total(self):
        return sum(d.cantidad * d.precio_unitario_historico for d in self.detalles.all())

    def __str__(self):
        return f"Orden {str(self.id)[:8]} ({self.get_estado_display()})"


# Detalle inmutable de la compra (guarda precio y lote historico)
class SolicitudDetalle(models.Model):
    solicitud = models.ForeignKey(SolicitudAbastecimiento, on_delete=models.CASCADE, related_name='detalles')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    nombre_historico = models.CharField(max_length=180)
    lote_historico = models.CharField(max_length=60)
    precio_unitario_historico = models.DecimalField(max_digits=12, decimal_places=0)
    cantidad = models.PositiveIntegerField()
