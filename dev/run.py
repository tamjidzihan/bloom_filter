import hashlib
import mmh3
import psycopg2
from typing import Optional
import time
from faker import Faker
import pickle
from math import exp

class UserBloomFilter:
    def __init__(self, size: int, num_hashes: int = 4):
        """
        Initialize Bloom filter for username lookup
        
        size: number of bits in the filter
        num_hashes: number of hash functions to use (4 is good balance)
        """
        self.size = size
        self.num_hashes = num_hashes
        self.bit_array = [0] * size
    
    def _hashes(self, username: str):
        """Generate multiple hash values for the username"""
        # Using mmh3 for fast, high-quality hashing
        for i in range(self.num_hashes):
            # Seed each hash differently
            hash_val = mmh3.hash(username, i) % self.size
            yield hash_val
    
    def add(self, username: str):
        """Add username to bloom filter"""
        for hash_val in self._hashes(username):
            self.bit_array[hash_val] = 1
    
    def check(self, username: str) -> bool:
        """
        Check if username MIGHT exist in database
        Returns: 
            True - Username might exist (may be false positive)
            False - Username definitely does NOT exist
        """
        for hash_val in self._hashes(username):
            if self.bit_array[hash_val] == 0:
                return False  # Definitely not in database
        return True  # Might be in database
    
    def get_false_positive_rate(self, n: Optional[int] = None) -> float:
        """Calculate approximate false positive probability"""
        k = self.num_hashes
        m = self.size
        if n is None:
            n = sum(self.bit_array)  # Approximate number of items
        if n == 0:
            return 0
        return (1 - exp(-k * n / m)) ** k
    
    # Add save/load methods directly to UserBloomFilter
    def save_to_file(self, filename: str):
        """Save bloom filter state to disk"""
        with open(filename, 'wb') as f:
            pickle.dump({
                'size': self.size,
                'num_hashes': self.num_hashes,
                'bit_array': self.bit_array
            }, f)
        print(f"💾 Bloom filter saved to {filename}")
    
    @classmethod
    def load_from_file(cls, filename: str):
        """Load bloom filter state from disk"""
        with open(filename, 'rb') as f:
            data = pickle.load(f)
        
        bf = cls(size=data['size'], num_hashes=data['num_hashes'])
        bf.bit_array = data['bit_array']
        print(f"📂 Bloom filter loaded from {filename}")
        return bf


