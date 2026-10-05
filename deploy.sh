#!/usr/bin/env bash
set -e
cd ~/Project1
git pull --ff-only
docker compose build studio
docker compose up -d studio
docker compose ps studio
curl -fsS http://localhost:3000/api/health && echo "OK"
