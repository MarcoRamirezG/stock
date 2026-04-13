from datetime import datetime, time

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from camiones.models import DocumentoPesaje, Pesaje


def _aware_day_bounds(raw_date: str, end_of_day: bool = False):
	parsed = parse_date(raw_date or '')
	if parsed is None:
		return None
	selected_time = time.max if end_of_day else time.min
	dt = datetime.combine(parsed, selected_time)
	return timezone.make_aware(dt, timezone.get_current_timezone())


def _group_document_data(data: dict):
	guia_keys = {
		'PDcID',
		'PDcDocNro',
		'PDcDocFec',
		'PDcTDcCod',
		'PDcTDcDes',
		'PDcEst',
		'PDcFecIng',
		'PDcFecMod',
		'PDcUsuMod',
		'PDcObs',
		'PDcSubTot',
		'PDcIVA',
		'PDcTotEnvTar',
		'PDcTotNetInf',
		'PDcCopNet',
		'PDcUltDet',
		'MonCod',
		'MonNom',
	}

	guia = []
	origen_recepcion = []
	destino_despacho = []
	campos_digitables = []
	otros = []

	for key, value in (data or {}).items():
		if key == 'CamposDigitables':
			campos_digitables.append((key, value))
			continue

		if key in guia_keys:
			guia.append((key, value))
		elif key.startswith('PDcOri'):
			origen_recepcion.append((key, value))
		elif key.startswith('PDcDst'):
			destino_despacho.append((key, value))
		else:
			otros.append((key, value))

	return {
		'guia': guia,
		'origen_recepcion': origen_recepcion,
		'destino_despacho': destino_despacho,
		'campos_digitables': campos_digitables,
		'otros': otros,
	}


def _extract_product_fields(data_json: dict) -> dict:
	"""Extrae campos importantes del data_json de un producto."""
	return {
		'PDcCnt': data_json.get('PDcCnt', ''),
		'PDcEnvCnt': data_json.get('PDcEnvCnt', ''),
		'PDcEnvNom': data_json.get('PDcEnvNom', ''),
		'PDcEnvPes': data_json.get('PDcEnvPes', ''),
		'PDcProNetInf': data_json.get('PDcProNetInf', ''),
		'PDcPrePro': data_json.get('PDcPrePro', ''),
		'PDcPreUni': data_json.get('PDcPreUni', ''),
		'PDcProForCalImp': data_json.get('PDcProForCalImp', ''),
		'PDcTarEnv': data_json.get('PDcTarEnv', ''),
	}


