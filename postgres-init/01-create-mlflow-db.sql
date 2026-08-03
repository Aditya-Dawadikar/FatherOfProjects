-- Runs once, only against a fresh postgres-data volume (docker-entrypoint-initdb.d scripts are
-- skipped once the data directory already has data). Creates a second database on the same dev
-- Postgres server for MLflowServer's backend store, kept separate from the webscraper/
-- job_matches app schema even though both live on the same local container.
CREATE DATABASE mlflow;
