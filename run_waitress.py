"""Ejecutar Stock API con Waitress en puerto 777."""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stock.settings')

from waitress import serve
from stock.wsgi import application

if __name__ == '__main__':
    host = '0.0.0.0'
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 777
    print(f'Iniciando Stock API en http://{host}:{port} ...')
    serve(application, host=host, port=port, threads=4)