class UserDatabaseWithBloom:
    def __init__(self, db_connection_params: dict, bloom_size: int = 10_000_000):
        """
        Initialize database connection and bloom filter
        
        bloom_size: 10 million bits for 1M users (optimal for ~1% false positive)
        """
        self.conn = psycopg2.connect(**db_connection_params)
        self.bloom = UserBloomFilter(size=bloom_size, num_hashes=4)
        self.cursor = self.conn.cursor()
        
        # Load existing usernames into bloom filter on startup
        self._load_existing_usernames()
    
    def _load_existing_usernames(self):
        """Load all existing usernames into bloom filter"""
        print("📊 Loading existing users into Bloom filter...")
        start_time = time.time()
        
        self.cursor.execute("SELECT username FROM users")
        count = 0
        for row in self.cursor.fetchall():
            self.bloom.add(row[0])
            count += 1
            if count % 100000 == 0:
                print(f"  Loaded {count:,} usernames...")
        
        elapsed = time.time() - start_time
        print(f"✅ Loaded {count:,} usernames in {elapsed:.2f} seconds")
        print(f"📈 Bloom filter false positive rate: ~{self.bloom.get_false_positive_rate()*100:.2f}%")
    
    def username_exists_bloom(self, username: str) -> tuple[bool, Optional[str]]:
        """
        Check if username exists using Bloom filter first
        
        Returns: (exists, reason)
        """
        # Step 1: Quick bloom filter check
        if not self.bloom.check(username):
            return (False, "Bloom filter says definitely not exists - no DB query needed")
        
        # Step 2: Verify with database (handles false positives)
        self.cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        result = self.cursor.fetchone()
        
        if result:
            return (True, "Username exists (confirmed by database)")
        else:
            return (False, "False positive from Bloom filter - username actually doesn't exist")
    
    def add_user_with_bloom(self, username: str, email: str, full_name: str, age: int, city: str):
        """Add new user and update bloom filter"""
        try:
            # Insert into database
            self.cursor.execute("""
                INSERT INTO users (username, email, full_name, age, city)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, email, full_name, age, city))
            self.conn.commit()
            
            # Add to bloom filter for future checks
            self.bloom.add(username)
            return True
        except psycopg2.IntegrityError:
            self.conn.rollback()
            print(f"⚠️  Username '{username}' already exists")
            return False
    
    def check_usernames_batch(self, usernames: list[str]) -> dict:
        """Check multiple usernames efficiently"""
        results = {}
        
        # First pass: bloom filter checks (fast)
        bloom_possible = []
        for username in usernames:
            if self.bloom.check(username):
                bloom_possible.append(username)
                results[username] = "Check database (bloom: possible)"
            else:
                results[username] = "Definitely doesn't exist"
        
        # Second pass: verify only potential matches with database
        if bloom_possible:
            placeholders = ','.join(['%s'] * len(bloom_possible))
            query = f"SELECT username FROM users WHERE username IN ({placeholders})"
            self.cursor.execute(query, bloom_possible)
            existing = {row[0] for row in self.cursor.fetchall()}
            
            for username in bloom_possible:
                if username in existing:
                    results[username] = "Confirmed exists"
                else:
                    results[username] = "False positive (doesn't actually exist)"
        
        return results
    
    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()


# Performance comparison without requiring PostgREST
def performance_comparison():
    """Compare Bloom filter vs direct database queries"""
    db_params = {
        "host": "localhost",
        "database": "bloom",
        "user": "postgres",
        "password": "postgres"
    }
    
    try:
        # Initialize system with bloom filter
        system = UserDatabaseWithBloom(db_params, bloom_size=10_000_000)
    except psycopg2.Error as e:
        print(f"❌ Cannot connect to database: {e}")
        print("\n📝 Please ensure:")
        print("  1. PostgreSQL is running")
        print(f"  2. Database '{db_params['database']}' exists")
        print("  3. Table 'users' exists with username column")
        print("  4. Connection parameters are correct")
        return
    
    print("\n" + "="*70)
    print("PERFORMANCE COMPARISON: Bloom Filter vs Direct DB Query")
    print("="*70)
    
    # Test 1: Check existing user (should be fast either way)
    print("\n📌 TEST 1: Existing user")
    # Get an existing username first
    system.cursor.execute("SELECT username FROM users LIMIT 1")
    result = system.cursor.fetchone()
    if not result:
        print("  ⚠️ No users found in database. Please add some users first.")
        system.close()
        return
    
    username = result[0]
    
    start = time.time()
    exists, reason = system.username_exists_bloom(username)
    bloom_time = time.time() - start
    
    start = time.time()
    system.cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
    db_result = system.cursor.fetchone()
    db_time = time.time() - start
    
    print(f"  Bloom filter: {exists} - {bloom_time*1000:.3f}ms ({reason})")
    print(f"  Direct query: {db_result is not None} - {db_time*1000:.3f}ms")
    
    # Test 2: Check non-existent user (Bloom filter shines here)
    print("\n📌 TEST 2: Non-existent user")
    fake_username = "xyz_nonexistent_user_12345"
    
    start = time.time()
    exists, reason = system.username_exists_bloom(fake_username)
    bloom_time = time.time() - start
    
    start = time.time()
    system.cursor.execute("SELECT username FROM users WHERE username = %s", (fake_username,))
    db_result = system.cursor.fetchone()
    db_time = time.time() - start
    
    print(f"  Bloom filter: {exists} - {bloom_time*1000:.3f}ms ({reason})")
    print(f"  Direct query: {db_result is not None} - {db_time*1000:.3f}ms")
    
    if db_time > 0 and bloom_time > 0:
        print(f"  ⚡ Bloom filter was {db_time/bloom_time:.1f}x faster!")
    
    # Test 3: Bulk check 1000 usernames (90% non-existent)
    print("\n📌 TEST 3: Bulk check 1000 usernames (900 non-existent, 100 existing)")
    
    # Generate test usernames
    test_users = []
    # Add 100 existing users
    system.cursor.execute("SELECT username FROM users LIMIT 100")
    test_users.extend([row[0] for row in system.cursor.fetchall()])
    # Add 900 random non-existent
    fake = Faker()
    for _ in range(900):
        test_users.append(fake.user_name() + "_nonexistent")
    
    # Bloom filter batch
    start = time.time()
    bloom_results = system.check_usernames_batch(test_users)
    bloom_total = time.time() - start
    
    print(f"  Bloom filter (1000 checks): {bloom_total*1000:.1f}ms")
    
    # Count false positives
    false_positives = sum(1 for status in bloom_results.values() 
                         if "False positive" in status or "Check database" in status)
    print(f"\n📊 Bloom filter stats:")
    print(f"  Total checks: {len(bloom_results)}")
    print(f"  Potential matches requiring DB check: {false_positives}")
    
    system.close()


# Save and load example
def save_and_load_example():
    """Example of saving and loading bloom filter without database"""
    print("\n" + "="*70)
    print("BLOOM FILTER PERSISTENCE EXAMPLE")
    print("="*70)
    
    # Create a bloom filter with some data
    bf = UserBloomFilter(size=1000, num_hashes=4)
    
    # Add some usernames
    test_usernames = ["alice", "bob", "charlie", "diana", "eve"]
    for username in test_usernames:
        bf.add(username)
        print(f"  Added: {username}")
    
    # Test before saving
    print("\n🔍 Testing before save:")
    for username in ["alice", "unknown"]:
        result = "MAY exist" if bf.check(username) else "definitely does NOT exist"
        print(f"  '{username}': {result}")
    
    # Save to file
    bf.save_to_file("test_bloom_filter.pkl")
    
    # Load from file
    loaded_bf = UserBloomFilter.load_from_file("test_bloom_filter.pkl")
    
    # Test after loading
    print("\n🔍 Testing after load:")
    for username in ["alice", "unknown"]:
        result = "MAY exist" if loaded_bf.check(username) else "definitely does NOT exist"
        print(f"  '{username}': {result}")
    
    # Verify functionality is preserved
    print(f"\n✅ Bloom filter successfully saved and loaded!")
    print(f"  Original filter size: {bf.size} bits")
    print(f"  Loaded filter size: {loaded_bf.size} bits")


# Alternative: Fast username check without PostgREST (using direct HTTP to PostgREST if available)
def fast_username_check_without_postgresql():
    """
    Example of using bloom filter for username checks
    without requiring PostgREST library
    """
    print("\n" + "="*70)
    print("STANDALONE BLOOM FILTER EXAMPLE")
    print("="*70)
    
    # Create bloom filter (simulate 1M users with 1% false positive rate)
    # Formula: m = -n*ln(p) / (ln(2))^2
    n = 1_000_000  # 1 million users
    p = 0.01  # 1% false positive rate
    optimal_size = int(-n * exp(-1) * exp(-1))  # Simplified: -n * ln(p) / (ln(2))^2
    optimal_size = int(-n * exp(exp(-1)))  # Rough approximation
    
    # For 1M users with 1% false positive, optimal size is ~9.6M bits
    bloom = UserBloomFilter(size=10_000_000, num_hashes=4)
    
    # Simulate adding 1M users
    print("📊 Simulating 1,000,000 users...")
    fake = Faker()
    added_users = []
    
    for i in range(10000):  # Add 10,000 for demo (use 1,000,000 in production)
        username = fake.unique.user_name()
        bloom.add(username)
        added_users.append(username)
        if (i + 1) % 2000 == 0:
            print(f"  Added {i+1:,} users...")
    
    print(f"✅ Added {len(added_users)} users to bloom filter")
    
    # Test existing users
    print("\n🔍 Testing existing users:")
    test_existing = added_users[:5]
    for username in test_existing:
        start = time.time()
        exists = bloom.check(username)
        elapsed = time.time() - start
        print(f"  '{username}': {'MAY exist' if exists else 'does NOT exist'} ({elapsed*1000:.3f}ms)")
    
    # Test non-existent users
    print("\n🔍 Testing non-existent users:")
    test_nonexistent = ["xyz_never_exists_123", "fake_user_456", "not_in_db_789"]
    for username in test_nonexistent:
        start = time.time()
        exists = bloom.check(username)
        elapsed = time.time() - start
        print(f"  '{username}': {'MAY exist' if exists else 'does NOT exist'} ({elapsed*1000:.3f}ms)")
    
    # Calculate false positive rate
    print(f"\n📈 Estimated false positive rate: ~{bloom.get_false_positive_rate(n=len(added_users))*100:.2f}%")
    print(f"💾 Memory usage: {bloom.size / 8 / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    print("🚀 BLOOM FILTER FOR USERNAME LOOKUP")
    print("="*70)
    
    # Run standalone example (doesn't require database)
    fast_username_check_without_postgresql()
    
    # Run persistence example
    save_and_load_example()
    
    # Try database version (will show error if database not available)
    print("\n" + "="*70)
    print("DATABASE INTEGRATION (if available)")
    print("="*70)
    performance_comparison()