"""Generate 6 months of realistic demo data for a family of four.

Spending on dining out and shopping slowly creeps up, and there are a few big
one-off purchases, so the ML models have real patterns to find.
"""

import random
from datetime import date, timedelta

# (description, category, min, max, times per month, member)
MONTHLY_EXPENSES = [
    ("House rent", "Housing", 18000, 18000, 1, "Family"),
    ("Electricity bill", "Utilities", 1800, 3200, 1, "Family"),
    ("Water bill", "Utilities", 300, 450, 1, "Family"),
    ("LPG cylinder", "Utilities", 1100, 1100, 1, "Family"),
    ("Broadband internet", "Utilities", 799, 799, 1, "Family"),
    ("Mobile recharge", "Utilities", 299, 599, 2, "Family"),
    ("DMart groceries", "Groceries", 2500, 4500, 3, "Mom"),
    ("Milk and dairy", "Groceries", 1500, 1800, 1, "Mom"),
    ("Vegetable market", "Groceries", 300, 700, 4, "Mom"),
    ("Petrol", "Transport", 1200, 2000, 2, "Dad"),
    ("Metro card recharge", "Transport", 500, 500, 1, "Riya"),
    ("School fee", "Education", 6500, 6500, 1, "Aarav"),
    ("Tuition classes", "Education", 2500, 2500, 1, "Aarav"),
    ("LIC premium", "Insurance", 2200, 2200, 1, "Dad"),
    ("Car loan EMI", "Loan EMI", 7500, 7500, 1, "Dad"),
    ("SIP mutual fund", "Savings & Investments", 5000, 5000, 1, "Dad"),
    ("Netflix subscription", "Subscriptions", 649, 649, 1, "Family"),
    ("Spotify premium", "Subscriptions", 119, 119, 1, "Riya"),
    ("Prime video", "Subscriptions", 299, 299, 1, "Family"),
    ("Gym membership", "Subscriptions", 1500, 1500, 1, "Dad"),
    ("Swiggy order", "Dining Out", 250, 750, 6, "Riya"),
    ("Zomato dinner", "Dining Out", 400, 1100, 3, "Family"),
    ("Starbucks coffee", "Dining Out", 300, 450, 3, "Riya"),
    ("Amazon shopping", "Shopping", 500, 3500, 2, "Mom"),
    ("Myntra clothes", "Shopping", 900, 2500, 1, "Riya"),
    ("PVR movie tickets", "Entertainment", 600, 1200, 1, "Family"),
    ("Apollo pharmacy", "Healthcare", 300, 1500, 1, "Mom"),
    ("Salon haircut", "Personal Care", 300, 900, 1, "Mom"),
]
ONE_OFFS = [  # (month offset from start, description, category, amount, member)
    (1, "Doctor consultation and lab test", "Healthcare", 3500, "Dad"),
    (2, "Birthday gift for cousin", "Gifts & Donations", 2500, "Mom"),
    (3, "Goa trip hotel booking", "Travel", 14000, "Family"),
    (3, "Flight tickets Goa", "Travel", 18000, "Family"),
    (4, "Diwali shopping Flipkart", "Shopping", 9500, "Family"),
    (4, "Temple donation", "Gifts & Donations", 1100, "Mom"),
    (5, "Laptop purchase Croma", "Shopping", 42000, "Riya"),
    (5, "Car service", "Transport", 4800, "Dad"),
]
CREEPING = ("Swiggy", "Zomato", "Starbucks", "Amazon", "Myntra")


def _month_starts(n: int, today: date) -> list[date]:
    first = today.replace(day=1)
    out = []
    for _ in range(n):
        out.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def generate(months: int = 6, seed: int = 7, today: date | None = None) -> list[dict]:
    rng = random.Random(seed)
    today = today or date.today()
    rows = []

    def add(d, desc, category, amount, type_, member):
        rows.append({"date": d.isoformat(), "description": desc, "amount": float(round(amount)),
                     "type": type_, "category": category, "member": member, "source": "demo"})

    for i, start in enumerate(_month_starts(months, today)):
        last_day = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if start.year == today.year and start.month == today.month:
            last_day = today
        span = (last_day - start).days
        day = lambda: start + timedelta(days=rng.randint(0, span))

        add(start, "Salary - Dad", "Salary", 72000, "income", "Dad")
        add(start + timedelta(days=min(4, span)), "Salary - Mom", "Salary", 38000, "income", "Mom")
        if i % 2 == 1:
            add(day(), "Freelance design project", "Freelance", rng.choice([6000, 8000, 12000]), "income", "Mom")
        if i == months - 1:
            add(day(), "FD interest", "Interest & Dividends", 1850, "income", "Dad")

        creep = 1 + 0.12 * i
        for desc, category, lo, hi, times, member in MONTHLY_EXPENSES:
            count = times + (1 if desc.startswith(("Swiggy", "Zomato")) and i >= 3 else 0)
            for _ in range(count):
                amount = rng.uniform(lo, hi) * (creep if desc.startswith(CREEPING) else 1)
                when = day() if times > 1 else start + timedelta(days=min(rng.randint(1, 9), span))
                add(when, desc, category, amount, "expense", member)

        for offset, desc, category, amount, member in ONE_OFFS:
            if offset == i:
                add(day(), desc, category, amount, "expense", member)

    return rows
