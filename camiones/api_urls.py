from django.urls import path
from rest_framework.routers import DefaultRouter

from camiones import api_views

router = DefaultRouter()
router.register(r'clientes', api_views.ClienteViewSet)
router.register(r'clientes-sucursal', api_views.ClienteSucursalViewSet)
router.register(r'bodegas', api_views.BodegaViewSet)
router.register(r'clientes-bodega', api_views.ClienteBodegaViewSet)
router.register(r'clientes-producto', api_views.ClienteProductoViewSet)
router.register(r'operaciones', api_views.OperacionViewSet)
router.register(r'kardex', api_views.KardexLineaViewSet)
router.register(r'pesajes', api_views.PesajeViewSet, basename='pesaje')

urlpatterns = [
    path(
        'pesajes-camiones/importar-xml-y-confirmar/',
        api_views.importar_xml_y_confirmar_view,
        name='importar_xml_y_confirmar',
    ),
] + router.urls
