import os
import sys
import socket
import smtplib
import psycopg
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def check_db():
    print("Checking Database connectivity...")
    engine = os.getenv("DB_ENGINE", "")
    if "postgresql" not in engine:
        print(f"Skipping DB check for engine: {engine}")
        return True
    
    try:
        conn = psycopg.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            connect_timeout=5
        )
        conn.close()
        print("✅ Database connectivity: OK")
        return True
    except Exception as e:
        print(f"❌ Database connectivity: FAILED - {e}")
        return False

def check_smtp():
    print("Checking SMTP connectivity...")
    host = os.getenv("EMAIL_HOST")
    port = int(os.getenv("EMAIL_PORT", 25))
    user = os.getenv("EMAIL_HOST_USER")
    password = os.getenv("EMAIL_HOST_PASSWORD")
    
    if not host:
        print("⚠️ EMAIL_HOST not set, skipping SMTP check.")
        return True
    
    try:
        server = smtplib.SMTP(host, port, timeout=5)
        if os.getenv("EMAIL_USE_TLS") == "True":
            server.starttls()
        if user and password:
            server.login(user, password)
        server.quit()
        print("✅ SMTP connectivity: OK")
        return True
    except Exception as e:
        print(f"❌ SMTP connectivity: FAILED - {e}")
        return False

def check_redis():
    print("Checking Redis connectivity...")
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("⚠️ REDIS_URL not set, skipping Redis check.")
        return True
    
    try:
        import redis
        r = redis.from_url(redis_url, socket_timeout=5)
        r.ping()
        print("✅ Redis connectivity: OK")
        return True
    except Exception as e:
        print(f"❌ Redis connectivity: FAILED - {e}")
        return False

if __name__ == "__main__":
    db_ok = check_db()
    smtp_ok = check_smtp()
    redis_ok = check_redis()
    
    if db_ok and smtp_ok and redis_ok:
        print("\n🚀 Production environment validation: SUCCESS")
        sys.exit(0)
    else:
        print("\n🛑 Production environment validation: FAILED")
        sys.exit(1)
