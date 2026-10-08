"""Render entrypoint: locked setup surface until formal Owner enrollment exists."""
import os
from pathlib import Path


def create_app():
    runtime = Path(os.environ.get('MARKETING_RUNTIME_FILE', '/opt/render/project/src/data/cloud-runtime.json'))
    os.environ['MARKETING_CLOUD_MODE'] = 'true'
    os.environ['MARKETING_RUNTIME_FILE'] = str(runtime)
    if runtime.exists():
        from app.main import app
        return app
    from app.core.cloud_setup import create_setup_app
    return create_setup_app(runtime)
