#!/bin/bash

mkdir -p .dev/mariadb_data
sudo chmod -R 777 .dev/mariadb_data
docker-compose up -d