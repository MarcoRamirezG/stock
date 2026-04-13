"""
Tests del servicio de stock: importar XML y confirmar operaciones.

Cobertura:
- Ciclo 1 (Recepción → ENTRADA)
- Ciclo 2 (Despacho → SALIDA)
- Ciclo 8 (Transferencia → SALIDA + ENTRADA)
- Ciclo inválido → error
- Idempotencia (doble envío del mismo XML)
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from camiones.models import Bodega, Cliente, ClienteProducto, KardexLinea, Operacion, Producto
from camiones.services.stock_service import (
    CicloNoSoportado,
    importar_xml_y_confirmar,
)

# ─── XML Templates ───

XML_CICLO_1 = """<?xml version="1.0" encoding="utf-8"?>
<Pesaje>
  <PesNro>TEST-001</PesNro>
  <PesEst>Finalizado</PesEst>
  <PesFecIng>2025-01-15T10:30:00</PesFecIng>
  <VhcPat>ABCD12</VhcPat>
  <PesTraNom>Transportes Test</PesTraNom>
  <PesComChoNom>Juan Chofer</PesComChoNom>
  <PesCicPesDes>Recepción</PesCicPesDes>
  <PesVhcComBru>25000</PesVhcComBru>
  <PesVhcTar>10000</PesVhcTar>
  <PesVhcComNet>15000</PesVhcComNet>
  <Documentos>
    <Documento>
      <PDcID>1</PDcID>
      <PDcDocNro>GD-100</PDcDocNro>
      <PDcTipDes>Guia Despacho</PDcTipDes>
      <PDcFec>2025-01-15</PDcFec>
      <PDcOriRut>76.000.000-1</PDcOriRut>
      <PDcOriNom>Forestal Test S.A.</PDcOriNom>
      <PDcDesRut>99.999.999-9</PDcDesRut>
      <PDcDesNom>Puerto Destino</PDcDesNom>
      <Productos>
        <Producto>
          <PDcProCod>MADERA-01</PDcProCod>
          <PDcProNom>Madera Pino</PDcProNom>
          <PDcProCan>100</PDcProCan>
          <PDcProPes>15000</PDcProPes>
        </Producto>
      </Productos>
    </Documento>
  </Documentos>
</Pesaje>"""

XML_CICLO_2 = """<?xml version="1.0" encoding="utf-8"?>
<Pesaje>
  <PesNro>TEST-002</PesNro>
  <PesEst>Finalizado</PesEst>
  <PesFecIng>2025-01-16T08:00:00</PesFecIng>
  <VhcPat>WXYZ99</VhcPat>
  <PesTraNom>Transportes Salida</PesTraNom>
  <PesComChoNom>Pedro Chofer</PesComChoNom>
  <PesCicPesDes>Despacho</PesCicPesDes>
  <PesVhcComBru>20000</PesVhcComBru>
  <PesVhcTar>8000</PesVhcTar>
  <PesVhcComNet>12000</PesVhcComNet>
  <Documentos>
    <Documento>
      <PDcID>2</PDcID>
      <PDcDocNro>GD-200</PDcDocNro>
      <PDcTipDes>Guia Despacho</PDcTipDes>
      <PDcFec>2025-01-16</PDcFec>
      <PDcOriRut>99.999.999-9</PDcOriRut>
      <PDcOriNom>Puerto Origen</PDcOriNom>
      <PDcDesRut>76.000.000-1</PDcDesRut>
      <PDcDesNom>Forestal Test S.A.</PDcDesNom>
      <Productos>
        <Producto>
          <PDcProCod>MADERA-01</PDcProCod>
          <PDcProNom>Madera Pino</PDcProNom>
          <PDcProCan>50</PDcProCan>
          <PDcProPes>6000</PDcProPes>
        </Producto>
      </Productos>
    </Documento>
  </Documentos>
</Pesaje>"""

XML_CICLO_8 = """<?xml version="1.0" encoding="utf-8"?>
<Pesaje>
  <PesNro>TEST-008</PesNro>
  <PesEst>Finalizado</PesEst>
  <PesFecIng>2025-01-17T09:00:00</PesFecIng>
  <VhcPat>TRAN88</VhcPat>
  <PesTraNom>Transportes Transfer</PesTraNom>
  <PesComChoNom>Luis Chofer</PesComChoNom>
  <PesCicPesDes>Transferencia entre bodegas</PesCicPesDes>
  <PesVhcComBru>18000</PesVhcComBru>
  <PesVhcTar>7000</PesVhcTar>
  <PesVhcComNet>11000</PesVhcComNet>
  <Documentos>
    <Documento>
      <PDcID>8</PDcID>
      <PDcDocNro>TR-800</PDcDocNro>
      <PDcTipDes>Transferencia</PDcTipDes>
      <PDcFec>2025-01-17</PDcFec>
      <PDcOriRut>99.999.999-9</PDcOriRut>
      <PDcOriNom>Bodega Origen</PDcOriNom>
      <PDcDesRut>99.999.999-9</PDcDesRut>
      <PDcDesNom>Bodega Destino</PDcDesNom>
      <Productos>
        <Producto>
          <PDcProCod>MADERA-01</PDcProCod>
          <PDcProNom>Madera Pino</PDcProNom>
          <PDcProCan>30</PDcProCan>
          <PDcProPes>3300</PDcProPes>
        </Producto>
      </Productos>
    </Documento>
  </Documentos>
</Pesaje>"""

XML_CICLO_INVALIDO = """<?xml version="1.0" encoding="utf-8"?>
<Pesaje>
  <PesNro>TEST-999</PesNro>
  <PesEst>Finalizado</PesEst>
  <PesCicPesDes>Ciclo Especial</PesCicPesDes>
  <Documentos>
    <Documento>
      <PDcID>99</PDcID>
      <PDcDocNro>XX-999</PDcDocNro>
    </Documento>
  </Documentos>
