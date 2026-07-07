import pyodbc
from django.conf import settings

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

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


# ─── API Pesajes Codelco/Cristalerias (SELECT directo SQL Server, sin XML) ───

_PESAJES_BASE_SQL = """
WITH PesajesCodelco AS (
    SELECT
        ROW_NUMBER() OVER (
            PARTITION BY P.PesBseCod, P.PesNro
            ORDER BY D.PDcID ASC, DD.PDcLin ASC
        ) AS rn,

        CAST(P.PesNro AS varchar(80))                             AS pes_nro,
        RTRIM(P.PesEst)                                           AS pes_est,
        P.PesFecIng                                               AS pes_fec_ing,
        RTRIM(P.VhcPat)                                           AS vhc_pat,
        RTRIM(ISNULL(P.PesAcoPat, ''))                            AS pes_aco_pat,
        RTRIM(ISNULL(T.TraNom, ''))                               AS pes_tra_nom,
        RTRIM(ISNULL(ChCom.ChoNom, ''))                           AS pes_com_cho_nom,
        RTRIM(ISNULL(CP.CicPesDes, ''))                           AS pes_cic_pes_des,
        CAST(P.PesCicPesCod AS varchar(80))                       AS pes_cic_pes_cod,
        CAST(ISNULL(P.PesVhcComNet, 0)    AS decimal(18,3))       AS pes_vhc_com_net,
        CAST(ISNULL(P.PesVhcComNetCor, 0) AS decimal(18,0))       AS pes_vhc_com_net_cor,
        CAST(ISNULL(DD.PDcProNetInf, 0)   AS decimal(18,0))       AS pes_vhc_net_inf,
        P.PesComFec                                               AS pes_com_fec,
        RTRIM(ISNULL(P.PesComObs, ''))                            AS pes_com_obs,
        P.PesTarFec                                               AS pes_tar_fec,
        CAST(D.PDcDocNro AS varchar(80))                          AS pdc_doc_nro,
        RTRIM(ISNULL(CliDst.CliRazSoc, ''))                          AS pdc_dst_cli_nom,
        RTRIM(ISNULL(SucDst.CliSucNom, ''))                           AS pdc_dst_cli_suc_nom,
        RTRIM(ISNULL(CliOri.CliRazSoc, ''))                          AS pdc_ori_cli_nom,
        RTRIM(ISNULL(SucOri.CliSucNom, ''))                       AS pdc_ori_cli_suc_nom,
        RTRIM(ISNULL(DD.PDcProCod, ''))                           AS pdc_pro_cod,
        RTRIM(ISNULL(PR.ProNom, ''))                              AS pdc_pro_nom,
        CAST(ISNULL(DD.PDcProNetInf, 0)   AS decimal(18,0))       AS pdc_pro_net_inf,
        ISNULL(Attr.attr_destino, '')                             AS attr_destino,
        ISNULL(Attr.attr_origen,  '')                             AS attr_origen,
        ISNULL(Attr.attr_sello,   '')                             AS attr_sello,
        ISNULL(Attr.attr_lote,    '')                             AS attr_lote,
        ISNULL(Attr.attr_turno,   '')                             AS attr_turno,
        'R'       AS estado_origen_sql,
        GETDATE() AS fecha_origen_sql

    FROM dbo.Pesaje P

    LEFT JOIN dbo.PesajeDocumento D
        ON D.PesBseCod = P.PesBseCod AND D.PesNro = P.PesNro

    LEFT JOIN dbo.PesajeDocumentoDetalle DD
        ON DD.PesBseCod = D.PesBseCod AND DD.PesNro = D.PesNro AND DD.PDcID = D.PDcID

    LEFT JOIN dbo.Producto PR
        ON PR.ProCod = DD.PDcProCod

    LEFT JOIN dbo.Cliente CliOri ON CliOri.CliID = D.PDcOriCliID
    LEFT JOIN dbo.ClienteSucursal SucOri
        ON SucOri.CliID = D.PDcOriCliID AND SucOri.CliSucCod = D.PDcOriCliSucCod

    LEFT JOIN dbo.Cliente CliDst ON CliDst.CliID = D.PDcDstCliID
    LEFT JOIN dbo.ClienteSucursal SucDst
        ON SucDst.CliID = D.PDcDstCliID AND SucDst.CliSucCod = D.PDcDstCliSucCod

    LEFT JOIN dbo.Transportista T   ON T.TraID   = P.PesTraID
    LEFT JOIN dbo.Chofer ChCom      ON ChCom.ChoID = P.PesComChoID
    LEFT JOIN dbo.CicloPesaje CP    ON CP.CicPesCod = P.PesCicPesCod

    OUTER APPLY (
        SELECT
            MAX(CASE WHEN LTRIM(RTRIM(A.PesAttID)) = 'DESTINO'
                THEN NULLIF(LTRIM(RTRIM(A.PesAttVal)), '') END) AS attr_destino,
            MAX(CASE WHEN LTRIM(RTRIM(A.PesAttID)) = 'ORIGEN'
                THEN NULLIF(LTRIM(RTRIM(A.PesAttVal)), '') END) AS attr_origen,
            MAX(CASE WHEN LTRIM(RTRIM(A.PesAttID)) = 'SELLO'
                THEN NULLIF(LTRIM(RTRIM(A.PesAttVal)), '') END) AS attr_sello,
            MAX(CASE WHEN LTRIM(RTRIM(A.PesAttID)) = 'LOTE'
                THEN NULLIF(LTRIM(RTRIM(A.PesAttVal)), '') END) AS attr_lote,
            MAX(CASE WHEN LTRIM(RTRIM(A.PesAttID)) = 'TURNO'
                THEN NULLIF(LTRIM(RTRIM(A.PesAttVal)), '') END) AS attr_turno
        FROM dbo.PesajeAtributo A
        WHERE A.PesBseCod = P.PesBseCod AND A.PesNro = P.PesNro
    ) Attr

        WHERE P.PesEst = 'T'
            AND (CliOri.CliDId = {cliente_did} OR CliDst.CliDId = {cliente_did})
)
SELECT *
FROM PesajesCodelco
WHERE rn = 1
  {where_extra}
ORDER BY pes_fec_ing DESC, pes_nro DESC
"""

