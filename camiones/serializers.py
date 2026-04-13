from rest_framework import serializers

from camiones.models import (
    AtributoPesaje, Bodega, Cliente, ClienteBodega, ClienteProducto,
    ClienteSucursal, DocumentoPesaje, KardexLinea, Operacion, Pesaje,
    Producto, ProductoDocumento,
)


class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ['codigo', 'nombre']


class BodegaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bodega
        fields = ['id', 'codigo', 'nombre']


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['id', 'rut', 'razon_social', 'activo']


class ClienteSucursalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteSucursal
        fields = ['id', 'cliente', 'codigo', 'nombre', 'activo']


class ClienteBodegaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteBodega
        fields = ['id', 'cliente', 'sucursal', 'bodega', 'es_default']


class ClienteProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClienteProducto
        fields = ['id', 'cliente', 'codigo_etruck', 'producto', 'activo']


class KardexLineaSerializer(serializers.ModelSerializer):
    producto_codigo = serializers.CharField(source='producto.codigo', read_only=True)
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    bodega_codigo = serializers.CharField(source='bodega.codigo', read_only=True)

    class Meta:
        model = KardexLinea
        fields = [
            'id', 'producto', 'producto_codigo', 'producto_nombre',
            'bodega', 'bodega_codigo',
            'cantidad', 'peso', 'stock_anterior', 'stock_posterior',
            'creado_en',
        ]


class OperacionSerializer(serializers.ModelSerializer):
    lineas = KardexLineaSerializer(many=True, read_only=True)
    cliente_rut = serializers.CharField(source='cliente.rut', read_only=True, default='')
    bodega_codigo = serializers.CharField(source='bodega.codigo', read_only=True)

    class Meta:
        model = Operacion
        fields = [
            'id', 'pesaje', 'external_uid', 'tipo', 'estado',
            'ciclo', 'nro_guia', 'fecha_documento',
            'cliente', 'cliente_rut', 'bodega', 'bodega_codigo',
            'patente', 'transportista', 'chofer',
            'peso_bruto', 'peso_tara', 'peso_neto',
            'observaciones', 'lineas',
            'creado_en', 'actualizado_en', 'creado_por',
        ]


# ─── Helpers para extraer campos de data_json ───

def _dj(data, *keys):
    """Busca un valor en un dict data_json ignorando mayúsculas."""
    if not data:
        return ''
    lowered = {k.lower(): v for k, v in data.items()}
    for key in keys:
        val = lowered.get(key.lower())
        if val is not None:
            return str(val).strip() if not isinstance(val, list) else str(val[0]).strip()
    return ''


# ─── Serializers de Pesaje (datos E-truck como JSON) ───

class ProductoDocumentoSerializer(serializers.ModelSerializer):
    pdc_pro_net_inf = serializers.SerializerMethodField()

    class Meta:
        model = ProductoDocumento
        fields = [
            'id', 'codigo_producto', 'nombre_producto', 'linea',
            'cantidad', 'peso', 'pdc_pro_net_inf', 'data_json',
        ]

    def get_pdc_pro_net_inf(self, obj):
        return _dj(obj.data_json, 'PDcProNetInf')


class DocumentoPesajeSerializer(serializers.ModelSerializer):
    productos_documento = ProductoDocumentoSerializer(many=True, read_only=True)
    pdc_dst_cli_suc_nom = serializers.SerializerMethodField()
    pdc_ori_cli_suc_nom = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoPesaje
        fields = [
            'id', 'pdc_id', 'pdc_doc_nro', 'tipo_documento',
            'fecha_documento', 'origen', 'destino',
            'pdc_dst_cli_suc_nom', 'pdc_ori_cli_suc_nom',
            'data_json', 'productos_documento',
        ]

    def get_pdc_dst_cli_suc_nom(self, obj):
        return _dj(obj.data_json, 'PDcDstCliSucNom')

    def get_pdc_ori_cli_suc_nom(self, obj):
        return _dj(obj.data_json, 'PDcOriCliSucNom')


class AtributoPesajeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AtributoPesaje
        fields = ['id', 'pes_att_id', 'pes_att_val']


class PesajeListSerializer(serializers.ModelSerializer):
    """Versión ligera para listados."""
    pes_cic_pes_cod = serializers.SerializerMethodField()
    pes_aco_pat = serializers.SerializerMethodField()
    pes_vhc_com_net_cor = serializers.SerializerMethodField()
    pes_vhc_net_inf = serializers.SerializerMethodField()
    pes_com_fec = serializers.SerializerMethodField()
    pes_com_obs = serializers.SerializerMethodField()
    pes_tar_fec = serializers.SerializerMethodField()

    # Campos aplanados del primer documento
    pdc_doc_nro = serializers.SerializerMethodField()
    pdc_dst_cli_suc_nom = serializers.SerializerMethodField()
    pdc_ori_cli_suc_nom = serializers.SerializerMethodField()

    # Campos aplanados del primer producto del documento
    pdc_pro_cod = serializers.SerializerMethodField()
    pdc_pro_nom = serializers.SerializerMethodField()
    pdc_pro_net_inf = serializers.SerializerMethodField()

    # Atributos clave aplanados
    attr_destino = serializers.SerializerMethodField()
    attr_origen = serializers.SerializerMethodField()
    attr_sello = serializers.SerializerMethodField()
    attr_lote = serializers.SerializerMethodField()
    attr_turno = serializers.SerializerMethodField()

    class Meta:
        model = Pesaje
        fields = [
            'id', 'pes_nro', 'pes_est', 'pes_fec_ing', 'vhc_pat',
            'pes_aco_pat', 'pes_tra_nom', 'pes_com_cho_nom',
            'pes_cic_pes_des', 'pes_cic_pes_cod',
            'pes_vhc_com_net', 'pes_vhc_com_net_cor', 'pes_vhc_net_inf',
            'pes_com_fec', 'pes_com_obs', 'pes_tar_fec',
            # Documento
            'pdc_doc_nro', 'pdc_dst_cli_suc_nom', 'pdc_ori_cli_suc_nom',
            # Producto
            'pdc_pro_cod', 'pdc_pro_nom', 'pdc_pro_net_inf',
            # Atributos
            'attr_destino', 'attr_origen', 'attr_sello', 'attr_lote', 'attr_turno',
            # Meta
            'estado_origen_sql', 'fecha_origen_sql',
            'creado_en',
        ]

    def _first_doc(self, obj):
        if not hasattr(obj, '_cached_first_doc'):
            docs = getattr(obj, '_prefetched_objects_cache', {}).get('documentos')
            if docs is not None:
                obj._cached_first_doc = docs[0] if docs else None
            else:
                obj._cached_first_doc = obj.documentos.first()
        return obj._cached_first_doc

    def _attr_val(self, obj, att_id):
        attrs = getattr(obj, '_prefetched_objects_cache', {}).get('atributos')
        if attrs is not None:
            for a in attrs:
                if a.pes_att_id.upper() == att_id:
                    return a.pes_att_val
            return ''
        a = obj.atributos.filter(pes_att_id__iexact=att_id).first()
        return a.pes_att_val if a else ''

    def get_pes_cic_pes_cod(self, obj):
        return _dj(obj.data_json, 'PesCicPesCod')

    def get_pes_aco_pat(self, obj):
        return _dj(obj.data_json, 'PesAcoPat')

    def get_pes_vhc_com_net_cor(self, obj):
        return _dj(obj.data_json, 'PesVhcComNetCor')

    def get_pes_vhc_net_inf(self, obj):
        return _dj(obj.data_json, 'PesVhcNetInf')

    def get_pes_com_fec(self, obj):
        return _dj(obj.data_json, 'PesComFec')

    def get_pes_com_obs(self, obj):
        return _dj(obj.data_json, 'PesComObs')

    def get_pes_tar_fec(self, obj):
        return _dj(obj.data_json, 'PesTarFec')

    # Documento
    def get_pdc_doc_nro(self, obj):
        doc = self._first_doc(obj)
        return doc.pdc_doc_nro if doc else ''

    def get_pdc_dst_cli_suc_nom(self, obj):
        doc = self._first_doc(obj)
        return _dj(doc.data_json, 'PDcDstCliSucNom') if doc else ''

    def get_pdc_ori_cli_suc_nom(self, obj):
        doc = self._first_doc(obj)
        return _dj(doc.data_json, 'PDcOriCliSucNom') if doc else ''

    # Producto
    def get_pdc_pro_cod(self, obj):
        doc = self._first_doc(obj)
        if doc:
            prod = doc.productos_documento.first()
            return prod.codigo_producto if prod else ''
        return ''

    def get_pdc_pro_nom(self, obj):
        doc = self._first_doc(obj)
        if doc:
            prod = doc.productos_documento.first()
            return prod.nombre_producto if prod else ''
        return ''

    def get_pdc_pro_net_inf(self, obj):
        doc = self._first_doc(obj)
        if doc:
            prod = doc.productos_documento.first()
            return _dj(prod.data_json, 'PDcProNetInf') if prod else ''
        return ''

    # Atributos
    def get_attr_destino(self, obj):
        return self._attr_val(obj, 'DESTINO')

    def get_attr_origen(self, obj):
        return self._attr_val(obj, 'ORIGEN')

    def get_attr_sello(self, obj):
        return self._attr_val(obj, 'SELLO')

    def get_attr_lote(self, obj):
        return self._attr_val(obj, 'LOTE')

    def get_attr_turno(self, obj):
        return self._attr_val(obj, 'TURNO')


