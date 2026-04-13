"""
Servicio para procesar pesajes e-truck y generar operaciones de stock.

Reglas de negocio:
- Ciclo 1 (Recepción) → ENTRADA de stock
- Ciclo 2 (Despacho)  → SALIDA de stock
- Ciclo 8 (Transferencia entre bodegas) → SALIDA origen + ENTRADA destino
- Otros ciclos → Rechazados con error

Idempotencia: Si ya existe una operación con el mismo external_uid (pes_nro),
se devuelve la existente sin duplicar.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum

from camiones.models import (
    Bodega,
    Cliente,
    ClienteBodega,
    ClienteProducto,
    KardexLinea,
    Operacion,
    Pesaje,
    Producto,
)
from camiones.services.xml_importer import import_pesaje_xml, _pick, _to_decimal

# Mapeo ciclo → tipo de movimiento
CICLO_TIPO: dict[str, str] = {
    '1': Operacion.TipoMov.ENTRADA,
    'Recepción': Operacion.TipoMov.ENTRADA,
    '2': Operacion.TipoMov.SALIDA,
    'Despacho': Operacion.TipoMov.SALIDA,
    '8': 'TRANSFERENCIA',
    'Transferencia entre bodegas': 'TRANSFERENCIA',
}

# Ciclos válidos como set normalizado
CICLOS_VALIDOS = {'1', '2', '8'}


class StockServiceError(Exception):
    """Error base del servicio de stock."""


class CicloNoSoportado(StockServiceError):
    pass


class ClienteNoEncontrado(StockServiceError):
    pass


class BodegaNoEncontrada(StockServiceError):
    pass


class ProductoNoMapeado(StockServiceError):
    pass


def _normalizar_ciclo(ciclo_raw: str) -> str:
    """Normaliza el ciclo de pesaje a su número canónico."""
    limpio = ciclo_raw.strip()
    # Si el texto es el nombre, mapeamos al número
    mapa_texto = {
        'recepción': '1', 'recepcion': '1',
        'despacho': '2',
        'transferencia entre bodegas': '8', 'transferencia': '8',
    }
    return mapa_texto.get(limpio.lower(), limpio)


def _extraer_pesos(data: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    """Extrae bruto, tara y neto del data_json de un pesaje.

    Cadena de prioridad para neto:
    1. PesVhcComNet (neto del combo)
    2. PesVhcNet (neto del vehículo)
    3. bruto - tara
    """
    bruto = _to_decimal(_pick(data, 'PesVhcComBru', 'PesVhcBru')) or Decimal('0')
    tara = _to_decimal(_pick(data, 'PesVhcTar', 'PesVhcComTar')) or Decimal('0')

    neto = _to_decimal(_pick(data, 'PesVhcComNet'))
    if not neto:
        neto = _to_decimal(_pick(data, 'PesVhcNet'))
    if not neto:
        neto = bruto - tara

    return bruto, tara, neto


def _resolver_cliente(data_doc: dict[str, Any], ciclo: str) -> Cliente | None:
    """Resuelve el cliente a partir de los datos del documento.

    Para ENTRADA (ciclo 1): cliente = origen (quien envía)
    Para SALIDA  (ciclo 2): cliente = destino (quien retira)
    """
    if ciclo == '1':
        rut = _pick(data_doc, 'PDcOriRut', 'OriRut', 'RutOrigen')
    else:
        rut = _pick(data_doc, 'PDcDesRut', 'DesRut', 'RutDestino')

    if not rut:
        return None

    rut_limpio = rut.strip().upper()
    try:
        return Cliente.objects.get(rut=rut_limpio, activo=True)
    except Cliente.DoesNotExist:
        return None


def _resolver_bodega(cliente: Cliente | None, sucursal_codigo: str,
                     ciclo: str) -> Bodega:
    """Resuelve la bodega destino del movimiento.

    Prioridad:
    1. ClienteBodega con sucursal exacta
    2. ClienteBodega default del cliente (es_default=True)
    3. Bodega con código 'PRINCIPAL'
    """
    if cliente:
        # Intento 1: match por sucursal
        if sucursal_codigo:
            cb = ClienteBodega.objects.filter(
                cliente=cliente,
                sucursal__codigo=sucursal_codigo,
            ).select_related('bodega').first()
            if cb:
                return cb.bodega

        # Intento 2: default del cliente
        cb_default = ClienteBodega.objects.filter(
            cliente=cliente, es_default=True,
        ).select_related('bodega').first()
        if cb_default:
            return cb_default.bodega

    # Intento 3: bodega principal
    bodega = Bodega.objects.filter(codigo='PRINCIPAL', activo=True).first()
    if bodega:
        return bodega

    # Fallback: primera bodega activa
    bodega = Bodega.objects.filter(activo=True).first()
    if bodega:
        return bodega

    raise BodegaNoEncontrada('No se encontró bodega para asignar la operación.')


def _resolver_producto(codigo_etruck: str, cliente: Cliente | None) -> Producto:
    """Resuelve el producto de stock a partir del código E-truck.

    Prioridad:
    1. ClienteProducto del cliente
    2. Producto directo por código
    """
    if cliente:
        cp = ClienteProducto.objects.filter(
            cliente=cliente, codigo_etruck=codigo_etruck, activo=True,
        ).select_related('producto').first()
        if cp:
            return cp.producto

    try:
        return Producto.objects.get(codigo=codigo_etruck)
    except Producto.DoesNotExist:
        raise ProductoNoMapeado(
            f'Producto "{codigo_etruck}" no encontrado ni mapeado para el cliente.'
        )


def _stock_actual(producto: Producto, bodega: Bodega) -> Decimal:
    """Calcula el stock actual de un producto en una bodega sumando el kardex."""
    ultima = KardexLinea.objects.filter(
        producto=producto, bodega=bodega,
    ).order_by('-pk').first()
    if ultima:
        return ultima.stock_posterior
    return Decimal('0')


def _crear_lineas_kardex(
    operacion: Operacion,
    productos_data: list[dict[str, Any]],
    bodega: Bodega,
    cliente: Cliente | None,
    tipo: str,
    peso_neto_total: Decimal,
) -> list[KardexLinea]:
    """Crea las líneas de kardex para una operación."""
    lineas = []

    if not productos_data:
        # Sin productos detallados: crear una línea genérica si hay producto por defecto
        return lineas

    for prod_data in productos_data:
        codigo = _pick(prod_data, 'PDcProCod', 'ProCod', 'Codigo', 'CodProducto')
        if not codigo:
            continue

        producto = _resolver_producto(codigo, cliente)

        cantidad = _to_decimal(_pick(prod_data, 'PDcProCan', 'Cantidad', 'Can')) or Decimal('0')
        peso = _to_decimal(_pick(prod_data, 'PDcProPes', 'Peso')) or Decimal('0')

        stock_ant = _stock_actual(producto, bodega)

        if tipo == Operacion.TipoMov.ENTRADA:
            stock_post = stock_ant + cantidad
        else:
            stock_post = stock_ant - cantidad

        linea = KardexLinea.objects.create(
            operacion=operacion,
            producto=producto,
            bodega=bodega,
            cantidad=cantidad if tipo == Operacion.TipoMov.ENTRADA else -cantidad,
            peso=peso,
            stock_anterior=stock_ant,
            stock_posterior=stock_post,
        )
        lineas.append(linea)

    return lineas


def importar_xml_y_confirmar(
    xml_string: str,
    user=None,
    origen: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Punto de entrada principal: importa XML de pesaje y genera operación de stock.

    Returns:
        dict con keys: operacion, pesaje, created, lineas, warnings
    """
    # 1. Importar XML a modelos de pesaje
    pesaje, pesaje_created = import_pesaje_xml(xml_string, origen)

    # 2. Verificar idempotencia
    op_existente = Operacion.objects.filter(external_uid=pesaje.pes_nro).first()
    if op_existente:
        return {
            'operacion': op_existente,
            'pesaje': pesaje,
            'created': False,
            'lineas': list(op_existente.lineas.all()),
            'warnings': [],
            'duplicado': True,
        }

    # 3. Determinar ciclo
    ciclo_raw = pesaje.pes_cic_pes_des or _pick(pesaje.data_json, 'PesCicPesDes', 'CicloPesaje')
    ciclo = _normalizar_ciclo(ciclo_raw)

    if ciclo not in CICLOS_VALIDOS:
        raise CicloNoSoportado(
            f'Ciclo "{ciclo_raw}" (normalizado: "{ciclo}") no es soportado. '
            f'Solo se aceptan ciclos: 1 (Recepción), 2 (Despacho), 8 (Transferencia).'
        )

    # 4. Extraer datos
    data = pesaje.data_json
    bruto, tara, neto = _extraer_pesos(data)
    warnings: list[str] = []

    # 5. Obtener datos del primer documento
    doc = pesaje.documentos.first()
    doc_data = doc.data_json if doc else {}
    nro_guia = doc.pdc_doc_nro if doc else ''
    fecha_doc = doc.fecha_documento if doc else None

    # 6. Resolver cliente
    cliente = _resolver_cliente(doc_data, ciclo)
    if not cliente:
        rut_info = _pick(doc_data, 'PDcOriRut', 'PDcDesRut', 'OriRut', 'DesRut')
        warnings.append(f'Cliente no encontrado (RUT: {rut_info}). Operación sin cliente.')

    # 7. Resolver sucursal para bodega
    if ciclo == '1':
        sucursal_cod = _pick(doc_data, 'PDcDesCod', 'PDcDesSucCod', 'DestinoCod')
    else:
        sucursal_cod = _pick(doc_data, 'PDcOriCod', 'PDcOriSucCod', 'OrigenCod')

    # 8. Extraer productos del documento
    productos_data = []
    if doc:
        for pd in doc.productos_documento.all():
            productos_data.append(pd.data_json)

    with transaction.atomic():
        if ciclo == '8':
            # Transferencia: SALIDA de origen + ENTRADA a destino
            bodega_origen = _resolver_bodega(cliente, _pick(doc_data, 'PDcOriCod', 'PDcOriSucCod'), ciclo)
            bodega_destino = _resolver_bodega(cliente, _pick(doc_data, 'PDcDesCod', 'PDcDesSucCod'), ciclo)

            op_salida = Operacion.objects.create(
                pesaje=pesaje,
                external_uid=f"{pesaje.pes_nro}_SAL",
                tipo=Operacion.TipoMov.SALIDA,
                ciclo=ciclo,
                nro_guia=nro_guia,
                fecha_documento=fecha_doc,
                cliente=cliente,
                bodega=bodega_origen,
                patente=pesaje.vhc_pat,
                transportista=pesaje.pes_tra_nom,
                chofer=pesaje.pes_com_cho_nom,
                peso_bruto=bruto,
                peso_tara=tara,
                peso_neto=neto,
                creado_por=user,
            )
            lineas_sal = _crear_lineas_kardex(
                op_salida, productos_data, bodega_origen, cliente,
                Operacion.TipoMov.SALIDA, neto,
            )

            # La operación principal (para external_uid de idempotencia) es la entrada
            op_entrada = Operacion.objects.create(
                pesaje=pesaje,
                external_uid=pesaje.pes_nro,
                tipo=Operacion.TipoMov.ENTRADA,
                ciclo=ciclo,
                nro_guia=nro_guia,
                fecha_documento=fecha_doc,
                cliente=cliente,
                bodega=bodega_destino,
                patente=pesaje.vhc_pat,
                transportista=pesaje.pes_tra_nom,
                chofer=pesaje.pes_com_cho_nom,
                peso_bruto=bruto,
                peso_tara=tara,
                peso_neto=neto,
                creado_por=user,
            )
            lineas_ent = _crear_lineas_kardex(
                op_entrada, productos_data, bodega_destino, cliente,
                Operacion.TipoMov.ENTRADA, neto,
            )

            return {
                'operacion': op_entrada,
                'operacion_salida': op_salida,
                'pesaje': pesaje,
                'created': True,
                'lineas': lineas_ent + lineas_sal,
                'warnings': warnings,
                'duplicado': False,
            }

        else:
            # Ciclo 1 o 2: operación simple
            tipo = Operacion.TipoMov.ENTRADA if ciclo == '1' else Operacion.TipoMov.SALIDA
            bodega = _resolver_bodega(cliente, sucursal_cod, ciclo)

            operacion = Operacion.objects.create(
                pesaje=pesaje,
                external_uid=pesaje.pes_nro,
                tipo=tipo,
                ciclo=ciclo,
                nro_guia=nro_guia,
                fecha_documento=fecha_doc,
                cliente=cliente,
                bodega=bodega,
                patente=pesaje.vhc_pat,
                transportista=pesaje.pes_tra_nom,
                chofer=pesaje.pes_com_cho_nom,
                peso_bruto=bruto,
                peso_tara=tara,
                peso_neto=neto,
                creado_por=user,
            )

            lineas = _crear_lineas_kardex(
                operacion, productos_data, bodega, cliente, tipo, neto,
            )

            return {
                'operacion': operacion,
                'pesaje': pesaje,
                'created': True,
                'lineas': lineas,
                'warnings': warnings,
                'duplicado': False,
            }
