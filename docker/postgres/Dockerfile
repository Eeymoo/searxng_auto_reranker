FROM postgres:16-alpine
# Bake the init SQL into the image so we don't depend on host file permissions
# (Synology NAS clones files as the host user's UID which the container's
#  postgres UID can't read; image-baked files are world-readable by default).
#
# NOTE: keep this file in sync with /migrations/001_init.sql. If you edit the
# schema, update both, or rebuild via `cp migrations/001_init.sql docker/postgres/`.
COPY 001_init.sql /docker-entrypoint-initdb.d/001_init.sql
RUN chmod 0444 /docker-entrypoint-initdb.d/001_init.sql
