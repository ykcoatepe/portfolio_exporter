web: gunicorn -k uvicorn.workers.UvicornWorker psd.web.server:make_app --bind 0.0.0.0:51127 --workers 2 --timeout 0
ingestor: python -m psd.ingestor.main
scanner: python -m psd.sentinel.scan
