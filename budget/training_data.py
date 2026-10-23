"""Built-in training data.

1. CATEGORY_PHRASES - labelled merchant names / phrases for the k-NN categorizer,
   expanded with bank-statement style templates ("UPI ZOMATO", "Zomato payment").
2. expert_necessity_examples() - labelled examples for the ID3 decision tree,
   encoding common personal-finance guidance. Families add their own labels
   on top, which count 3x.
"""

import itertools
import random

CATEGORY_PHRASES = {
    # ---- expenses
    "Housing": ["house rent", "flat rent", "monthly rent", "society maintenance", "apartment maintenance",
                "property tax", "plumber", "electrician", "home repair", "carpenter", "painting house",
                "urban company repair", "pest control", "nobroker rent"],
    "Utilities": ["electricity bill", "bescom", "tata power", "msedcl", "water bill", "lpg cylinder",
                  "indane gas", "piped gas", "broadband internet", "jio fiber", "airtel xstream",
                  "wifi bill", "mobile recharge", "airtel recharge", "jio recharge", "vi postpaid",
                  "phone bill", "dth recharge", "tata play"],
    "Groceries": ["groceries", "supermarket", "vegetables", "fruits", "milk", "dairy", "kirana store",
                  "bigbasket", "blinkit", "zepto", "dmart", "swiggy instamart", "reliance fresh",
                  "more supermarket", "ration", "bakery", "nature basket", "spencers", "jiomart"],
    "Transport": ["petrol", "diesel", "fuel", "indian oil", "hp petrol pump", "bharat petroleum", "uber",
                  "ola cabs", "rapido", "metro card", "bus pass", "train ticket", "parking", "toll",
                  "fastag", "auto rickshaw", "car service", "bike service", "tyre"],
    "Healthcare": ["pharmacy", "medicine", "medical store", "hospital", "doctor consultation", "clinic",
                   "apollo pharmacy", "lab test", "diagnostics", "dental", "1mg", "pharmeasy", "netmeds",
                   "eye checkup", "medplus", "practo"],
    "Education": ["school fee", "tuition fee", "college fee", "online course", "books", "stationery",
                  "exam fee", "coaching classes", "udemy", "coursera", "byjus", "unacademy", "school bus",
                  "uniform"],
    "Insurance": ["insurance", "lic premium", "health insurance", "term insurance", "car insurance",
                  "star health", "hdfc ergo", "policybazaar", "policy renewal"],
    "Loan EMI": ["emi", "car loan emi", "home loan emi", "personal loan", "credit card bill",
                 "bajaj finserv emi", "education loan", "loan repayment"],
    "Dining Out": ["restaurant", "cafe", "coffee", "swiggy", "zomato", "pizza", "burger", "dominos",
                   "mcdonalds", "kfc", "starbucks", "barbeque nation", "dine out", "food delivery",
                   "haldirams", "chai point", "subway", "eatsure"],
    "Shopping": ["amazon", "flipkart", "myntra", "ajio", "meesho", "mall", "clothes", "shoes",
                 "electronics", "croma", "reliance digital", "nykaa", "lifestyle store", "westside",
                 "decathlon", "ikea", "headphones", "mobile phone purchase", "laptop"],
    "Entertainment": ["movie tickets", "cinema", "pvr", "inox", "concert", "bookmyshow", "gaming",
                      "amusement park", "wonderla", "party", "bowling", "steam games", "playstation"],
    "Subscriptions": ["netflix", "prime video", "amazon prime", "hotstar", "spotify", "youtube premium",
                      "subscription", "gym membership", "cult fit", "icloud", "google one", "sonyliv",
                      "zee5", "apple music", "linkedin premium"],
    "Travel": ["flight tickets", "indigo", "air india", "hotel booking", "airbnb", "makemytrip", "irctc",
               "goibibo", "oyo", "trip", "vacation", "holiday package", "cleartrip", "redbus"],
    "Personal Care": ["salon", "haircut", "spa", "beauty parlour", "cosmetics", "grooming", "lakme salon",
                      "barber", "skincare"],
    "Gifts & Donations": ["gift", "donation", "charity", "temple", "birthday gift", "wedding gift",
                          "ngo", "church", "gurudwara", "festival gift"],
    "Savings & Investments": ["sip", "mutual fund", "fixed deposit", "recurring deposit", "ppf", "stocks",
                              "zerodha", "groww", "nps", "gold savings", "savings transfer", "sukanya"],
    # ---- income
    "Salary": ["salary", "salary credit", "payroll", "monthly salary", "wages", "stipend"],
    "Business": ["business income", "sales revenue", "shop income", "customer payment", "invoice payment"],
    "Freelance": ["freelance", "freelance project", "consulting fee", "upwork", "fiverr", "design project",
                  "project payment", "tuition income"],
    "Interest & Dividends": ["interest credit", "fd interest", "savings interest", "dividend",
                             "mutual fund redemption"],
    "Rental Income": ["rent received", "rental income", "tenant rent"],
    "Other Income": ["cashback", "refund", "gift received", "bonus", "reimbursement"],
}