_PESAJES_CODELCO_SQL = _PESAJES_BASE_SQL.format(cliente_did=61704000, where_extra="{where_extra}")
_PESAJES_CRISTALERIAS_SQL = _PESAJES_BASE_SQL.format(cliente_did=90331000, where_extra="{where_extra}")
_PESAJES_PORTLAND_SQL = _PESAJES_BASE_SQL.format(cliente_did=87690900, where_extra="{where_extra}")

_CODELCO_FIELDS = [
    'pes_nro', 'pes_est', 'pes_fec_ing', 'vhc_pat', 'pes_aco_pat',
    'pes_tra_nom', 'pes_com_cho_nom', 'pes_cic_pes_des', 'pes_cic_pes_cod',
    'pes_vhc_com_net', 'pes_vhc_com_net_cor', 'pes_vhc_net_inf',
    'pes_com_fec', 'pes_com_obs', 'pes_tar_fec', 'pdc_doc_nro',
    'pdc_dst_cli_nom', 'pdc_dst_cli_suc_nom', 'pdc_ori_cli_nom', 'pdc_ori_cli_suc_nom',
    'pdc_pro_cod', 'pdc_pro_nom',
    'pdc_pro_net_inf', 'attr_destino', 'attr_origen', 'attr_sello',
    'attr_lote', 'attr_turno', 'estado_origen_sql', 'fecha_origen_sql',
]


