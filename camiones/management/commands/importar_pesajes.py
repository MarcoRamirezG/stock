from __future__ import annotations

from datetime import datetime, time
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date, parse_datetime

from camiones.services.sqlserver_source import SqlServerReadError, import_from_sqlserver


class Command(BaseCommand):
    help = 'Importa XML de pesajes E-truck desde WSCLIENTE.dbo.PesajeRecep y normaliza en modelos Django.'

    def add_arguments(self, parser):
        parser.add_argument('--id', dest='ids', action='append', type=int, help='ID de PesajeRecep (repetible).')
        parser.add_argument('--pes-nro', dest='pes_nro', help='Filtra por PesNro exacto.')
        parser.add_argument('--fecha-desde', dest='fecha_desde', help='Fecha inicial (YYYY-MM-DD o ISO datetime).')
        parser.add_argument('--fecha-hasta', dest='fecha_hasta', help='Fecha final (YYYY-MM-DD o ISO datetime).')
        parser.add_argument('--top', dest='top', type=int, default=100, help='Maximo de filas a leer.')

        parser.add_argument('--server', dest='server', help='Servidor SQL Server (default: pverq2).')
        parser.add_argument('--database', dest='database', help='Base SQL Server (default: WSCLIENTE).')
        parser.add_argument('--user', dest='user', help='Usuario SQL Server.')
        parser.add_argument('--password', dest='password', help='Password SQL Server.')
        parser.add_argument('--driver', dest='driver', help='Driver ODBC SQL Server.')
        parser.add_argument(
            '--trusted-connection',
            dest='trusted_connection',
            choices=['yes', 'no'],
            help='Usar autenticacion integrada (yes/no).',
        )

    def _parse_datetime_arg(self, raw_value: str | None, option_name: str, *, end_of_day: bool = False):
        if not raw_value:
            return None

        dt = parse_datetime(raw_value)
        if dt is not None:
            return dt

        d = parse_date(raw_value)
        if d is not None:
            selected_time = time.max if end_of_day else time.min
            return datetime.combine(d, selected_time)

        raise CommandError(f'Formato invalido para {option_name}: {raw_value}')

    def handle(self, *args, **options):
        fecha_desde = self._parse_datetime_arg(options.get('fecha_desde'), '--fecha-desde')
        fecha_hasta = self._parse_datetime_arg(options.get('fecha_hasta'), '--fecha-hasta', end_of_day=True)

        config_overrides: dict[str, Any] = {
            'SERVER': options.get('server'),
            'DATABASE': options.get('database'),
            'USER': options.get('user'),
            'PASSWORD': options.get('password'),
            'DRIVER': options.get('driver'),
            'TRUSTED_CONNECTION': options.get('trusted_connection'),
        }

        self.stdout.write(self.style.NOTICE('Iniciando importacion de pesajes desde SQL Server...'))

        try:
            summary = import_from_sqlserver(
                ids=options.get('ids'),
                pes_nro=options.get('pes_nro'),
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                top=options.get('top') or 100,
                config_overrides=config_overrides,
            )
        except SqlServerReadError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS('Importacion finalizada.'))
        self.stdout.write(f"Leidos: {summary['leidos']}")
        self.stdout.write(f"Importados (nuevos): {summary['importados']}")
        self.stdout.write(f"Actualizados (reimportados): {summary['actualizados']}")
        self.stdout.write(f"Omitidos (XML vacio): {summary['omitidos']}")
        self.stdout.write(f"Errores: {len(summary['errores'])}")

        if summary['errores']:
            self.stdout.write(self.style.WARNING('Detalle de errores:'))
            for item in summary['errores']:
                self.stdout.write(
                    f"- ID={item.get('id')} PesNro={item.get('pes_nro')} Error={item.get('error')}"
                )
