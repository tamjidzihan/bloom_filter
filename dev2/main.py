import time

import psycopg2
from psycopg2 import sql
import os
from faker import Faker
import random
from tqdm import tqdm

# Connection parameters (using default postgres superuser)
DB_PARAMS = {
    "host": "localhost",
    "port": "5432",
    "database": "bloom",
    "user": "postgres",
    "password": "postgres",
}


def setup_database():
    """Run the SQL setup script to create database and tables"""
    try:
        # Connect to default postgres database
        print("📡 Connecting to PostgreSQL...")
        conn = psycopg2.connect(**DB_PARAMS)  # type: ignore
        conn.autocommit = True  # Important for CREATE DATABASE
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DB_PARAMS["database"],)
        )
        exists = cursor.fetchone()

        if not exists:
            # Create database
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(DB_PARAMS["database"])
                )
            )
            print(f"✅ Database '{DB_PARAMS['database']}' created")
        else:
            print(f"📁 Database '{DB_PARAMS['database']}' already exists")

        cursor.close()
        conn.close()

        # Connect to the new database
        conn = psycopg2.connect(**DB_PARAMS)  # type: ignore
        conn.autocommit = False  # Turn off autocommit for transaction management
        cursor = conn.cursor()

        print("\n🏗️  Creating database schema...")

        # Create users table
        create_users_table = """
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
        """
        cursor.execute(create_users_table)
        print("  ✅ Created users table")

        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_city ON users(city)",
            "CREATE INDEX IF NOT EXISTS idx_users_age ON users(age)",
            "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_users_city_age ON users(city, age)",
        ]

        for idx in indexes:
            cursor.execute(idx)
        print("  ✅ Created indexes")

        # Create updated_at trigger function
        create_trigger_function = """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
        cursor.execute(create_trigger_function)

        # Create trigger
        create_trigger = """
        DROP TRIGGER IF EXISTS update_users_updated_at ON users;
        CREATE TRIGGER update_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column()
        """
        cursor.execute(create_trigger)
        print("  ✅ Created update trigger")

        # Create batch insert function
        create_batch_insert = """
        CREATE OR REPLACE FUNCTION insert_users_batch(
            usernames TEXT[],
            emails TEXT[],
            full_names TEXT[],
            ages INTEGER[],
            cities TEXT[]
        )
        RETURNS INTEGER AS $$
        DECLARE
            i INTEGER;
            inserted_count INTEGER := 0;
        BEGIN
            FOR i IN 1..array_length(usernames, 1) LOOP
                BEGIN
                    INSERT INTO users (username, email, full_name, age, city)
                    VALUES (usernames[i], emails[i], full_names[i], ages[i], cities[i]);
                    inserted_count := inserted_count + 1;
                EXCEPTION WHEN unique_violation THEN
                    -- Skip duplicate entries
                    CONTINUE;
                END;
            END LOOP;
            RETURN inserted_count;
        END;
        $$ LANGUAGE plpgsql
        """
        cursor.execute(create_batch_insert)
        print("  ✅ Created batch insert function")

        # Create search function
        create_search_function = """
        CREATE OR REPLACE FUNCTION search_users(search_pattern TEXT)
        RETURNS TABLE(
            id INTEGER,
            username VARCHAR,
            email VARCHAR,
            full_name VARCHAR,
            city VARCHAR
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT u.id, u.username, u.email, u.full_name, u.city
            FROM users u
            WHERE u.username ILIKE '%' || search_pattern || '%'
               OR u.full_name ILIKE '%' || search_pattern || '%'
            ORDER BY u.username
            LIMIT 100;
        END;
        $$ LANGUAGE plpgsql
        """
        cursor.execute(create_search_function)
        print("  ✅ Created search function")

        # Create statistics function
        create_stats_function = """
        CREATE OR REPLACE FUNCTION get_user_statistics()
        RETURNS TABLE(
            total_users BIGINT,
            average_age NUMERIC,
            unique_cities BIGINT,
            max_age INTEGER,
            min_age INTEGER
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                COUNT(*)::BIGINT,
                AVG(age)::NUMERIC(10,2),
                COUNT(DISTINCT city)::BIGINT,
                MAX(age)::INTEGER,
                MIN(age)::INTEGER
            FROM users;
        END;
        $$ LANGUAGE plpgsql
        """
        cursor.execute(create_stats_function)
        print("  ✅ Created statistics function")

        # Add table comments
        comments = [
            "COMMENT ON TABLE users IS 'Stores user information for the application'",
            "COMMENT ON COLUMN users.id IS 'Unique identifier for each user'",
            "COMMENT ON COLUMN users.username IS 'Unique username for login'",
            "COMMENT ON COLUMN users.email IS 'Unique email address'",
            "COMMENT ON COLUMN users.full_name IS 'User''s full name'",
            "COMMENT ON COLUMN users.age IS 'User''s age (0-150)'",
            "COMMENT ON COLUMN users.city IS 'City of residence'",
            "COMMENT ON COLUMN users.created_at IS 'Timestamp when user was created'",
            "COMMENT ON COLUMN users.updated_at IS 'Timestamp when user was last updated'",
        ]

        for comment in comments:
            try:
                cursor.execute(comment)
            except Exception:
                pass  # Comments are optional
        print("  ✅ Added documentation comments")

        # Commit all changes
        conn.commit()
        print("\n✅ Database schema setup completed successfully!")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if "conn" in locals() and conn:  # type: ignore
            conn.rollback()
        print("\nPlease ensure:")
        print("  1. PostgreSQL is running")
        print("  2. Connection parameters are correct")
        print("  3. You have proper permissions")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if "conn" in locals() and conn:  # type: ignore
            conn.rollback()


def generate_fake_users(num_users=1000000, batch_size=50000):
    """Generate fake user data using Faker"""
    fake = Faker()
    Faker.seed(42)  # For reproducible data

    users = []
    print(f"\n📝 Generating {num_users:,} fake users...")

    cities = [
        "New York",
        "Los Angeles",
        "Chicago",
        "Houston",
        "Phoenix",
        "Philadelphia",
        "San Antonio",
        "San Diego",
        "Dallas",
        "Austin",
        "San Jose",
        "Fort Worth",
        "Jacksonville",
        "Columbus",
        "Charlotte",
        "San Francisco",
        "Indianapolis",
        "Seattle",
        "Denver",
        "Boston",
        "El Paso",
        "Detroit",
        "Nashville",
        "Portland",
        "Memphis",
        "Oklahoma City",
        "Las Vegas",
        "Louisville",
        "Baltimore",
        "Milwaukee",
    ]

    start_time = time.time()

    for i in tqdm(range(num_users), desc="Generating users"):
        # Generate unique username (using first name + last name + number to avoid collisions)
        # Generate unique username/email
        first_name = fake.first_name()
        last_name = fake.last_name()

        unique_number = random.randint(1, 999999)

        username = f"{first_name.lower()}.{last_name.lower()}{unique_number}"

        email = (
            f"{first_name.lower()}."
            f"{last_name.lower()}"
            f"{unique_number}@{fake.free_email_domain()}"
        )

        # Generate full name
        full_name = f"{first_name} {last_name}"

        # Generate age (18-80)
        age = random.randint(18, 80)

        # Generate city
        city = random.choice(cities)

        users.append((username, email, full_name, age, city))

    elapsed = time.time() - start_time
    print(f"✅ Generated {num_users:,} users in {elapsed:.2f} seconds")
    print(f"   Rate: {num_users/elapsed:.0f} users/second")

    return users


def insert_users_bulk_postgresql(users, batch_size=50000):
    """Insert users in bulk using PostgreSQL's execute_values"""
    from psycopg2.extras import execute_values

    print(f"\n💾 Inserting {len(users):,} users into database...")

    try:
        conn = psycopg2.connect(**DB_PARAMS)  # type: ignore
        cursor = conn.cursor()

        # Disable triggers and indexes temporarily for faster insertion
        cursor.execute("SET session_replication_role = 'replica'")

        start_time = time.time()

        insert_query = """
        INSERT INTO users (username, email, full_name, age, city) 
        VALUES %s
        ON CONFLICT DO NOTHING
        """

        total_inserted = 0

        # Insert in batches
        for i in tqdm(range(0, len(users), batch_size), desc="Inserting batches"):
            batch = users[i : i + batch_size]
            execute_values(cursor, insert_query, batch)
            conn.commit()
            total_inserted += len(batch)

        # Re-enable triggers and indexes
        cursor.execute("SET session_replication_role = 'origin'")

        elapsed = time.time() - start_time
        print(f"\n✅ Inserted {total_inserted:,} users in {elapsed:.2f} seconds")
        print(f"   Rate: {total_inserted/elapsed:.0f} users/second")

        # Analyze table to update statistics
        cursor.execute("ANALYZE users")
        conn.commit()

        cursor.close()
        conn.close()

        return total_inserted

    except psycopg2.Error as e:
        print(f"❌ Database error during insertion: {e}")
        return 0


def test_bloom_filter_performance(sample_size=1000):
    """Test bloom filter queries with sample data"""
    print("\n🔍 Testing Bloom Filter Performance...")

    try:
        conn = psycopg2.connect(**DB_PARAMS)  # type: ignore
        cursor = conn.cursor()

        # Test exact matches
        cursor.execute("SELECT username FROM users LIMIT 5")
        sample_usernames = [row[0] for row in cursor.fetchall()]

        print(f"  Testing with {sample_size} random username lookups...")

        # Get random usernames for testing
        cursor.execute(
            f"SELECT username FROM users ORDER BY RANDOM() LIMIT {sample_size}"
        )
        test_usernames = [row[0] for row in cursor.fetchall()]

        start_time = time.time()

        # Simulate bloom filter checks (existence checks)
        found_count = 0
        for username in test_usernames:
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM users WHERE username = %s)", (username,)
            )
            if cursor.fetchone()[0]:
                found_count += 1

        elapsed = time.time() - start_time

        print(f"  ✅ {found_count}/{sample_size} usernames found")
        print(f"  ⚡ Average lookup time: {elapsed/sample_size*1000:.3f} ms")
        print(f"  📊 Total time for {sample_size} lookups: {elapsed:.3f} seconds")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"  ❌ Performance test failed: {e}")


if __name__ == "__main__":
    print("🚀 PostgreSQL Database Setup with 100,000 Users")
    print("=" * 60)

    # Run setup
    # setup_database()

    # Generate fake users
    num_users = 1000000
    users = generate_fake_users(num_users)

    # Choose insertion method
    print("\n" + "=" * 60)
    print("💾 Choose insertion method:")
    print("  1. Bulk insert using execute_values (faster, recommended)")
    print("  2. Stored procedure batch insert")

    total_inserted = insert_users_bulk_postgresql(users, batch_size=10000)

    if total_inserted > 0:
        test_bloom_filter_performance(min(1000, total_inserted))

    print("\n" + "=" * 60)
    print("✨ Setup complete! You can now use the database.")
    print(f"📝 Connection string for {DB_PARAMS['user']}:")
    print(
        f"   postgresql://{DB_PARAMS['user']}:{DB_PARAMS['password']}@localhost:5432/{DB_PARAMS["database"]}"
    )
    print(f"\n📊 Total users in database: {total_inserted:,}")
