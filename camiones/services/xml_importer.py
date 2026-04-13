from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
import xml.etree.ElementTree as ET

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from camiones.models import AtributoPesaje, DocumentoPesaje, Pesaje, Producto, ProductoDocumento


class XmlImportError(Exception):
    """Error base para importaciones de XML de pesaje."""


class InvalidXmlError(XmlImportError):
    """XML invalido o con estructura no soportada."""


class MissingPesNroError(XmlImportError):
    """El XML no contiene PesNro, llave principal del pesaje."""


def _local_name(tag: str) -> str:
    return tag.split('}', 1)[1] if '}' in tag else tag


def _namespace_prefix(tag: str) -> str:
    if '}' not in tag:
        return ''
    return tag.split('}', 1)[0] + '}'


def _text_or_empty(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _save_value(container: dict[str, Any], key: str, value: str) -> None:
    if key not in container:
        container[key] = value
        return
    if isinstance(container[key], list):
        container[key].append(value)
        return
    container[key] = [container[key], value]


def _simple_children_data(element: ET.Element) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for child in list(element):
        if len(list(child)) > 0:
            continue
        _save_value(data, _local_name(child.tag), _text_or_empty(child.text))
    return data


def _pick(data: dict[str, Any], *keys: str) -> str:
    lowered = {k.lower(): v for k, v in data.items()}
    for key in keys:
        if key.lower() in lowered:
            value = lowered[key.lower()]
            if isinstance(value, list):
                return _text_or_empty(value[0])
            return _text_or_empty(value)
    return ''


def _to_decimal(raw: str) -> Decimal | None:
    cleaned = _text_or_empty(raw).replace(',', '.')
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _to_datetime(raw: str):
    value = _text_or_empty(raw)
    if not value:
        return None

    dt = parse_datetime(value)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    d = parse_date(value)
    if d is not None:
        dt = timezone.datetime.combine(d, timezone.datetime.min.time())
        return timezone.make_aware(dt, timezone.get_current_timezone())

    return None


def _findall_path(parent: ET.Element, names: list[str], ns_prefix: str) -> list[ET.Element]:
    nodes = [parent]
    for name in names:
        next_nodes: list[ET.Element] = []
        for node in nodes:
            next_nodes.extend(node.findall(f'{ns_prefix}{name}'))
        nodes = next_nodes
    return nodes


def _make_aware_dt(value):
    """Convierte un datetime naive a aware (zona local de settings)."""
    if value is None:
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
        if value is None:
            return None
    if hasattr(value, 'tzinfo') and timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _build_pesaje_defaults(root_data: dict[str, Any], xml_string: str, origen: dict[str, Any] | None) -> dict[str, Any]:
    origen = origen or {}

    return {
        'xml_original': xml_string,
        'data_json': root_data,
        'id_origen_sql': origen.get('ID') or origen.get('id'),
        'fecha_origen_sql': _make_aware_dt(origen.get('Fecha') or origen.get('fecha')),
        'estado_origen_sql': _text_or_empty(origen.get('Estado') or origen.get('estado')),
        'bse_cod_origen_sql': _text_or_empty(origen.get('BseCod') or origen.get('bsecod')),
        'modo_origen_sql': _text_or_empty(origen.get('Modo') or origen.get('modo')),
        'vhc_tip_origen_sql': _text_or_empty(origen.get('VhcTip') or origen.get('vhctip')),
        'comentario_origen_sql': _text_or_empty(origen.get('Comentario') or origen.get('comentario')),
        'pes_est': _pick(root_data, 'PesEst'),
        'pes_fec_ing': _to_datetime(_pick(root_data, 'PesFecIng')),
        'vhc_pat': _pick(root_data, 'VhcPat'),
        'pes_tra_nom': _pick(root_data, 'PesTraNom'),
        'pes_com_cho_nom': _pick(root_data, 'PesComChoNom'),
        'pes_cic_pes_des': _pick(root_data, 'PesCicPesDes'),
        'pes_vhc_com_net': _to_decimal(_pick(root_data, 'PesVhcComNet')),
    }


def _get_or_create_producto(producto_data: dict[str, Any]) -> Producto | None:
    codigo = _pick(producto_data, 'PDcProCod', 'ProCod', 'Codigo', 'CodProducto')
    nombre = _pick(producto_data, 'PDcProNom', 'ProNom', 'Nombre', 'NomProducto')

    if not codigo:
        return None

    producto, created = Producto.objects.get_or_create(
        codigo=codigo,
        defaults={'nombre': nombre, 'data_json': producto_data},
    )

    updated_fields: list[str] = []
    if not created and nombre and producto.nombre != nombre:
        producto.nombre = nombre
        updated_fields.append('nombre')

    if not created and not producto.data_json:
        producto.data_json = producto_data
        updated_fields.append('data_json')

    if updated_fields:
        producto.save(update_fields=updated_fields + ['actualizado_en'])

    return producto


def import_pesaje_xml(xml_string: str, origen: dict[str, Any] | None = None) -> tuple[Pesaje, bool]:
    """Importa un XML de E-truck y lo persiste en estructura normalizada."""
    xml_limpio = _text_or_empty(xml_string)
    if not xml_limpio:
        raise XmlImportError('El XML viene vacio.')

    try:
        root = ET.fromstring(xml_limpio)
    except ET.ParseError as exc:
        raise InvalidXmlError(f'XML invalido: {exc}') from exc

    if _local_name(root.tag) != 'Pesaje':
        raise InvalidXmlError('El nodo raiz del XML no es <Pesaje>.')

    ns_prefix = _namespace_prefix(root.tag)
    root_data = _simple_children_data(root)
    pes_nro = _pick(root_data, 'PesNro')
    if not pes_nro:
        raise MissingPesNroError('No se encontro PesNro dentro del nodo raiz.')

    defaults = _build_pesaje_defaults(root_data, xml_limpio, origen)

    with transaction.atomic():
        pesaje, created = Pesaje.objects.get_or_create(pes_nro=pes_nro, defaults=defaults)
        if not created:
            for field_name, value in defaults.items():
                setattr(pesaje, field_name, value)
            pesaje.save()

        # Reimportacion segura: se reemplazan hijos para evitar duplicados.
        pesaje.documentos.all().delete()
        pesaje.atributos.all().delete()

        documento_nodes = _findall_path(root, ['Documentos', 'Documento'], ns_prefix)
        for doc_node in documento_nodes:
            doc_data = _simple_children_data(doc_node)
            documento = DocumentoPesaje.objects.create(
                pesaje=pesaje,
                pdc_id=_pick(doc_data, 'PDcID', 'PdcID'),
                pdc_doc_nro=_pick(doc_data, 'PDcDocNro', 'PdcDocNro', 'DocNro'),
                tipo_documento=_pick(doc_data, 'PDcTipDes', 'PDcTip', 'TipoDocumento'),
                fecha_documento=_to_datetime(_pick(doc_data, 'PDcFec', 'Fecha')),
                origen=_pick(doc_data, 'PDcOriNom', 'Origen'),
                destino=_pick(doc_data, 'PDcDesNom', 'Destino'),
                data_json=doc_data,
            )

            for prod_node in _findall_path(doc_node, ['Productos', 'Producto'], ns_prefix):
                producto_data = _simple_children_data(prod_node)
                producto = _get_or_create_producto(producto_data)

                ProductoDocumento.objects.create(
                    documento=documento,
                    producto=producto,
                    codigo_producto=_pick(producto_data, 'PDcProCod', 'ProCod', 'Codigo', 'CodProducto'),
                    nombre_producto=_pick(producto_data, 'PDcProNom', 'ProNom', 'Nombre', 'NomProducto'),
                    linea=_pick(producto_data, 'PDcLin', 'PDcProLin', 'Linea'),
                    cantidad=_to_decimal(_pick(producto_data, 'PDcProCan', 'Cantidad', 'Can')), 
                    peso=_to_decimal(_pick(producto_data, 'PDcProPes', 'Peso')), 
                    data_json=producto_data,
                )

        atributo_nodes = _findall_path(root, ['Atributos', 'Atributo'], ns_prefix)
        for atributo_node in atributo_nodes:
            atributo_data = _simple_children_data(atributo_node)
            AtributoPesaje.objects.create(
                pesaje=pesaje,
                pes_att_id=_pick(atributo_data, 'PesAttID', 'AttID', 'Codigo', 'Id'),
                pes_att_val=_pick(atributo_data, 'PesAttVal', 'AttVal', 'Valor'),
                data_json=atributo_data,
            )

    return pesaje, created
