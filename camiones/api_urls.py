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
    path(
        'pesajes-codelco/',
        api_views.PesajesCodelcoAPIView.as_view(),
        name='pesajes-codelco',
    ),
    path(
        'pesajes-codelco/<str:pes_nro>/',
        api_views.PesajeCodelcoDetailAPIView.as_view(),
        name='pesajes-codelco-detail',
    ),
] + router.urls
