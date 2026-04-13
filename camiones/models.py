from decimal import Decimal

from django.db import models


# ──────────────────────────────────────────────
# Modelos de pesaje (E-truck)
# ──────────────────────────────────────────────

class Producto(models.Model):
	codigo = models.CharField(max_length=80, primary_key=True)
	nombre = models.CharField(max_length=255, blank=True)
	data_json = models.JSONField(default=dict, blank=True)
	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"{self.codigo} - {self.nombre}" if self.nombre else self.codigo


class Pesaje(models.Model):
	pes_nro = models.CharField(max_length=80, unique=True)

	fecha_origen_sql = models.DateTimeField(null=True, blank=True)
	id_origen_sql = models.BigIntegerField(null=True, blank=True, db_index=True)
	estado_origen_sql = models.CharField(max_length=120, blank=True)
	bse_cod_origen_sql = models.CharField(max_length=80, blank=True)
	modo_origen_sql = models.CharField(max_length=40, blank=True)
	vhc_tip_origen_sql = models.CharField(max_length=40, blank=True)
	comentario_origen_sql = models.TextField(blank=True)

	pes_est = models.CharField(max_length=80, blank=True)
	pes_fec_ing = models.DateTimeField(null=True, blank=True)
	vhc_pat = models.CharField(max_length=40, blank=True)
	pes_tra_nom = models.CharField(max_length=255, blank=True)
	pes_com_cho_nom = models.CharField(max_length=255, blank=True)
	pes_cic_pes_des = models.CharField(max_length=255, blank=True)
	pes_vhc_com_net = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)

	data_json = models.JSONField(default=dict, blank=True)
	xml_original = models.TextField()
	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return f"Pesaje {self.pes_nro}"


class DocumentoPesaje(models.Model):
	pesaje = models.ForeignKey(Pesaje, on_delete=models.CASCADE, related_name='documentos')

	pdc_id = models.CharField(max_length=80, blank=True, db_index=True)
	pdc_doc_nro = models.CharField(max_length=80, blank=True, db_index=True)
	tipo_documento = models.CharField(max_length=80, blank=True)
	fecha_documento = models.DateTimeField(null=True, blank=True)
	origen = models.CharField(max_length=255, blank=True)
	destino = models.CharField(max_length=255, blank=True)

	data_json = models.JSONField(default=dict, blank=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"Doc {self.pdc_doc_nro or self.pdc_id or self.pk} / Pesaje {self.pesaje_id}"


class ProductoDocumento(models.Model):
	documento = models.ForeignKey(DocumentoPesaje, on_delete=models.CASCADE, related_name='productos_documento')
	producto = models.ForeignKey(
		Producto,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='productos_documento',
	)

	codigo_producto = models.CharField(max_length=80, blank=True, db_index=True)
	nombre_producto = models.CharField(max_length=255, blank=True)
	linea = models.CharField(max_length=80, blank=True)
	cantidad = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
	peso = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)

	data_json = models.JSONField(default=dict, blank=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.codigo_producto or 'SIN-COD'} ({self.nombre_producto})"


class AtributoPesaje(models.Model):
	pesaje = models.ForeignKey(Pesaje, on_delete=models.CASCADE, related_name='atributos')
	pes_att_id = models.CharField(max_length=120, blank=True, db_index=True)
	pes_att_val = models.TextField(blank=True)
	data_json = models.JSONField(default=dict, blank=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.pes_att_id}={self.pes_att_val}"


# ──────────────────────────────────────────────
# Modelos de stock
# ──────────────────────────────────────────────

class Cliente(models.Model):
	rut = models.CharField(max_length=20, unique=True)
	razon_social = models.CharField(max_length=255)
	activo = models.BooleanField(default=True)
	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['razon_social']

	def __str__(self) -> str:
		return f"{self.rut} - {self.razon_social}"


class ClienteSucursal(models.Model):
	"""Sucursal de un cliente (e.g. planta CMPC)."""
	cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='sucursales')
	codigo = models.CharField(max_length=80)
	nombre = models.CharField(max_length=255, blank=True)
	activo = models.BooleanField(default=True)

	class Meta:
		unique_together = ('cliente', 'codigo')
		ordering = ['cliente', 'codigo']

	def __str__(self) -> str:
		return f"{self.codigo} - {self.nombre}" if self.nombre else self.codigo


