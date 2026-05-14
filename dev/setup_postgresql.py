import psycopg2
from psycopg2 import sql
import os

def setup_database():
    """Run the SQL setup script to create database and tables"""
    
    # Connection parameters (using default postgres superuser)
    db_params = {
        "host": "localhost",
        "port": "5432",
        "database": "postgres",  # Connect to default postgres database
        "user": "postgres",
        "password": "postgres"
    }
    
    try:
        # Connect to default postgres database
        print("📡 Connecting to PostgreSQL...")
        conn = psycopg2.connect(**db_params)
        conn.autocommit = True  # Important for CREATE DATABASE
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'userdb'")
        exists = cursor.fetchone()
        
        if not exists:
            # Create database
            cursor.execute("CREATE DATABASE userdb")
            print("✅ Database 'userdb' created")
        else:
            print("📁 Database 'userdb' already exists")
        
        cursor.close()
        conn.close()
        
        # Connect to the new database
        db_params["database"] = "userdb"
        conn = psycopg2.connect(**db_params)
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
            "CREATE INDEX IF NOT EXISTS idx_users_city_age ON users(city, age)"
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
        
        # Create or update api_user
        cursor.execute("SELECT 1 FROM pg_user WHERE usename = 'api_user'")
        user_exists = cursor.fetchone()
        
        if not user_exists:
            cursor.execute("CREATE USER api_user WITH PASSWORD 'secure_password'")
            print("  ✅ Created api_user")
        else:
            cursor.execute("ALTER USER api_user WITH PASSWORD 'secure_password'")
            print("  ✅ Updated api_user password")
        
        # Grant privileges
        privileges = [
            "GRANT CONNECT ON DATABASE userdb TO api_user",
            "GRANT USAGE ON SCHEMA public TO api_user",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO api_user",
            "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO api_user",
            "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO api_user"
        ]
        
        for priv in privileges:
            cursor.execute(priv)
        print("  ✅ Granted privileges to api_user")
        
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
            "COMMENT ON COLUMN users.updated_at IS 'Timestamp when user was last updated'"
        ]
        
        for comment in comments:
            try:
                cursor.execute(comment)
            except Exception:
                pass  # Comments are optional
        print("  ✅ Added documentation comments")
        
        # Commit all changes
        conn.commit()
        print("\n✅ Database setup completed successfully!")
        
        cursor.close()
        conn.close()
        
        # Test the connection with api_user
        test_api_user_connection()
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
        print("\nPlease ensure:")
        print("  1. PostgreSQL is running")
        print("  2. Connection parameters are correct")
        print("  3. You have proper permissions")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if conn:
            conn.rollback()

def test_api_user_connection():
    """Test connection with the newly created api_user"""
    print("\n🔐 Testing api_user connection...")
    
    db_params = {
        "host": "localhost",
        "port": "5432",
        "database": "userdb",
        "user": "api_user",
        "password": "secure_password"
    }
    
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        cursor.execute("SELECT current_user, current_database()")
        user, db = cursor.fetchone()
        print(f"  ✅ Successfully connected as '{user}' to database '{db}'")
        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        print(f"  ⚠️  Could not connect as api_user: {e}")
        print("  You may need to restart PostgreSQL or check permissions")

def verify_setup():
    """Verify the database setup"""
    print("\n📊 Database Verification:")
    
    db_params = {
        "host": "localhost",
        "port": "5432",
        "database": "userdb",
        "user": "postgres",
        "password": "postgres"
    }
    
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'users'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            # Get table statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT city) as unique_cities,
                    COUNT(DISTINCT username) as unique_usernames
                FROM users
            """)
            stats = cursor.fetchone()
            
            print(f"  ✅ Table 'users' exists")
            print(f"  📈 Total users: {stats[0]:,}")
            print(f"  🏙️  Unique cities: {stats[1]:,}")
            print(f"  👤 Unique usernames: {stats[2]:,}")
            
            # Check indexes
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'users'
            """)
            indexes = cursor.fetchall()
            print(f"  🔍 Indexes: {len(indexes)} indexes found")
            
            # Check functions
            cursor.execute("""
                SELECT proname 
                FROM pg_proc 
                WHERE proname IN ('insert_users_batch', 'search_users', 'get_user_statistics')
            """)
            functions = cursor.fetchall()
            print(f"  ⚡ Functions: {len(functions)} utility functions found")
            
        else:
            print("  ❌ Table 'users' does not exist")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"  ❌ Verification failed: {e}")

def insert_sample_data():
    """Insert sample data for testing"""
    print("\n📝 Inserting sample data...")
    
    db_params = {
        "host": "localhost",
        "port": "5432",
        "database": "userdb",
        "user": "postgres",
        "password": "postgres"
    }
    
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        # Insert sample users
        sample_users = [
            ("alice", "alice@example.com", "Alice Johnson", 28, "New York"),
            ("bob", "bob@example.com", "Bob Smith", 35, "Los Angeles"),
            ("charlie", "charlie@example.com", "Charlie Brown", 42, "Chicago"),
            ("diana", "diana@example.com", "Diana Prince", 30, "Washington"),
            ("eve", "eve@example.com", "Eve Adams", 25, "Seattle")
        ]
        
        for user in sample_users:
            try:
                cursor.execute("""
                    INSERT INTO users (username, email, full_name, age, city)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                """, user)
            except Exception as e:
                print(f"  ⚠️  Could not insert {user[0]}: {e}")
        
        conn.commit()
        
        # Check how many were inserted
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        print(f"  ✅ Inserted/Verified {count} sample users")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"  ❌ Failed to insert sample data: {e}")

if __name__ == "__main__":
    print("🚀 PostgreSQL Database Setup")
    print("="*50)
    
    # Run setup
    setup_database()
    
    # Insert sample data
    insert_sample_data()
    
    # Verify setup
    verify_setup()
    
    print("\n" + "="*50)
    print("✨ Setup complete! You can now use the database.")
    print("📝 Connection string for api_user:")
    print("   postgresql://api_user:secure_password@localhost:5432/userdb")