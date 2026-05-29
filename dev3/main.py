import random
import time

from faker import Faker
from tqdm import tqdm


def generate_fake_users_data(num_users=10000):
    fake = Faker()
    Faker.seed(42)

    user = []
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
        first_name = fake.first_name()
        last_name = fake.last_name()

        unique_number = random.randint(1, 999999)

        username = f"{first_name.lower()}.{last_name.lower()}{unique_number}"
        email = (
            f"{first_name.lower()}."
            f"{last_name.lower()}"
            f"{unique_number}@{fake.free_email_domain()}"
        )
        full_name = f"{first_name} {last_name}"
        age = random.randint(18, 80)
        city = random.choice(cities)

        user.append((username, email, full_name, age, city))

    elapsed = time.time() - start_time

    print(f"✅ Generated {num_users:,} users in {elapsed:.2f} seconds")
    print(f"   Rate: {num_users/elapsed:.0f} users/second")

    return user


def save_user_data(file_dir, users):
    with open(file_dir, "w") as file:
        print(f"Saving Fake Users Data to: {output_file}")
        for item in users:
            file.write(f"{item}\n")


if __name__ == "__main__":
    fake_users = 10000
    users = generate_fake_users_data(fake_users)
    output_file = "my_list.txt"
    save_user_data(output_file, users)
