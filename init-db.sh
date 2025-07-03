#!/bin/bash
set -e

chown -R postgres:postgres /var/lib/postgresql/data
chmod 700 /var/lib/postgresql/data

if [ -z "$(ls -A /var/lib/postgresql/data)" ]; then
    gosu postgres initdb --locale en_US.UTF-8
    gosu postgres pg_ctl -D /var/lib/postgresql/data -l logfile start
    sleep 5
    gosu postgres psql -c "ALTER USER bot WITH PASSWORD 'botpassword';"
    gosu postgres pg_ctl -D /var/lib/postgresql/data -m fast -w stop
fi

exec "$@"