class Bodega(models.Model):
	codigo = models.CharField(max_length=80, unique=True)
	nombre = models.CharField(max_length=255)
	activo = models.BooleanField(default=True)
	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['codigo']

	def __str__(self) -> str:
		return f"{self.codigo} - {self.nombre}"


class ClienteBodega(models.Model):
	"""Mapea un destino de cliente a una bodega."""
	cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='bodegas')
	sucursal = models.ForeignKey(ClienteSucursal, on_delete=models.CASCADE, related_name='bodegas', null=True, blank=True)
	bodega = models.ForeignKey(Bodega, on_delete=models.CASCADE, related_name='clientes')
	es_default = models.BooleanField(default=False)

	class Meta:
		unique_together = ('cliente', 'sucursal', 'bodega')

	def __str__(self) -> str:
		suc = f" / {self.sucursal}" if self.sucursal else ""
		return f"{self.cliente}{suc} → {self.bodega}"


class ClienteProducto(models.Model):
	"""Mapea un código de producto E-truck a un producto de stock para un cliente."""
	cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='productos')
	codigo_etruck = models.CharField(max_length=80)
	producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='clientes_producto')
	activo = models.BooleanField(default=True)

	class Meta:
		unique_together = ('cliente', 'codigo_etruck')

	def __str__(self) -> str:
		return f"{self.cliente.rut}: {self.codigo_etruck} → {self.producto}"


class Operacion(models.Model):
	"""Movimiento de stock generado a partir de un pesaje confirmado."""

	class TipoMov(models.TextChoices):
		ENTRADA = 'ENTRADA', 'Entrada'
		SALIDA = 'SALIDA', 'Salida'

	class Estado(models.TextChoices):
		CONFIRMADO = 'CONFIRMADO', 'Confirmado'
		ANULADO = 'ANULADO', 'Anulado'

	pesaje = models.ForeignKey(Pesaje, on_delete=models.CASCADE, related_name='operaciones')
	external_uid = models.CharField(max_length=160, unique=True, help_text='pes_nro para idempotencia')

	tipo = models.CharField(max_length=10, choices=TipoMov.choices)
	estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.CONFIRMADO)

	ciclo = models.CharField(max_length=20, blank=True)
	nro_guia = models.CharField(max_length=80, blank=True)
	fecha_documento = models.DateTimeField(null=True, blank=True)

	cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='operaciones', null=True, blank=True)
	bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT, related_name='operaciones')

	patente = models.CharField(max_length=40, blank=True)
	transportista = models.CharField(max_length=255, blank=True)
	chofer = models.CharField(max_length=255, blank=True)

	peso_bruto = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal('0'))
	peso_tara = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal('0'))
	peso_neto = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal('0'))

	observaciones = models.TextField(blank=True)
	data_json = models.JSONField(default=dict, blank=True)

	creado_en = models.DateTimeField(auto_now_add=True)
	actualizado_en = models.DateTimeField(auto_now=True)
	creado_por = models.ForeignKey(
		'auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='operaciones_creadas',
	)

	class Meta:
		ordering = ['-creado_en']

	def __str__(self) -> str:
		return f"Op {self.pk} [{self.tipo}] Pesaje={self.pesaje.pes_nro}"


class KardexLinea(models.Model):
	"""Línea de kardex: cada producto movido en una operación."""
	operacion = models.ForeignKey(Operacion, on_delete=models.CASCADE, related_name='lineas')
	producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='kardex_lineas')
	bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT, related_name='kardex_lineas')

	cantidad = models.DecimalField(max_digits=18, decimal_places=3)
	peso = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal('0'))

	stock_anterior = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal('0'))
	stock_posterior = models.DecimalField(max_digits=18, decimal_places=3, default=Decimal('0'))

	creado_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['operacion', 'pk']

	def __str__(self) -> str:
		return f"Kardex Op={self.operacion_id} {self.producto} qty={self.cantidad}"
