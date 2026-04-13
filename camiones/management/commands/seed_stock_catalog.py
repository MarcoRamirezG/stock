"""
Comando para poblar el catálogo base de stock.
Crea la bodega PRINCIPAL si no existe.

Uso:
    python manage.py seed_stock_catalog
"""
from django.core.management.base import BaseCommand

from camiones.models import Bodega


class Command(BaseCommand):
    help = 'Crea datos base de catálogo de stock (bodegas).'

    def handle(self, *args, **options):
        bodega, created = Bodega.objects.get_or_create(
            codigo='PRINCIPAL',
            defaults={'nombre': 'Bodega Principal'},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Bodega creada: {bodega}'))
        else:
            self.stdout.write(f'Bodega ya existe: {bodega}')

        self.stdout.write(self.style.SUCCESS('Catálogo de stock listo.'))