</Pesaje>"""


class StockServiceBaseTest(TestCase):
    """Base con fixtures comunes."""

    def setUp(self):
        self.bodega = Bodega.objects.create(codigo='PRINCIPAL', nombre='Bodega Principal')
        self.producto = Producto.objects.create(codigo='MADERA-01', nombre='Madera Pino')
        self.user = User.objects.create_user('testuser', password='testpass')


class TestCiclo1Recepcion(StockServiceBaseTest):
    """Ciclo 1 (Recepción) → ENTRADA de stock."""

    def test_crea_operacion_entrada(self):
        result = importar_xml_y_confirmar(XML_CICLO_1, user=self.user)

        self.assertTrue(result['created'])
        self.assertFalse(result.get('duplicado', False))

        op = result['operacion']
        self.assertEqual(op.tipo, 'ENTRADA')
        self.assertEqual(op.ciclo, '1')
        self.assertEqual(op.nro_guia, 'GD-100')
        self.assertEqual(op.patente, 'ABCD12')
        self.assertEqual(op.peso_neto, Decimal('15000'))
        self.assertEqual(op.peso_bruto, Decimal('25000'))
        self.assertEqual(op.peso_tara, Decimal('10000'))

    def test_crea_linea_kardex(self):
        result = importar_xml_y_confirmar(XML_CICLO_1, user=self.user)

        lineas = result['lineas']
        self.assertEqual(len(lineas), 1)

        linea = lineas[0]
        self.assertEqual(linea.producto.codigo, 'MADERA-01')
        self.assertEqual(linea.cantidad, Decimal('100'))
        self.assertEqual(linea.stock_anterior, Decimal('0'))
        self.assertEqual(linea.stock_posterior, Decimal('100'))


class TestCiclo2Despacho(StockServiceBaseTest):
    """Ciclo 2 (Despacho) → SALIDA de stock."""

    def test_crea_operacion_salida(self):
        result = importar_xml_y_confirmar(XML_CICLO_2, user=self.user)

        op = result['operacion']
        self.assertEqual(op.tipo, 'SALIDA')
        self.assertEqual(op.ciclo, '2')
        self.assertEqual(op.nro_guia, 'GD-200')
        self.assertEqual(op.peso_neto, Decimal('12000'))

    def test_kardex_resta_stock(self):
        result = importar_xml_y_confirmar(XML_CICLO_2, user=self.user)

        lineas = result['lineas']
        self.assertEqual(len(lineas), 1)

        linea = lineas[0]
        self.assertEqual(linea.cantidad, Decimal('-50'))
        self.assertEqual(linea.stock_anterior, Decimal('0'))
        self.assertEqual(linea.stock_posterior, Decimal('-50'))


class TestCiclo8Transferencia(StockServiceBaseTest):
    """Ciclo 8 (Transferencia) → SALIDA + ENTRADA."""

    def test_crea_dos_operaciones(self):
        result = importar_xml_y_confirmar(XML_CICLO_8, user=self.user)

        self.assertIn('operacion', result)
        self.assertIn('operacion_salida', result)

        op_entrada = result['operacion']
        op_salida = result['operacion_salida']

        self.assertEqual(op_entrada.tipo, 'ENTRADA')
        self.assertEqual(op_salida.tipo, 'SALIDA')
        self.assertEqual(op_entrada.ciclo, '8')
        self.assertEqual(op_salida.ciclo, '8')

    def test_operaciones_count(self):
        importar_xml_y_confirmar(XML_CICLO_8, user=self.user)
        self.assertEqual(Operacion.objects.count(), 2)


class TestCicloInvalido(StockServiceBaseTest):
    """Ciclo no soportado → CicloNoSoportado."""

    def test_ciclo_invalido_lanza_error(self):
        with self.assertRaises(CicloNoSoportado):
            importar_xml_y_confirmar(XML_CICLO_INVALIDO, user=self.user)


class TestIdempotencia(StockServiceBaseTest):
    """Doble envío del mismo XML → no duplica operación."""

    def test_segundo_envio_no_crea(self):
        r1 = importar_xml_y_confirmar(XML_CICLO_1, user=self.user)
        self.assertTrue(r1['created'])

        r2 = importar_xml_y_confirmar(XML_CICLO_1, user=self.user)
        self.assertTrue(r2['duplicado'])
        self.assertFalse(r2['created'])

        self.assertEqual(r1['operacion'].pk, r2['operacion'].pk)
        self.assertEqual(Operacion.objects.count(), 1)


class TestFlujoCombinado(StockServiceBaseTest):
    """Entrada seguida de salida → kardex correcto."""

    def test_entrada_luego_salida(self):
        r1 = importar_xml_y_confirmar(XML_CICLO_1, user=self.user)

        # Después de entrada: stock = 100
        linea_ent = r1['lineas'][0]
        self.assertEqual(linea_ent.stock_posterior, Decimal('100'))
        self.assertEqual(linea_ent.bodega.codigo, 'PRINCIPAL')

        r2 = importar_xml_y_confirmar(XML_CICLO_2, user=self.user)

        linea_sal = r2['lineas'][0]
        # Verificar que la bodega es la misma
        self.assertEqual(linea_sal.bodega.codigo, 'PRINCIPAL')
        self.assertEqual(linea_sal.producto.codigo, 'MADERA-01')
        # Después de salida: stock = 100 - 50 = 50
        self.assertEqual(linea_sal.stock_anterior, Decimal('100'))
        self.assertEqual(linea_sal.stock_posterior, Decimal('50'))
