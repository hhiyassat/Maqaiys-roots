# maqayis_v2/test_api.py is a command-line demo script (runs queries at import
# and calls sys.exit), not a pytest module; keep pytest from collecting it.
collect_ignore = ["maqayis_v2/test_api.py"]