def pesaje_list(request):
	queryset = Pesaje.objects.all().order_by('-actualizado_en')

	pes_nro = (request.GET.get('pes_nro') or '').strip()
	id_origen_sql = (request.GET.get('id_origen_sql') or '').strip()
	estado_origen_sql = (request.GET.get('estado_origen_sql') or '').strip()
	ciclo = (request.GET.get('ciclo') or '').strip()
	fecha_desde = (request.GET.get('fecha_desde') or '').strip()
	fecha_hasta = (request.GET.get('fecha_hasta') or '').strip()

	if pes_nro:
		queryset = queryset.filter(pes_nro__icontains=pes_nro)

	if id_origen_sql:
		queryset = queryset.filter(id_origen_sql=id_origen_sql)

	if estado_origen_sql:
		queryset = queryset.filter(estado_origen_sql__icontains=estado_origen_sql)

	if ciclo:
		queryset = queryset.filter(pes_cic_pes_des__icontains=ciclo)

	desde_dt = _aware_day_bounds(fecha_desde)
	if desde_dt is not None:
		queryset = queryset.filter(fecha_origen_sql__gte=desde_dt)

	hasta_dt = _aware_day_bounds(fecha_hasta, end_of_day=True)
	if hasta_dt is not None:
		queryset = queryset.filter(fecha_origen_sql__lte=hasta_dt)

	# Ciclos disponibles para el dropdown
	ciclos_disponibles = (
		Pesaje.objects.exclude(pes_cic_pes_des='')
		.values_list('pes_cic_pes_des', flat=True)
		.distinct()
		.order_by('pes_cic_pes_des')
	)

	hay_filtros = any([pes_nro, id_origen_sql, estado_origen_sql, ciclo, fecha_desde, fecha_hasta])
	if hay_filtros:
		pesajes = list(queryset.prefetch_related('documentos'))
	else:
		pesajes = list(queryset.prefetch_related('documentos')[:200])

	# Enriquecer con datos de guía
	pesajes_data = []
	for p in pesajes:
		dj = p.data_json or {}
		first_doc = p.documentos.first()
		ddj = (first_doc.data_json or {}) if first_doc else {}
		pesajes_data.append({
			'obj': p,
			'nro_guia': ddj.get('PDcDocNro', '-'),
			'origen': ddj.get('PDcOriCliRazSoc', '-'),
			'destino': ddj.get('PDcDstCliRazSoc', '-'),
			'bruto': dj.get('PesVhcComBru') or dj.get('PesTotComBru') or '-',
			'tara': dj.get('PesVhcTar') or dj.get('PesTotTar') or '-',
			'neto': dj.get('PesVhcComNet') or '-',
			'ciclo': p.pes_cic_pes_des,
		})

	context = {
		'pesajes_data': pesajes_data,
		'total': len(pesajes_data),
		'ciclos_disponibles': ciclos_disponibles,
		'filtros': {
			'pes_nro': pes_nro,
			'id_origen_sql': id_origen_sql,
			'estado_origen_sql': estado_origen_sql,
			'ciclo': ciclo,
			'fecha_desde': fecha_desde,
			'fecha_hasta': fecha_hasta,
		},
	}
	return render(request, 'camiones/pesaje_list.html', context)