def _codelco_conn():
    conn_str = (
        f"DRIVER={{{getattr(settings, 'ETRUCK_CODELCO_SQL_DRIVER', 'ODBC Driver 17 for SQL Server')}}};"
        f"SERVER={settings.ETRUCK_CODELCO_SQL_SERVER};"
        f"DATABASE={settings.ETRUCK_CODELCO_SQL_DATABASE};"
        f"UID={settings.ETRUCK_CODELCO_SQL_USER};"
        f"PWD={settings.ETRUCK_CODELCO_SQL_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=30)


class CodelcoPagination(PageNumberPagination):
    page_size = 500
    page_size_query_param = 'page_size'
    max_page_size = 2000


class PesajesCodelcoAPIView(APIView):
    """
    GET /api/pesajes-codelco/

    Lee pesajes finalizados de Codelco directamente desde SQL Server.
    No usa XML. No modifica datos locales.

    Filtros opcionales:
      - pes_nro       : número de pesaje (búsqueda exacta)
      - patente       : patente del vehículo (búsqueda exacta, mayúsculas)
      - guia          : número de guía / pdc_doc_nro (exacto)
      - fecha_desde   : ISO date YYYY-MM-DD (inclusive)
      - fecha_hasta   : ISO date YYYY-MM-DD (inclusive)
    """
    permission_classes = [EsOperadorStock]
    sql_template = _PESAJES_CODELCO_SQL

    def get(self, request):
        conditions = []
        params = []

        pes_nro = request.query_params.get('pes_nro', '').strip()
        if pes_nro:
            conditions.append("pes_nro = ?")
            params.append(pes_nro)

        patente = request.query_params.get('patente', '').strip().upper()
        if patente:
            conditions.append("vhc_pat = ?")
            params.append(patente)

        guia = request.query_params.get('guia', '').strip()
        if guia:
            conditions.append("pdc_doc_nro = ?")
            params.append(guia)

        fecha_desde = request.query_params.get('fecha_desde', '').strip()
        if fecha_desde:
            conditions.append("pes_fec_ing >= CAST(? AS date)")
            params.append(fecha_desde)

        fecha_hasta = request.query_params.get('fecha_hasta', '').strip()
        if fecha_hasta:
            conditions.append("pes_fec_ing < DATEADD(day, 1, CAST(? AS date))")
            params.append(fecha_hasta)

        where_extra = ("AND " + " AND ".join(conditions)) if conditions else ""
        sql = self.sql_template.format(where_extra=where_extra)

        try:
            with _codelco_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        except Exception as exc:
            return Response(
                {'error': 'Error al consultar SQL Server', 'detalle': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Serializar filas a dicts (rn ya filtrado en el WHERE, no se expone)
        data = []
        for row in rows:
            item = {}
            for i, field in enumerate(_CODELCO_FIELDS):
                val = row[i + 1]  # +1 porque columna 0 es rn (no expuesta)
                if hasattr(val, 'isoformat'):
                    val = val.isoformat()
                elif hasattr(val, '__float__'):
                    val = str(val)
                item[field] = val
            data.append(item)

        paginator = CodelcoPagination()
        page = paginator.paginate_queryset(data, request, view=self)
        return paginator.get_paginated_response(page)


class PesajeCodelcoDetailAPIView(APIView):
    """
    GET /api/pesajes-codelco/<pes_nro>/

    Retorna el detalle de un pesaje Codelco por su número de pesaje.
    Responde 404 si no existe.
    """
    permission_classes = [EsOperadorStock]
    sql_template = _PESAJES_CODELCO_SQL

    def get(self, request, pes_nro):
        sql = self.sql_template.format(where_extra="AND pes_nro = ?")
        try:
            with _codelco_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, [str(pes_nro)])
                row = cursor.fetchone()
        except Exception as exc:
            return Response(
                {'error': 'Error al consultar SQL Server', 'detalle': str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if row is None:
            return Response(
                {'error': f'Pesaje {pes_nro} no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        item = {}
        for i, field in enumerate(_CODELCO_FIELDS):
            val = row[i + 1]  # +1 porque columna 0 es rn (no expuesta)
            if hasattr(val, 'isoformat'):
                val = val.isoformat()
            elif hasattr(val, '__float__'):
                val = str(val)
            item[field] = val

        return Response(item)


class PesajesCristaleriasAPIView(PesajesCodelcoAPIView):
    """
    GET /api/pesajes-cristalerias/

    Misma logica de Codelco, filtrando por cliente RUT 90331000
    (CRISTALERIAS DE CHILE S.A.).
    """
    sql_template = _PESAJES_CRISTALERIAS_SQL


class PesajeCristaleriasDetailAPIView(PesajeCodelcoDetailAPIView):
    """
    GET /api/pesajes-cristalerias/<pes_nro>/

    Detalle de pesaje para cliente RUT 90331000
    (CRISTALERIAS DE CHILE S.A.).
    """
    sql_template = _PESAJES_CRISTALERIAS_SQL


class PesajesPortlandAPIView(PesajesCodelcoAPIView):
    """
    GET /api/pesajes-portland/

    Misma logica de Codelco, filtrando por cliente RUT 87690900
    (DISTRIBUIDORA PORTLAND S.A.).
    """
    sql_template = _PESAJES_PORTLAND_SQL


class PesajePortlandDetailAPIView(PesajeCodelcoDetailAPIView):
    """
    GET /api/pesajes-portland/<pes_nro>/

    Detalle de pesaje para cliente RUT 87690900
    (DISTRIBUIDORA PORTLAND S.A.).
    """
    sql_template = _PESAJES_PORTLAND_SQL

