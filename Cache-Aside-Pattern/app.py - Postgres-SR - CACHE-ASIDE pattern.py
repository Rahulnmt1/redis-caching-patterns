from flask import Flask, request, jsonify
import psycopg2
import redis
import json
import logging
import time

# ------- CONFIGURATION -------
PG_DBNAME = "postgres"
PG_USER = "postgres"
PG_PASS = "postgres"  # <-- Set your Postgres password
PG_HOST = "localhost"
PG_PORT = 5432

REDIS_HOST = "localhost"
REDIS_PORT = 12000
REDIS_DB = 0

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# --- DB CONNECTION HELPERS ---
def get_pg_conn():
    return psycopg2.connect(
        dbname=PG_DBNAME, user=PG_USER, password=PG_PASS, host=PG_HOST, port=PG_PORT
    )

def get_redis_conn():
    return redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
    )

# --- POST: Insert/Update Customer in Postgres only (no Redis caching) ---
@app.route("/customer", methods=["POST"])
def create_customer():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    required_fields = [
        "aadhaar_number", "name", "email", "mobile",
        "pan_number", "dob", "address", "products"
    ]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    aadhaar = data["aadhaar_number"]
    products = data["products"]

    try:
        pg = get_pg_conn()
        with pg.cursor() as cur:
            # Insert or update customer
            cur.execute("""
                INSERT INTO customer
                (aadhaar_number, name, email, mobile, pan_number, dob, address)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (aadhaar_number) DO UPDATE SET
                    name=EXCLUDED.name,
                    email=EXCLUDED.email,
                    mobile=EXCLUDED.mobile,
                    pan_number=EXCLUDED.pan_number,
                    dob=EXCLUDED.dob,
                    address=EXCLUDED.address
                """,
                (aadhaar, data["name"], data["email"], data["mobile"],
                 data["pan_number"], data["dob"], data["address"])
            )

            # Delete old products for this customer
            cur.execute("DELETE FROM customer_product WHERE aadhaar_number = %s", (aadhaar,))

            # Insert new products
            for product in products:
                cur.execute("""
                    INSERT INTO customer_product
                    (aadhaar_number, product_type, account_status, date)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (aadhaar, product["type"], product["account_status"], product["date"])
                )
        pg.commit()
        pg.close()
    except Exception as e:
        logging.error(f"[PG][INSERT] Error inserting aadhaar {aadhaar}: {e}")
        return jsonify({"error": f"Postgres error: {str(e)}"}), 500

    return jsonify({"status": "inserted", "aadhaar_number": aadhaar}), 201

# --- GET: Fetch Customer with Cache-Aside Pattern and Timing ---
@app.route("/customer/<aadhaar>", methods=["GET"])
def fetch_customer(aadhaar):
    r = get_redis_conn()
    key = f"customer:{aadhaar}"

    # 1. Try Redis (cache) first, with timing
    if r.exists(key):
        t1 = time.perf_counter_ns()
        data = r.hgetall(key)
        t2 = time.perf_counter_ns()
        redis_usecs = (t2 - t1) / 1000  # microseconds

        logging.info(f"[CACHE HIT] Aadhaar {aadhaar} from Redis: hgetall took {redis_usecs:.1f}us")

        try:
            data["products"] = json.loads(data.get("products", "[]"))
        except Exception:
            data["products"] = []

        data["source"] = "redis"
        data["redis_hgetall_microseconds"] = redis_usecs

        return jsonify(data), 200

    # 2. Cache miss: time Postgres fetch only
    logging.info(f"[CACHE MISS] Aadhaar {aadhaar}: Loading from Postgres, caching to Redis.")
    t1 = time.perf_counter_ns()

    try:
        pg = get_pg_conn()
        with pg.cursor() as cur:
            # Fetch customer record
            cur.execute("""
                SELECT aadhaar_number, name, email, mobile, pan_number, dob, address
                FROM customer WHERE aadhaar_number = %s
            """, (aadhaar, ))
            row = cur.fetchone()

            if not row:
                pg.close()
                return jsonify({"error": "Customer not found"}), 404

            customer = {
                "aadhaar_number": row[0],
                "name": row[1],
                "email": row[2],
                "mobile": row[3],
                "pan_number": row[4],
                "dob": str(row[5]),
                "address": row[6]
            }

            # Fetch products for customer
            cur.execute("""
                SELECT product_type, account_status, date
                FROM customer_product WHERE aadhaar_number = %s
            """, (aadhaar, ))

            products = []
            for p in cur.fetchall():
                products.append({
                    "type": p[0],
                    "account_status": p[1],
                    "date": str(p[2])
                })

            customer["products"] = products
            customer["source"] = "postgres"
        pg.close()

    except Exception as e:
        logging.error(f"[PG][READ] Error for Aadhaar {aadhaar}: {e}")
        return jsonify({"error": f"Postgres error: {str(e)}"}), 500

    t2 = time.perf_counter_ns()
    pg_usecs = (t2 - t1) / 1000  # microseconds
    customer["postgres_fetch_microseconds"] = pg_usecs

    # --- Insert artificial delay for demo ---
    time.sleep(.95)  # .95 seconds delay to exaggerate Postgres fetch time for demo

    logging.info(f"[PG][READ TIMING] Aadhaar {aadhaar}: db fetch took {pg_usecs:.1f}us")

    # Cache result in Redis for next queries
    try:
        r.hset(
            key,
            mapping={
                **{k: v for k, v in customer.items() if k not in ["products", "source", "postgres_fetch_microseconds"]},
                "products": json.dumps(products)
            }
        )
        logging.info(f"[REDIS][SET] Aadhaar {aadhaar} cached after Postgres read.")
    except Exception as e:
        logging.error(f"[REDIS][SET] Error caching Aadhaar {aadhaar}: {e}")

    return jsonify(customer), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)