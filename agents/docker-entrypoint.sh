#!/bin/sh
set -eu

if [ "${DEV:-false}" = "true" ]; then
	exec /app/bin/watchfiles \
		--filter all \
		--target-type command \
		'/app/bin/arag-standalone' \
		/app/rag360
fi

exec /app/bin/arag-standalone
