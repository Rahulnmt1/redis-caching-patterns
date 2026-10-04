The code illustrates following:

1. Insert data in Postgres.

2. When data is read from API / postman following happens:

    a. The data is read from Redis Cache but since the data is not available in cache there is cache miss.
    b. The app then goes to Postgres reads the data and also insert the data in redis cache
    c. When we retry or read the same data again the data is read from Redis cache which is cache hit.

2025-07-29 15:49:00,732 | INFO | 127.0.0.1 - - [29/Jul/2025 15:49:00] "POST /customer HTTP/1.1" 201 -
2025-07-29 15:49:18,446 | INFO | [CACHE MISS] Aadhaar 876543220003: Loading from Postgres, caching to Redis.
2025-07-29 15:49:19,413 | INFO | [PG][READ TIMING] Aadhaar 876543220003: db fetch took 15551.4us
2025-07-29 15:49:19,418 | INFO | [REDIS][SET] Aadhaar 876543220003 cached after Postgres read.
2025-07-29 15:49:19,420 | INFO | 127.0.0.1 - - [29/Jul/2025 15:49:19] "GET /customer/876543220003 HTTP/1.1" 200 -
2025-07-29 15:49:32,419 | INFO | [CACHE HIT] Aadhaar 876543220003 from Redis: hgetall took 3333.8us
2025-07-29 15:49:32,420 | INFO | 127.0.0.1 - - [29/Jul/2025 15:49:32] "GET /customer/876543220003 HTTP/1.1" 200 -

3. We demostrate the time difference between read the data from Postgres and Redis.