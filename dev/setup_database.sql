-- setup_database.sql
-- Complete PostgreSQL setup for user database with Bloom filter

-- 1. Create the database (if not exists)
CREATE DATABASE userdb;

-- 2. Connect to the database
\c userdb;

-- 3. Create the users table with proper structure
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(100),
    age INTEGER CHECK (age >= 0 AND age <= 150),
    city VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_city ON users(city);
CREATE INDEX IF NOT EXISTS idx_users_age ON users(age);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- 5. Create a composite index for common queries
CREATE INDEX IF NOT EXISTS idx_users_city_age ON users(city, age);

-- 6. Create a function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 7. Create trigger to update updated_at on row update
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 8. Create a view for active users (example)
CREATE OR REPLACE VIEW active_users AS
SELECT id, username, email, full_name, city, created_at
FROM users
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';

-- 9. Create a stored procedure for batch user insertion
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
            VALUES (
                usernames[i],
                emails[i],
                full_names[i],
                ages[i],
                cities[i]
            );
            inserted_count := inserted_count + 1;
        EXCEPTION WHEN unique_violation THEN
            -- Skip duplicate entries
            CONTINUE;
        END;
    END LOOP;
    RETURN inserted_count;
END;
$$ LANGUAGE plpgsql;

-- 10. Create a function to get user statistics
CREATE OR REPLACE FUNCTION get_user_statistics()
RETURNS TABLE(
    total_users BIGINT,
    avg_age NUMERIC,
    unique_cities BIGINT,
    oldest_user INTEGER,
    youngest_user INTEGER
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
$$ LANGUAGE plpgsql;

-- 11. Create a function to search users by username pattern
CREATE OR REPLACE FUNCTION search_users_by_pattern(search_pattern TEXT)
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
    ORDER BY u.username
    LIMIT 100;
END;
$$ LANGUAGE plpgsql;

-- 12. Grant permissions to api_user
-- Create the api_user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'api_user') THEN
        CREATE USER api_user WITH PASSWORD 'secure_password';
    END IF;
END
$$;

-- Grant privileges
GRANT CONNECT ON DATABASE userdb TO api_user;
GRANT USAGE ON SCHEMA public TO api_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO api_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO api_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO api_user;

-- 13. Create a materialized view for city statistics (for better performance)
CREATE MATERIALIZED VIEW IF NOT EXISTS city_stats AS
SELECT 
    city,
    COUNT(*) as user_count,
    AVG(age) as avg_age,
    MIN(age) as min_age,
    MAX(age) as max_age
FROM users
GROUP BY city;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_city_stats_city ON city_stats(city);

-- 14. Create a function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_city_stats()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY city_stats;
END;
$$ LANGUAGE plpgsql;

-- 15. Add table comments for documentation
COMMENT ON TABLE users IS 'Stores user information for the application';
COMMENT ON COLUMN users.id IS 'Unique identifier for each user';
COMMENT ON COLUMN users.username IS 'Unique username for login';
COMMENT ON COLUMN users.email IS 'Unique email address';
COMMENT ON COLUMN users.full_name IS 'User''s full name';
COMMENT ON COLUMN users.age IS 'User''s age (0-150)';
COMMENT ON COLUMN users.city IS 'City of residence';
COMMENT ON COLUMN users.created_at IS 'Timestamp when user was created';
COMMENT ON COLUMN users.updated_at IS 'Timestamp when user was last updated';

-- 16. Create a partition for better performance with large datasets (optional)
-- Uncomment if you want to partition by created_at month
/*
CREATE TABLE users_partitioned (
    LIKE users INCLUDING ALL
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE users_2024_01 PARTITION OF users_partitioned
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE users_2024_02 PARTITION OF users_partitioned
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- Add more partitions as needed
*/

-- 17. Create a database maintenance function
CREATE OR REPLACE FUNCTION maintenance_users_table()
RETURNS TEXT AS $$
DECLARE
    table_size TEXT;
    index_size TEXT;
    fragmentation FLOAT;
BEGIN
    -- Get table size
    SELECT pg_size_pretty(pg_total_relation_size('users')) INTO table_size;
    
    -- Get index size
    SELECT pg_size_pretty(pg_indexes_size('users')) INTO index_size;
    
    -- Analyze table to update statistics
    ANALYZE users;
    
    -- Reindex if fragmentation is high (example check)
    -- This would need a more sophisticated check in production
    
    RETURN format('Maintenance completed. Table size: %s, Index size: %s', 
                  table_size, index_size);
END;
$$ LANGUAGE plpgsql;

-- 18. Create audit log table (optional, for tracking changes)
CREATE TABLE IF NOT EXISTS users_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR(10),
    old_data JSONB,
    new_data JSONB,
    changed_by VARCHAR(50),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create trigger function for audit logging
CREATE OR REPLACE FUNCTION log_user_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO users_audit_log (user_id, action, new_data, changed_by)
        VALUES (NEW.id, 'INSERT', to_jsonb(NEW), current_user);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO users_audit_log (user_id, action, old_data, new_data, changed_by)
        VALUES (NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW), current_user);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO users_audit_log (user_id, action, old_data, changed_by)
        VALUES (OLD.id, 'DELETE', to_jsonb(OLD), current_user);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Uncomment to enable audit logging (may impact performance)
-- CREATE TRIGGER audit_users_changes
--     AFTER INSERT OR UPDATE OR DELETE ON users
--     FOR EACH ROW EXECUTE FUNCTION log_user_changes();

-- Display setup completion message
DO $$
BEGIN
    RAISE NOTICE '✅ Database setup completed successfully!';
    RAISE NOTICE '📊 Tables created: users, users_audit_log';
    RAISE NOTICE '🔍 Indexes created for performance optimization';
    RAISE NOTICE '⚡ Functions created for batch operations';
    RAISE NOTICE '👤 User api_user created with appropriate permissions';
END $$;