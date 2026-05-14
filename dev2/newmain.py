import time
import random
import math
import pickle
from typing import Optional, List, Tuple, Dict
from math import exp

import psycopg2
from psycopg2 import sql
from faker import Faker
from tqdm import tqdm
import mmh3
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Connection parameters
DB_PARAMS = {
    "host": "localhost",
    "port": "5432",
    "database": "bloom",
    "user": "postgres",
    "password": "postgres",
}

class UserBloomFilter:
    def __init__(self, size: int, num_hashes: int = 4):
        """
        Initialize Bloom filter for username lookup
        
        size: number of bits in the filter
        num_hashes: number of hash functions to use
        """
        self.size = size
        self.num_hashes = num_hashes
        self.bit_array = [0] * size
    
    def _hashes(self, username: str):
        """Generate multiple hash values for the username"""
        for i in range(self.num_hashes):
            hash_val = mmh3.hash(username, i) % self.size
            yield hash_val
    
    def add(self, username: str):
        """Add username to bloom filter"""
        for hash_val in self._hashes(username):
            self.bit_array[hash_val] = 1
    
    def check(self, username: str) -> bool:
        """
        Check if username MIGHT exist in database
        """
        for hash_val in self._hashes(username):
            if self.bit_array[hash_val] == 0:
                return False
        return True
    
    def get_false_positive_rate(self, n: Optional[int] = None) -> float:
        """Calculate approximate false positive probability"""
        k = self.num_hashes
        m = self.size
        if n is None:
            n = sum(self.bit_array)  # Approximate number of items
        if n == 0:
            return 0
        return (1 - exp(-k * n / m)) ** k

class UserDatabaseWithBloom:
    def __init__(self, db_params: dict, bloom_size: int = 10_000_000):
        """Initialize database connection and bloom filter"""
        self.conn = psycopg2.connect(**db_params)
        self.bloom = UserBloomFilter(size=bloom_size, num_hashes=4)
        self.cursor = self.conn.cursor()
        self._load_existing_usernames()
    
    def _load_existing_usernames(self):
        """Load all existing usernames into bloom filter"""
        print(f"{Fore.CYAN}📊 Loading existing users into Bloom filter...")
        start_time = time.time()
        
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total = self.cursor.fetchone()[0]
        
        if total == 0:
            print(f"{Fore.YELLOW}⚠️ No users found in database.")
            return

        self.cursor.execute("SELECT username FROM users")
        
        # Using a small chunk size for memory efficiency if needed
        count = 0
        for row in self.cursor:
            self.bloom.add(row[0])
            count += 1
            if count % 100000 == 0:
                print(f"  Loaded {count:,} / {total:,} usernames...")
        
        elapsed = time.time() - start_time
        print(f"{Fore.GREEN}✅ Loaded {count:,} usernames in {elapsed:.2f} seconds")
        print(f"{Fore.CYAN}📈 Estimated false positive rate: ~{self.bloom.get_false_positive_rate(n=count)*100:.2f}%")
    
    def query_username(self, username: str) -> dict:
        """
        Query username using both Bloom filter and Database for efficiency check
        """
        # 1. Bloom Filter Check
        start_bloom = time.time()
        bloom_result = self.bloom.check(username)
        bloom_time = time.time() - start_bloom
        
        db_result = False
        db_time = 0.0
        status = ""
        
        # 2. Database Check (only if Bloom says yes)
        if bloom_result:
            start_db = time.time()
            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM users WHERE username = %s)", (username,))
            db_result = self.cursor.fetchone()[0]
            db_time = time.time() - start_db
            
            if db_result:
                status = "Confirmed (True Positive)"
            else:
                status = "False Positive"
        else:
            status = "Definitively Not Found (Filtered)"
            
        return {
            "username": username,
            "bloom_result": bloom_result,
            "bloom_time_ms": bloom_time * 1000,
            "db_result": db_result,
            "db_time_ms": db_time * 1000 if bloom_result else None,
            "status": status
        }

    def close(self):
        self.cursor.close()
        self.conn.close()

def setup_database():
    """Run the SQL setup script to create database and tables"""
    try:
        print(f"{Fore.CYAN}📡 Connecting to PostgreSQL...")
        # Connect to 'postgres' first to create 'bloom' db
        conn_temp = psycopg2.connect(
            host=DB_PARAMS["host"],
            port=DB_PARAMS["port"],
            user=DB_PARAMS["user"],
            password=DB_PARAMS["password"],
            database="postgres"
        )
        conn_temp.autocommit = True
        cursor_temp = conn_temp.cursor()

        cursor_temp.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DB_PARAMS["database"],)
        )
        if not cursor_temp.fetchone():
            cursor_temp.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_PARAMS["database"])))
            print(f"{Fore.GREEN}✅ Database '{DB_PARAMS['database']}' created")
        
        cursor_temp.close()
        conn_temp.close()

        # Connect to 'bloom' database
        conn = psycopg2.connect(**DB_PARAMS)
        conn.autocommit = True
        cursor = conn.cursor()

        print(f"{Fore.CYAN}🏗️  Creating database schema...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL UNIQUE,
                full_name VARCHAR(100),
                age INTEGER CHECK (age >= 0 AND age <= 150),
                city VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
        ]
        for idx in indexes:
            cursor.execute(idx)
            
        print(f"{Fore.GREEN}✅ Schema setup complete.")
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"{Fore.RED}❌ Database error: {e}")

