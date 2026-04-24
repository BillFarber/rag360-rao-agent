#!/bin/sh
set -eu

if [ "${DEV:-false}" = "true" ]; then
	exec /app/bin/watchfiles \
		--filter all \
		--target-type command \
		'/app/bin/python3 -m rag360_agents.standalone_entrypoint' \
		/app/rag360
fi

exec /app/bin/python3 -m rag360_agents.standalone_entrypoint
