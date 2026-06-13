# 1) seeker running with SERIAL gate: LAKE_SEARCH_MAX_CONCURRENCY=1
python3 seeker_search_bench.py run \
  --url http://localhost:8095 --dataset my_logs \
  --auth "Bearer <base64>" \
  --requests 300 --concurrency 30 --randomize \
  --label serial --out serial.json

# 2) restart seeker with PARALLEL gate (kill-switch): LAKE_SEARCH_MAX_CONCURRENCY=0
python3 seeker_search_bench.py run \
  --url http://localhost:8095 --dataset my_logs \
  --auth "Bearer <base64>" \
  --requests 300 --concurrency 30 --randomize \
  --label parallel --out parallel.json

# 3) compare
python3 seeker_search_bench.py compare serial.json parallel.json