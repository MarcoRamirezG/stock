from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from camiones.models import (
    Bodega, Cliente, ClienteBodega, ClienteProducto, ClienteSucursal,
    KardexLinea, Operacion, Pesaje,
)
from camiones.permissions import EsOperadorStock
from camiones.serializers import (
    BodegaSerializer, ClienteBodegaSerializer, ClienteProductoSerializer,
    ClienteSerializer, ClienteSucursalSerializer, ImportarXmlSerializer,
    KardexLineaSerializer, OperacionSerializer,
    PesajeDetailSerializer, PesajeListSerializer,
)
from camiones.services.stock_service import (
    StockServiceError,
    importar_xml_y_confirmar,
)


@api_view(['POST'])
@permission_classes([EsOperadorStock])
def importar_xml_y_confirmar_view(request):
    """
    POST /api/pesajes-camiones/importar-xml-y-confirmar/

    Recibe un XML de pesaje E-truck, lo importa, y genera la operación de stock.

    Responses:
    - 201: Operación creada exitosamente
    - 200: Operación ya existía (idempotente)
    - 400: Error de validación o regla de negocio
    """
    serializer = ImportarXmlSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    xml_string = serializer.validated_data['xml']

    try:
        resultado = importar_xml_y_confirmar(
            xml_string=xml_string,
            user=request.user if request.user.is_authenticated else None,
        )
    except StockServiceError as exc:
        return Response(
            {'error': str(exc), 'tipo': type(exc).__name__},
            status=status.HTTP_400_BAD_REQUEST,
        )

    op_data = OperacionSerializer(resultado['operacion']).data

    response_data = {
        'operacion': op_data,
        'pes_nro': resultado['pesaje'].pes_nro,
        'warnings': resultado.get('warnings', []),
    }

    if resultado.get('operacion_salida'):
        response_data['operacion_salida'] = OperacionSerializer(
            resultado['operacion_salida']
        ).data

    if resultado.get('duplicado'):
        return Response(response_data, status=status.HTTP_200_OK)

    return Response(response_data, status=status.HTTP_201_CREATED)


# ─── ViewSets CRUD para catálogos ───

class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsOperadorStock]


class ClienteSucursalViewSet(viewsets.ModelViewSet):
    queryset = ClienteSucursal.objects.select_related('cliente').all()
    serializer_class = ClienteSucursalSerializer
    permission_classes = [EsOperadorStock]


class BodegaViewSet(viewsets.ModelViewSet):
    queryset = Bodega.objects.all()
    serializer_class = BodegaSerializer
    permission_classes = [EsOperadorStock]


class ClienteBodegaViewSet(viewsets.ModelViewSet):
    queryset = ClienteBodega.objects.select_related('cliente', 'sucursal', 'bodega').all()
    serializer_class = ClienteBodegaSerializer
    permission_classes = [EsOperadorStock]


class ClienteProductoViewSet(viewsets.ModelViewSet):
    queryset = ClienteProducto.objects.select_related('cliente', 'producto').all()
    serializer_class = ClienteProductoSerializer
    permission_classes = [EsOperadorStock]


class OperacionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Operacion.objects.select_related(
        'pesaje', 'cliente', 'bodega', 'creado_por',
    ).prefetch_related('lineas__producto', 'lineas__bodega').all()
    serializer_class = OperacionSerializer
    permission_classes = [EsOperadorStock]


class KardexLineaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = KardexLinea.objects.select_related(
        'operacion', 'producto', 'bodega',
    ).all()
    serializer_class = KardexLineaSerializer
    permission_classes = [EsOperadorStock]
    filterset_fields = ['producto', 'bodega']


class PesajePagination(PageNumberPagination):
    page_size = 500
    max_page_size = 500


class PesajeViewSet(viewsets.ReadOnlyModelViewSet):
    """Pesajes importados desde E-truck, expuestos como JSON.

    GET /api/pesajes/              Lista (campos ligeros)
    GET /api/pesajes/{pes_nro}/    Detalle completo con documentos, productos y atributos
    GET /api/pesajes/?ciclo=Recepción&pes_nro=XXX&patente=ABCD12
    """
    permission_classes = [EsOperadorStock]
    lookup_field = 'pes_nro'
    pagination_class = PesajePagination

    def get_queryset(self):
        qs = Pesaje.objects.all().order_by('-creado_en')

        # Filtros opcionales por query params
        pes_nro = self.request.query_params.get('pes_nro')
        if pes_nro:
            qs = qs.filter(pes_nro__icontains=pes_nro)

        ciclo = self.request.query_params.get('ciclo')
        if ciclo:
            qs = qs.filter(pes_cic_pes_des__icontains=ciclo)

        patente = self.request.query_params.get('patente')
        if patente:
            qs = qs.filter(vhc_pat__icontains=patente)

        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(pes_est__icontains=estado)

        qs = qs.prefetch_related(
            'documentos__productos_documento', 'atributos',
        )
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PesajeDetailSerializer
        return PesajeListSerializer
