import os

# Keep ordinary unit tests independent of the developer's local .env.
# Explicit DATABASE_URL supplied by the shell is preserved so integration
# tests can opt into PostgreSQL.
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = ""
