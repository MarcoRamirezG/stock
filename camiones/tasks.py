import logging

from celery import shared_task

from camiones.services.sqlserver_source import SqlServerReadError, import_from_sqlserver

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def importar_pesajes_nuevos(self, top=500):
    """Consulta SQL Server y trae los pesajes más recientes que aún no estén importados."""
    try:
        summary = import_from_sqlserver(top=top)
    except SqlServerReadError as exc:
        logger.error('Error conectando a SQL Server: %s', exc)
        raise self.retry(exc=exc)

    logger.info(
        'Importación periódica: leídos=%d importados=%d actualizados=%d omitidos=%d errores=%d',
        summary['leidos'],
        summary['importados'],
        summary['actualizados'],
        summary['omitidos'],
        len(summary['errores']),
    )
    return summary
