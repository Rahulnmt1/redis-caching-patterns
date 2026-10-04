import psycopg2
import redis
from faker import Faker
import random
from datetime import date
import sys
import time

# ---- CONFIGURATION ----

# PostgreSQL DB config
PG_DBNAME = "postgres"
PG_USER = "postgres"
PG_PASS = "postgres"  # replace with your DB password
PG_HOST = "localhost"
PG_PORT = 5432

# Redis config
REDIS_HOST = "localhost"
REDIS_PORT = 12000
REDIS_DB = 0

# Data parameters
NUM_CUSTOMERS = 1000
PRODUCT_TYPES = ["current_account", "saving_account", "fd", "2_wheeler_loan", "4_wheeler_loan"]
ACCOUNT_STATUS_OPTIONS = ["opened", "closed"]

# ---- DB CONNECTIONS ----

try:
    psql_conn = psycopg2.connect(
        dbname=PG_DBNAME, user=PG_USER, password=PG_PASS, host=PG_HOST, port=PG_PORT
    )
    psql_conn.autocommit = False
except Exception as e:
    print(f"Could not connect to Postgres: {e}")
    sys.exit(1)

try:
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
    )
    redis_client.ping()
except Exception as e:
    print(f"Could not connect to Redis: {e}")
    sys.exit(1)

fake = Faker()
aadhaar_set = set()

# ---- HELPER: Generate Unique Aadhaar ----

def get_unique_aadhaar():
    while True:
        aadhaar = str(fake.unique.random_number(digits=12, fix_len=True))
        if len(aadhaar) == 12 and aadhaar not in aadhaar_set and not aadhaar.startswith("0"):
            aadhaar_set.add(aadhaar)
            return aadhaar

# ---- MAIN BULK INSERT ----

fail_count_customer = 0
fail_count_product = 0
inserts_product = 0
inserts_customer = 0

start_time = time.time()

for cust_num in range(1, NUM_CUSTOMERS + 1):
    # Generate base customer KYC/profile
    aadhaar = get_unique_aadhaar()
    name = fake.name()
    email = fake.email()[:100]
    mobile = fake.phone_number().replace(" ", "")[:20]  # Truncate + strip spaces
    pan = fake.bothify(text='?????#??#?')[:10]
    dob = fake.date_of_birth(minimum_age=18, maximum_age=80)
    address = fake.address().replace("\n", ", ")[:255]  # reasonable truncation

    # Generate banking product(s)
    num_products = random.randint(1, 4)
    products = []
    for _ in range(num_products):
        prod_type = random.choice(PRODUCT_TYPES)
        status = random.choice(ACCOUNT_STATUS_OPTIONS)
        # Date: up to 10 years back, always before today
        open_date = fake.date_between(start_date='-10y', end_date='today')
        products.append({
            "type": prod_type,
            "account_status": status,
            "date": open_date
        })

    # 1. Insert into Postgres (customer)
    try:
        with psql_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO customer (aadhaar_number, name, email, mobile, pan_number, dob, address) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (aadhaar, name, email, mobile, pan, dob, address)
            )
            psql_conn.commit()
            inserts_customer += 1
    except Exception as e:
        print(f"[ERROR][customer_insert] Aadhaar={aadhaar}: {e}")
        psql_conn.rollback()
        fail_count_customer += 1
        continue  # Don't insert products if customer failed

    # Confirm customer exists before products insert
    cust_exists = False
    try:
        with psql_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM customer WHERE aadhaar_number=%s", (aadhaar,))
            if cur.fetchone():
                cust_exists = True
    except Exception as e:
        print(f"[ERROR][customer_exists_check] Aadhaar={aadhaar}: {e}")

    if not cust_exists:
        print(f"[SKIP] Products not inserted for missing Aadhaar={aadhaar}")
        fail_count_product += len(products)
        continue

    # 2. Insert customer products (Postgres) individually for troubleshooting
    for product in products:
        try:
            with psql_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO customer_product (aadhaar_number, product_type, account_status, date) "
                    "VALUES (%s, %s, %s, %s)",
                    (aadhaar, product["type"], product["account_status"], product["date"])
                )
                psql_conn.commit()
                inserts_product += 1
        except Exception as e:
            print(f"[ERROR][product_insert] Aadhaar={aadhaar}, Product={product}: {e}")
            psql_conn.rollback()
            fail_count_product += 1

    # 3. Insert into Redis (customer hash with product list as JSON string)
    try:
        serializable_products = [
            {
                "type": p["type"],
                "account_status": p["account_status"],
                "date": str(p["date"])
            } for p in products
        ]
        redis_client.hset(f"customer:{aadhaar}", mapping={
            "aadhaar_number": aadhaar,
            "name": name,
            "email": email,
            "mobile": mobile,
            "pan_number": pan,
            "dob": str(dob),
            "address": address,
            "products": str(serializable_products)  # Use JSON if strict structure needed
        })
    except Exception as e:
        print(f"[ERROR][redis_insert] Aadhaar={aadhaar}: {e}")

    # Progress feedback
    if cust_num % 100 == 0 or cust_num == NUM_CUSTOMERS:
        print(f"Inserted {cust_num} customers...")

# ---- SUMMARY ----

elapsed = time.time() - start_time

print("\n--- Bulk Insert Summary ---")
print(f"Customers attempted:    {NUM_CUSTOMERS}")
print(f"Customers inserted:    {inserts_customer}")
print(f"Customer insert fails: {fail_count_customer}")
print(f"Products inserted:     {inserts_product}")
print(f"Product insert fails:  {fail_count_product}")
print(f"Elapsed time:          {elapsed:.2f} seconds")

# Close connections
psql_conn.close()
redis_client.close()