from django.contrib import admin

from camiones.models import (
	AtributoPesaje, Bodega, Cliente, ClienteBodega, ClienteProducto,
	ClienteSucursal, DocumentoPesaje, KardexLinea, Operacion, Pesaje,
	Producto, ProductoDocumento,
)


class DocumentoPesajeInline(admin.TabularInline):
	model = DocumentoPesaje
	extra = 0
	show_change_link = True


class AtributoPesajeInline(admin.TabularInline):
	model = AtributoPesaje
	extra = 0


@admin.register(Pesaje)
class PesajeAdmin(admin.ModelAdmin):
	list_display = ('pes_nro', 'vhc_pat', 'pes_tra_nom', 'pes_com_cho_nom', 'pes_vhc_com_net', 'pes_est', 'estado_origen_sql', 'fecha_origen_sql')
	list_filter = ('pes_cic_pes_des', 'estado_origen_sql', 'pes_est')
	search_fields = ('pes_nro', 'vhc_pat', 'pes_tra_nom', 'pes_com_cho_nom')
	readonly_fields = ('creado_en', 'actualizado_en')
	list_per_page = 50
	inlines = [DocumentoPesajeInline, AtributoPesajeInline]


class ProductoDocumentoInline(admin.TabularInline):
	model = ProductoDocumento
	extra = 0


@admin.register(DocumentoPesaje)
class DocumentoPesajeAdmin(admin.ModelAdmin):
	list_display = ('pdc_doc_nro', 'pesaje', 'tipo_documento', 'origen', 'destino', 'fecha_documento')
	search_fields = ('pdc_doc_nro', 'pdc_id')
	inlines = [ProductoDocumentoInline]


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'nombre', 'actualizado_en')
	search_fields = ('codigo', 'nombre')


@admin.register(ProductoDocumento)
class ProductoDocumentoAdmin(admin.ModelAdmin):
	list_display = ('codigo_producto', 'nombre_producto', 'documento', 'cantidad', 'peso')
	search_fields = ('codigo_producto', 'nombre_producto')


@admin.register(AtributoPesaje)
class AtributoPesajeAdmin(admin.ModelAdmin):
	list_display = ('pes_att_id', 'pes_att_val', 'pesaje')
	search_fields = ('pes_att_id', 'pes_att_val')


# ──────────────────────────────────────────────
# Admin de Stock
# ──────────────────────────────────────────────

class ClienteSucursalInline(admin.TabularInline):
	model = ClienteSucursal
	extra = 0


class ClienteBodegaInline(admin.TabularInline):
	model = ClienteBodega
	extra = 0


class ClienteProductoInline(admin.TabularInline):
	model = ClienteProducto
	extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
	list_display = ('rut', 'razon_social', 'activo', 'actualizado_en')
	list_filter = ('activo',)
	search_fields = ('rut', 'razon_social')
	inlines = [ClienteSucursalInline, ClienteBodegaInline, ClienteProductoInline]


@admin.register(Bodega)
class BodegaAdmin(admin.ModelAdmin):
	list_display = ('codigo', 'nombre', 'activo', 'actualizado_en')
	list_filter = ('activo',)
	search_fields = ('codigo', 'nombre')


class KardexLineaInline(admin.TabularInline):
	model = KardexLinea
	extra = 0
	readonly_fields = ('producto', 'bodega', 'cantidad', 'peso', 'stock_anterior', 'stock_posterior', 'creado_en')


@admin.register(Operacion)
class OperacionAdmin(admin.ModelAdmin):
	list_display = ('id', 'external_uid', 'tipo', 'estado', 'ciclo', 'nro_guia', 'bodega', 'cliente', 'peso_neto', 'creado_en')
	list_filter = ('tipo', 'estado', 'ciclo')
	search_fields = ('external_uid', 'nro_guia', 'patente')
	readonly_fields = ('creado_en', 'actualizado_en', 'creado_por')
	list_per_page = 50
	inlines = [KardexLineaInline]


@admin.register(KardexLinea)
class KardexLineaAdmin(admin.ModelAdmin):
	list_display = ('id', 'operacion', 'producto', 'bodega', 'cantidad', 'stock_anterior', 'stock_posterior', 'creado_en')
	list_filter = ('bodega',)
	search_fields = ('producto__codigo', 'producto__nombre')
	list_per_page = 50
