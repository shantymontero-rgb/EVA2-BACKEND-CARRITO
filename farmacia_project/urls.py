"""
ENRUTAMIENTO PRINCIPAL - SISTEMA B2B FARMACIA Y MEDICINA
Cumple con la Matriz de Endpoints y Requerimiento re_path Anti-404
"""
from django.contrib import admin
from django.urls import path, re_path
from django.shortcuts import redirect
from rest_framework_simplejwt.views import TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

from store.serializers import CustomTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class CustomTokenView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

from store.views import (
    catalog_view, cart_view, login_view, dashboard_view,
    InsumoListCreateAPI, InsumoDetailAPI,
    CarroInsumosAPI, CarroItemDetailAPI,
    ConfirmarSolicitudCheckoutAPI, MisSolicitudesAPI,
    CambiarEstadoSolicitudAPI, BodegaDashboardStatsAPI
)

schema_view = get_schema_view(
   openapi.Info(
      title="API Insumos Medicos y Farmacia B2B",
      default_version='v1',
      description="Documentacion interactiva Swagger para Sistema de Abastecimiento Clinico",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Vistas Web de Presentacion
    path('', catalog_view, name='home'),
    path('carro/', cart_view, name='cart_view'),
    path('login/', login_view, name='login_view'),
    path('dashboard/', dashboard_view, name='dashboard_view'),

    # Autenticacion JWT con Claims de Rol
    path('api/token/', CustomTokenView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # MATRIZ OFICIAL: Insumos (Publico / Gestor)
    path('api/insumos/', InsumoListCreateAPI.as_view(), name='api_insumos'),
    path('api/insumos/<int:pk>/', InsumoDetailAPI.as_view(), name='api_insumo_detail'),

    # MATRIZ OFICIAL: Carro Insumos (Institucion Medica)
    path('api/carro-insumos/', CarroInsumosAPI.as_view(), name='api_carro_insumos'),
    path('api/carro-insumos/<int:pk>/', CarroItemDetailAPI.as_view(), name='api_carro_item_detail'),

    # MATRIZ OFICIAL: Solicitudes y Checkout
    path('api/solicitudes/confirmar/', ConfirmarSolicitudCheckoutAPI.as_view(), name='api_confirmar_solicitud'),
    path('api/mis-solicitudes/', MisSolicitudesAPI.as_view(), name='api_mis_solicitudes'),
    path('api/solicitudes/<uuid:pk>/estado/', CambiarEstadoSolicitudAPI.as_view(), name='api_cambiar_estado'),

    # Dashboard y Metricas de Bodega
    path('api/admin/dashboard/', BodegaDashboardStatsAPI.as_view(), name='api_dashboard'),

    # Swagger / OpenAPI
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='swagger-ui'),

    # re_path para eliminar error 404 (Requerimiento de Catedra)
    re_path(r'^.*$', lambda request: redirect('/')),
]
