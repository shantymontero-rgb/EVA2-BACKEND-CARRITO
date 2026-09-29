from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

urlpatterns = [
    # Tienda y Carro
    path('', views.catalog_view, name='catalog'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:insumo_id>/', views.add_to_cart_view, name='add_to_cart'),
    path('cart/update/<int:item_id>/', views.update_cart_view, name='update_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart_view, name='remove_from_cart'),
    path('cart/checkout/', views.checkout_view, name='checkout'),

    # Usuarios y Autenticación
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Bodega
    path('bodega/', views.bodega_view, name='bodega'),

    # API REST para Swagger
    path('api/insumos/', views.InsumoListAPI.as_view(), name='api_insumos'),
    path('api/token/', TokenObtainPairView.as_view(), name='api_token'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
]