INCOME_CATEGORIES = ["Salary", "Business", "Freelance", "Interest & Dividends", "Rental Income", "Other Income"]
TEMPLATES = ["{p}", "UPI/{P}/{n}", "{p} payment", "POS {P} {city}"]
INCOME_TEMPLATES = ["{p}", "NEFT {P} {n}", "{p} received"]
CITIES = ["BANGALORE", "MUMBAI", "DELHI", "PUNE", "CHENNAI", "HYDERABAD"]


def knn_training_examples(seed: int = 0, with_phrase: bool = False) -> list[tuple]:
    """Returns [(description, type, category)] built from the phrase lists and templates.

    with_phrase=True adds the source phrase as a 4th item (used to hold out whole merchants).
    """
    rng = random.Random(seed)
    out = []
    for category, phrases in CATEGORY_PHRASES.items():
        type_ = "income" if category in INCOME_CATEGORIES else "expense"
        for phrase in phrases:
            for template in (INCOME_TEMPLATES if type_ == "income" else TEMPLATES):
                text = template.format(p=phrase, P=phrase.upper(), n=rng.randint(1000, 99999),
                                       city=rng.choice(CITIES))
                out.append((text, type_, category, phrase) if with_phrase else (text, type_, category))
    return out


# ---------------------------------------------------------------- decision tree
NECESSITY_ATTRIBUTES = ["category_type", "amount_level", "frequency", "day_type", "budget_status"]
NECESSITY_VALUES = {
    "category_type": ["need", "want"],
    "amount_level": ["low", "normal", "high", "very_high"],   # vs. the usual amount in that category
    "frequency": ["rare", "regular", "frequent"],             # purchases in that category this month
    "day_type": ["weekday", "weekend"],
    "budget_status": ["within", "over"],                      # category total vs. budget / usual
}


def expert_label(f: dict) -> str:
    """Personal-finance guidance used to label the built-in training examples."""
    if f["category_type"] == "need":
        return "Unnecessary" if f["amount_level"] == "very_high" and f["budget_status"] == "over" else "Reasonable"
    if f["amount_level"] == "very_high":
        return "Unnecessary"
    if f["frequency"] == "frequent":
        return "Unnecessary"
    if f["budget_status"] == "over" and (f["amount_level"] == "high" or f["day_type"] == "weekend"):
        return "Unnecessary"
    if f["amount_level"] == "high" and f["frequency"] == "regular":
        return "Unnecessary"
    return "Reasonable"


def expert_necessity_examples() -> tuple[list[dict], list[str]]:
    rows = [dict(zip(NECESSITY_ATTRIBUTES, combo))
            for combo in itertools.product(*(NECESSITY_VALUES[a] for a in NECESSITY_ATTRIBUTES))]
    return rows, [expert_label(r) for r in rows]
