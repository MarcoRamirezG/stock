from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pyodbc
from django.conf import settings

from camiones.services.xml_importer import XmlImportError, import_pesaje_xml

logger = logging.getLogger(__name__)


class SqlServerReadError(Exception):
    """Error de lectura en SQL Server origen."""


def _effective_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = getattr(settings, 'ETRUCK_SQLSERVER', {})
    data = {
        'SERVER': base.get('SERVER', 'pverq2'),
        'DATABASE': base.get('DATABASE', 'WSCLIENTE'),
        'USER': base.get('USER', ''),
        'PASSWORD': base.get('PASSWORD', ''),
        'DRIVER': base.get('DRIVER', 'ODBC Driver 17 for SQL Server'),
        'TRUSTED_CONNECTION': base.get('TRUSTED_CONNECTION', 'yes'),
    }
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
    return data


def _build_connection_string(config: dict[str, Any]) -> str:
    parts = [
        f"DRIVER={{{config['DRIVER']}}}",
        f"SERVER={config['SERVER']}",
        f"DATABASE={config['DATABASE']}",
        'TrustServerCertificate=yes',
    ]

    user = str(config.get('USER') or '').strip()
    password = str(config.get('PASSWORD') or '').strip()
    trusted = str(config.get('TRUSTED_CONNECTION') or 'yes').strip().lower()

    if user and password:
        parts.append(f'UID={user}')
        parts.append(f'PWD={password}')
    else:
        parts.append(f'Trusted_Connection={trusted}')

    return ';'.join(parts)


def fetch_pesaje_recep_rows(
    *,
    ids: list[int] | None = None,
    pes_nro: str | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    top: int = 100,
    config_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Lee registros de WSCLIENTE.dbo.PesajeRecep con filtros opcionales."""
    config = _effective_config(config_overrides)
    connection_string = _build_connection_string(config)

    where_clauses = ['1=1']
    params: list[Any] = []

    if ids:
        placeholders = ','.join('?' for _ in ids)
        where_clauses.append(f'ID IN ({placeholders})')
        params.extend(ids)

    if pes_nro:
        where_clauses.append('PesNro = ?')
        params.append(pes_nro)

    if fecha_desde is not None:
        where_clauses.append('Fecha >= ?')
        params.append(fecha_desde)

    if fecha_hasta is not None:
        where_clauses.append('Fecha <= ?')
        params.append(fecha_hasta)

    top_value = max(1, int(top))

    query = f"""
        SELECT TOP ({top_value})
            ID,
            Fecha,
            Modo,
            BseCod,
            PesNro,
            Estado,
            XML,
            Comentario,
            IntFecha,
            IntErrCode,
            IntErrDesc,
            IntBseCod,
            IntNroPes,
            [Date],
            VhcTip
        FROM [dbo].[PesajeRecep]
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ID DESC
    """

    try:
        with pyodbc.connect(connection_string, timeout=15) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        raise SqlServerReadError(f'Error leyendo WSCLIENTE.dbo.PesajeRecep: {exc}') from exc

    return rows


def import_from_sqlserver(
    *,
    ids: list[int] | None = None,
    pes_nro: str | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    top: int = 100,
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Importa registros desde SQL Server origen y normaliza en tablas Django."""
    rows = fetch_pesaje_recep_rows(
        ids=ids,
        pes_nro=pes_nro,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        top=top,
        config_overrides=config_overrides,
    )

    summary: dict[str, Any] = {
        'leidos': len(rows),
        'importados': 0,
        'actualizados': 0,
        'omitidos': 0,
        'errores': [],
    }

    for row in rows:
        xml_value = row.get('XML')
        if not xml_value or not str(xml_value).strip():
            summary['omitidos'] += 1
            logger.warning('Registro ID=%s omitido: XML vacio.', row.get('ID'))
            continue

        try:
            _, created = import_pesaje_xml(str(xml_value), origen=row)
        except XmlImportError as exc:
            summary['errores'].append(
                {
                    'id': row.get('ID'),
                    'pes_nro': row.get('PesNro'),
                    'error': str(exc),
                }
            )
            logger.exception('Error importando ID=%s PesNro=%s', row.get('ID'), row.get('PesNro'))
            continue

        if created:
            summary['importados'] += 1
        else:
            summary['actualizados'] += 1

    return summary
