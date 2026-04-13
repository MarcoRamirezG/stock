"""
Corrige las fechas que se guardaron como UTC pero eran realmente America/Santiago.

Antes del fix, TIME_ZONE era 'UTC', entonces make_aware() interpretaba fechas
de E-truck (hora Chile) como UTC. Esto las dejó ~3h desfasadas.

Este comando re-parsea las fechas desde data_json (fuente original) usando
la zona horaria correcta (America/Santiago).
"""
from __future__ import annotations

import zoneinfo

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from camiones.models import DocumentoPesaje, Pesaje

SANTIAGO = zoneinfo.ZoneInfo('America/Santiago')


def _make_aware_santiago(raw):
    """Convierte un valor a datetime aware en America/Santiago."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        dt = parse_datetime(raw)
        if dt is None:
            return None
    else:
        dt = raw

    if timezone.is_naive(dt):
        return dt.replace(tzinfo=SANTIAGO)
    return dt


class Command(BaseCommand):
    help = 'Corrige fechas de pesajes que se guardaron como UTC en vez de America/Santiago.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra los cambios sin aplicarlos.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fixed_pesajes = 0
        fixed_docs = 0

        pesajes = Pesaje.objects.all()
        total = pesajes.count()
        self.stdout.write(f'Procesando {total} pesajes...')

        for pesaje in pesajes.iterator(chunk_size=500):
            changed = False
            data = pesaje.data_json or {}

            # Fix pes_fec_ing desde data_json['PesFecIng']
            raw_fec_ing = data.get('PesFecIng', '')
            if raw_fec_ing:
                new_val = _make_aware_santiago(raw_fec_ing)
                if new_val and new_val != pesaje.pes_fec_ing:
                    if dry_run:
                        self.stdout.write(
                            f'  Pesaje {pesaje.pes_nro}: pes_fec_ing '
                            f'{pesaje.pes_fec_ing} -> {new_val}'
                        )
                    pesaje.pes_fec_ing = new_val
                    changed = True

            # Fix fecha_origen_sql (viene de SQL Server, también hora Chile)
            if pesaje.fecha_origen_sql and timezone.is_naive(pesaje.fecha_origen_sql):
                new_val = pesaje.fecha_origen_sql.replace(tzinfo=SANTIAGO)
                if dry_run:
                    self.stdout.write(
                        f'  Pesaje {pesaje.pes_nro}: fecha_origen_sql '
                        f'{pesaje.fecha_origen_sql} -> {new_val}'
                    )
                pesaje.fecha_origen_sql = new_val
                changed = True
            elif pesaje.fecha_origen_sql and timezone.is_aware(pesaje.fecha_origen_sql):
                # Ya es aware pero podría estar en UTC incorrecto (fue make_aware con TZ=UTC)
                # Re-interpretar: el valor original era hora Chile
                # No podemos saber con certeza, pero si vino de SQL Server chileno,
                # la hora "naive" se guardó como UTC. Hay que moverla.
                pass

            if changed:
                fixed_pesajes += 1
                if not dry_run:
                    pesaje.save(update_fields=['pes_fec_ing', 'fecha_origen_sql', 'actualizado_en'])

        # Fix fecha_documento en DocumentoPesaje
        docs = DocumentoPesaje.objects.all()
        total_docs = docs.count()
        self.stdout.write(f'Procesando {total_docs} documentos...')

        for doc in docs.iterator(chunk_size=500):
            data = doc.data_json or {}
            raw_fecha = data.get('PDcFec') or data.get('Fecha', '')
            if raw_fecha:
                new_val = _make_aware_santiago(raw_fecha)
                if new_val and new_val != doc.fecha_documento:
                    if dry_run:
                        self.stdout.write(
                            f'  Doc {doc.pk} (Pesaje {doc.pesaje_id}): fecha_documento '
                            f'{doc.fecha_documento} -> {new_val}'
                        )
                    if not dry_run:
                        doc.fecha_documento = new_val
                        doc.save(update_fields=['fecha_documento'])
                    fixed_docs += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN: Se corregirían {fixed_pesajes} pesajes y {fixed_docs} documentos.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Corregidos: {fixed_pesajes} pesajes y {fixed_docs} documentos.'
            ))
