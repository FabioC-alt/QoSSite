#!/bin/bash

URL="http://192.168.17.121:30080/?level=high"
TOTAL_REQUESTS=100  # Change this number as needed

for ((i=1; i<=TOTAL_REQUESTS; i++)); do
    curl -s "$URL" &
done

# Wait for all background processes to finish
wait

echo "Sent $TOTAL_REQUESTS requests to $URL"

