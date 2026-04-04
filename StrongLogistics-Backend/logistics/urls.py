from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    MaterialViewSet, LocationViewSet, InventoryViewSet, 
    VehicleViewSet, OrderViewSet, OrderItemViewSet, AnalyticsView
)

router = DefaultRouter()
router.register(r'materials', MaterialViewSet)
router.register(r'locations', LocationViewSet)
router.register(r'inventories', InventoryViewSet)
router.register(r'vehicles', VehicleViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'order-items', OrderItemViewSet)

urlpatterns = [
    # API endpoints
    path('analytics/', AnalyticsView.as_view(), name='analytics'),
    path('', include(router.urls)),
    
    # JWT Auth tokens
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
