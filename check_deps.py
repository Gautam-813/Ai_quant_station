try:
    import fastapi
    print('FastAPI available')
except ImportError:
    print('FastAPI not installed')