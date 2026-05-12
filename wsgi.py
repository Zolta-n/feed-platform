"""
PythonAnywhere WSGI entry point.

Usage (PythonAnywhere WSGI config):
    from wsgi import application

The WSGI server calls `application` as the WSGI callable.
"""
import logging
import os
import sys

# Ensure the project root is on the Python path when deployed on PythonAnywhere
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load .env in development (python-dotenv is optional)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_project_root, ".env"))
except ImportError:
    pass

# Capture the real Python executable before uWSGI replaces sys.executable
_PYTHON_EXECUTABLE = sys.executable

from niche.web.app import create_app

application = create_app()

# Expose the real Python executable path in app config for subprocess use
application.config.setdefault("PYTHON_EXECUTABLE", _PYTHON_EXECUTABLE)

if __name__ == "__main__":
    # Development server
    logging.basicConfig(level=logging.DEBUG)
    application.run(debug=True, port=5000)
