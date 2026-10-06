<p align="center">
  <img src="assets/shri-radha.png" alt="श्री राधा" width="200">
</p>

# Redis Caching Patterns — Cache-Aside with PostgreSQL

Cache-aside pattern with Redis in front of PostgreSQL: a Flask API showing cache miss → load from Postgres → populate Redis → cache hit, plus a bulk-insert loader.

## Contents

- [`Cache-Aside-Pattern/`](Cache-Aside-Pattern/)

## Configuration & secrets

Confidential files (`.env`, credentials, keys) are kept out of this repository in the owner's private vault. Link them into a fresh clone with:

```bash
export DEMO_SECRETS_DIR=~/Documents/RWork/secrets   # default location
./link-secrets.sh
```