def pesaje_detail(request, pesaje_id: int):
	pesaje = get_object_or_404(
		Pesaje.objects.prefetch_related(
			Prefetch(
				'documentos',
				queryset=DocumentoPesaje.objects.prefetch_related('productos_documento__producto').order_by('id'),
			),
			'atributos',
		),
		id=pesaje_id,
	)

	dj = pesaje.data_json or {}

	# --- Construir datos limpios para guía de despacho ---
	def _v(val):
		"""Retorna el valor o '-' si está vacío."""
		if val is None:
			return '-'
		s = str(val).strip()
		return s if s else '-'

	def _rut(did, dv):
		"""Formatea RUT chileno."""
		did_str = _v(did)
		dv_str = _v(dv)
		if did_str == '-':
			return '-'
		return f"{did_str}-{dv_str}"

	# Datos de documento y origen/destino
	guia_docs = []
	productos_guia = []
	for documento in pesaje.documentos.all():
		ddj = documento.data_json or {}
		guia_docs.append({
			'nro_guia': _v(ddj.get('PDcDocNro')),
			'fecha_guia': _v(ddj.get('PDcDocFec')),
			'tipo_documento': _v(ddj.get('PDcTDcDes')),
			'estado_documento': _v(ddj.get('PDcEst')),
			'moneda': _v(ddj.get('MonNom')),
			'neto_informado_doc': _v(ddj.get('PDcTotNetInf')),
			'subtotal': _v(ddj.get('PDcSubTot')),
			'iva': _v(ddj.get('PDcIVA')),
			'tara_envases_doc': _v(ddj.get('PDcTotEnvTar')),
			'observaciones': _v(ddj.get('PDcObs')),
			'usuario_mod': _v(ddj.get('PDcUsuMod')),
			'fecha_mod': _v(ddj.get('PDcFecMod')),
			# Origen
			'origen_rut': _rut(ddj.get('PDcOriCliDId'), ddj.get('PDcOriCliDV')),
			'origen_razon_social': _v(ddj.get('PDcOriCliRazSoc')),
			'origen_sucursal': _v(ddj.get('PDcOriCliSucNom')),
			'origen_direccion': _v(ddj.get('PDcOriCliSucDir')),
			'origen_comuna': _v(ddj.get('PDcOriCliSucComNom')),
			# Destino
			'destino_rut': _rut(ddj.get('PDcDstCliDId'), ddj.get('PDcDstCliDV')),
			'destino_razon_social': _v(ddj.get('PDcDstCliRazSoc')),
			'destino_sucursal': _v(ddj.get('PDcDstCliSucNom')),
			'destino_direccion': _v(ddj.get('PDcDstCliSucDir')),
			'destino_comuna': _v(ddj.get('PDcDstCliSucComNom')),
			# Facturación
			'facturacion_direccion': _v(ddj.get('PDcFacDir')),
			'facturacion_comuna': _v(ddj.get('PDcFacComNom')),
		})
		for prod in documento.productos_documento.all():
			pdj = prod.data_json or {}
			productos_guia.append({
				'codigo': _v(prod.codigo_producto),
				'nombre': _v(prod.nombre_producto),
				'cantidad': _v(pdj.get('PDcCnt')),
				'neto_informado': _v(pdj.get('PDcProNetInf')),
				'envase': _v(pdj.get('PDcEnvNom')),
				'cant_envases': _v(pdj.get('PDcEnvCnt')),
				'peso_envase': _v(pdj.get('PDcEnvPes')),
				'tara_envase': _v(pdj.get('PDcTarEnv')),
			})

	# Atributos como diccionario
	atributos_dict = {}
	for attr in pesaje.atributos.all().order_by('id'):
		atributos_dict[attr.pes_att_id] = _v(attr.pes_att_val)

	context = {
		'pesaje': pesaje,
		'dj': dj,
		'_v': _v,
		'guia_docs': guia_docs,
		'productos_guia': productos_guia,
		'atributos_dict': atributos_dict,
		# Datos de transporte
		'transporte': {
			'transportista': _v(dj.get('PesTraNom')),
			'rut_transportista': _rut(dj.get('PesTraDId'), dj.get('PesTraDV')),
			'chofer': _v(dj.get('PesComChoNom')),
			'rut_chofer': _rut(dj.get('PesComChoDId'), dj.get('PesComChoDV')),
			'patente': _v(dj.get('VhcPat')),
			'patente_acoplado': _v(dj.get('PesAcoPat')),
			'tipo_carga': _v(dj.get('PesTipCarDes')),
			'tipo_camion': _v(dj.get('PesTipCamNom')),
		},
		# Pesos
		'pesos': {
			'bruto': _v(dj.get('PesVhcComBru') or dj.get('PesTotComBru')),
			'tara': _v(dj.get('PesVhcTar') or dj.get('PesTotTar')),
			'neto': _v(dj.get('PesVhcComNet')),
			'neto_corregido': _v(dj.get('PesVhcComNetCor')),
			'neto_informado': _v(dj.get('PesVhcNetInf')),
		},
		# Datos del pesaje
		'pesaje_info': {
			'nro_pesaje': _v(dj.get('PesNro')),
			'estado': _v(dj.get('PesEst')),
			'ciclo': _v(dj.get('PesCicPesDes')),
			'fecha_ingreso': _v(dj.get('PesFecIng')),
			'balanza_comando': _v(dj.get('PesComBasDes')),
			'balanza_tara': _v(dj.get('PesTarBasDes')),
			'fecha_comando': _v(dj.get('PesComFec')),
			'fecha_tara': _v(dj.get('PesTarFec')),
			'usuario': _v(dj.get('PesUsuMod')),
			'empresa_rut': _rut(dj.get('PesEmpDId'), dj.get('PesEmpDV')),
			'empresa_razon_social': _v(dj.get('PesEmpRazSoc')),
		},
		# Todo el data_json para la sección colapsable
		'pesaje_data_items': sorted(dj.items()),
	}
	return render(request, 'camiones/pesaje_detail.html', context)
