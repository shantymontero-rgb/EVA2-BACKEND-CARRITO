"""
ENRUTAMIENTO PRINCIPAL - SISTEMA B2B FARMACIA Y MEDICINA
"""
from django.contrib import admin
from django.urls import path, re_path
from django.shortcuts import redirect
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

from store.serializers import CustomTokenObtainPairSerializer
from store.views import (
    catalog_view, cart_view, login_view, bodega_view,
    InsumoListCreateAPI, InsumoDetailAPI,
    CarroInsumosAPI, CarroItemDetailAPI,
    ConfirmarSolicitudCheckoutAPI, MisSolicitudesAPI,
    CambiarEstadoSolicitudAPI, BodegaDashboardStatsAPI
)

class CustomTokenView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

schema_view = get_schema_view(
   openapi.Info(
      title="API Insumos Médicos y Farmacia B2B",
      default_version='v1',
      description="Documentación interactiva Swagger para Sistema de Abastecimiento Clínico",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Vistas Web HTML (ambas rutas funcionando)
    path('', catalog_view, name='home'),
    path('carro/', cart_view, name='cart_view'),
    path('login/', login_view, name='login_view'),
    path('dashboard/', bodega_view, name='dashboard_view'),
    path('bodega/', bodega_view, name='bodega_view'),

    # Autenticación JWT
    path('api/token/', CustomTokenView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Endpoints API
    path('api/insumos/', InsumoListCreateAPI.as_view(), name='api_insumos'),
    path('api/insumos/<int:pk>/', InsumoDetailAPI.as_view(), name='api_insumo_detail'),
    path('api/carro-insumos/', CarroInsumosAPI.as_view(), name='api_carro_insumos'),
    path('api/carro-insumos/<int:pk>/', CarroItemDetailAPI.as_view(), name='api_carro_item_detail'),
    path('api/solicitudes/confirmar/', ConfirmarSolicitudCheckoutAPI.as_view(), name='api_confirmar_solicitud'),
    path('api/mis-solicitudes/', MisSolicitudesAPI.as_view(), name='api_mis_solicitudes'),
    path('api/solicitudes/<uuid:pk>/estado/', CambiarEstadoSolicitudAPI.as_view(), name='api_cambiar_estado'),
    path('api/admin/dashboard/', BodegaDashboardStatsAPI.as_view(), name='api_dashboard'),

    # Swagger
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='swagger-ui'),

    # Anti-404
    re_path(r'^.*$', lambda request: redirect('/')),
]