class PesajeDetailSerializer(serializers.ModelSerializer):
    """Versión completa con documentos, productos y atributos anidados."""
    documentos = DocumentoPesajeSerializer(many=True, read_only=True)
    atributos = AtributoPesajeSerializer(many=True, read_only=True)

    # Campos extraídos de data_json
    pes_cic_pes_cod = serializers.SerializerMethodField()
    pes_aco_pat = serializers.SerializerMethodField()
    pes_vhc_com_net_cor = serializers.SerializerMethodField()
    pes_vhc_net_inf = serializers.SerializerMethodField()
    pes_com_fec = serializers.SerializerMethodField()
    pes_com_obs = serializers.SerializerMethodField()
    pes_tar_fec = serializers.SerializerMethodField()

    class Meta:
        model = Pesaje
        fields = [
            'id', 'pes_nro', 'pes_est', 'pes_fec_ing', 'vhc_pat',
            'pes_aco_pat', 'pes_tra_nom', 'pes_com_cho_nom',
            'pes_cic_pes_des', 'pes_cic_pes_cod',
            'pes_vhc_com_net', 'pes_vhc_com_net_cor', 'pes_vhc_net_inf',
            'pes_com_fec', 'pes_com_obs', 'pes_tar_fec',
            'fecha_origen_sql', 'id_origen_sql', 'estado_origen_sql',
            'bse_cod_origen_sql', 'modo_origen_sql',
            'data_json',
            'documentos', 'atributos',
            'creado_en', 'actualizado_en',
        ]

    def get_pes_cic_pes_cod(self, obj):
        return _dj(obj.data_json, 'PesCicPesCod')

    def get_pes_aco_pat(self, obj):
        return _dj(obj.data_json, 'PesAcoPat')

    def get_pes_vhc_com_net_cor(self, obj):
        return _dj(obj.data_json, 'PesVhcComNetCor')

    def get_pes_vhc_net_inf(self, obj):
        return _dj(obj.data_json, 'PesVhcNetInf')

    def get_pes_com_fec(self, obj):
        return _dj(obj.data_json, 'PesComFec')

    def get_pes_com_obs(self, obj):
        return _dj(obj.data_json, 'PesComObs')

    def get_pes_tar_fec(self, obj):
        return _dj(obj.data_json, 'PesTarFec')


class ImportarXmlSerializer(serializers.Serializer):
    """Serializer para el endpoint POST de importar XML y confirmar."""
    xml = serializers.CharField(help_text='XML completo de pesaje E-truck')