def generate_fake_users(num_users=100000):
    fake = Faker()
    Faker.seed(42)
    users = []
    print(f"\n{Fore.CYAN}📝 Generating {num_users:,} fake users...")
    
    for _ in tqdm(range(num_users), desc="Generating"):
        first_name = fake.first_name()
        last_name = fake.last_name()
        unique_num = random.randint(1, 9999999)
        username = f"{first_name.lower()}.{last_name.lower()}{unique_num}"
        email = f"{username}@{fake.free_email_domain()}"
        users.append((username, email, f"{first_name} {last_name}", random.randint(18, 80), fake.city()))
    
    return users

def insert_users_bulk(users, batch_size=10000):
    from psycopg2.extras import execute_values
    print(f"\n{Fore.CYAN}💾 Inserting {len(users):,} users...")
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        query = "INSERT INTO users (username, email, full_name, age, city) VALUES %s ON CONFLICT DO NOTHING"
        
        for i in tqdm(range(0, len(users), batch_size), desc="Inserting"):
            batch = users[i : i + batch_size]
            execute_values(cursor, query, batch)
            conn.commit()
            
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count
    except Exception as e:
        print(f"{Fore.RED}❌ Insertion error: {e}")
        return 0

def interactive_query_system():
    print("\n" + "="*60)
    print(f"{Fore.MAGENTA}{Style.BRIGHT}   BLOOM FILTER INTERACTIVE QUERY SYSTEM")
    print("="*60)
    
    try:
        system = UserDatabaseWithBloom(DB_PARAMS)
    except Exception as e:
        print(f"{Fore.RED}❌ Failed to initialize system: {e}")
        return

    print(f"\n{Fore.YELLOW}Instructions: Enter a username to check if it exists.")
    print(f"{Fore.YELLOW}Enter 'exit' to quit or 'rand' for a random existing user.\n")

    while True:
        try:
            query = input(f"{Fore.WHITE}Username > {Style.RESET_ALL}").strip()
            
            if query.lower() == 'exit':
                break
            
            if query.lower() == 'rand':
                system.cursor.execute("SELECT username FROM users ORDER BY RANDOM() LIMIT 1")
                res = system.cursor.fetchone()
                if res:
                    query = res[0]
                    print(f"{Fore.BLUE}Randomly selected: {query}")
                else:
                    print(f"{Fore.RED}No users in DB.")
                    continue

            if not query:
                continue

            result = system.query_username(query)
            
            print(f"\n{Fore.WHITE}{'-'*40}")
            print(f"Status: {Fore.YELLOW if 'False' in result['status'] else (Fore.GREEN if 'Confirmed' in result['status'] else Fore.RED)}{result['status']}")
            print(f"Bloom Result: {'MAYBE FOUND' if result['bloom_result'] else 'DEFINITELY NOT FOUND'}")
            print(f"Bloom Time: {Fore.CYAN}{result['bloom_time_ms']:.4f} ms")
            
            if result['db_time_ms'] is not None:
                print(f"DB Time: {Fore.CYAN}{result['db_time_ms']:.4f} ms")
                total_time = result['bloom_time_ms'] + result['db_time_ms']
                print(f"Total Time: {total_time:.4f} ms")
            else:
                print(f"DB Query: {Fore.GREEN}SKIPPED (Efficiency Gained!)")
            
            print(f"{Fore.WHITE}{'-'*40}\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{Fore.RED}Error: {e}")

    system.close()
    print(f"\n{Fore.MAGENTA}👋 System closed.")

if __name__ == "__main__":
    print(f"{Fore.MAGENTA}{Style.BRIGHT}🚀 Bloom Filter Demo - Initializing...")
    
    # setup_database()
    
    # Check if we need to seed data
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    if user_count < 10000:
        print(f"{Fore.YELLOW}Database looks empty ({user_count} users). Seeding data...")
        users = generate_fake_users(100000)
        user_count = insert_users_bulk(users)
    
    print(f"{Fore.GREEN}✅ Database ready with {user_count:,} users.")
    
    interactive_query_system()
