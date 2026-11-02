"""Built-in training data.

1. CATEGORY_PHRASES - labelled merchant names / phrases for the k-NN categorizer,
   expanded with the formats transactions really arrive in: bank SMS and
   statement narrations ("UPI/ZOMATO/8812", "POS AMAZON BANGALORE",
   "ZOMATO PVT LTD"), UPI apps ("Paid to Zomato") and typed text.
   Covers the common Indian merchants, banks' bill-pay billers and UPI payees.
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
                "urban company repair", "pest control", "nobroker rent", "mygate maintenance", "nestaway rent",
                "housing society", "rent payment", "pg rent", "hostel fee", "home cleaning", "ac repair",
                "water purifier service", "house deposit"],
    "Utilities": ["electricity bill", "bescom", "tata power", "msedcl", "water bill", "lpg cylinder",
                  "indane gas", "piped gas", "broadband internet", "jio fiber", "airtel xstream",
                  "wifi bill", "mobile recharge", "airtel recharge", "jio recharge", "vi postpaid",
                  "phone bill", "dth recharge", "tata play", "jio prepaid", "airtel postpaid", "vi prepaid",
                  "act fibernet", "hathway broadband", "bwssb water", "mahanagar gas", "hp gas", "bharat gas",
                  "adani electricity", "bses delhi", "tneb electricity", "kseb electricity", "cesc", "sun direct",
                  "dish tv", "airtel dth", "electricity board", "power bill"],
    "Groceries": ["groceries", "supermarket", "vegetables", "fruits", "milk", "dairy", "kirana store",
                  "bigbasket", "blinkit", "zepto", "dmart", "swiggy instamart", "reliance fresh",
                  "more supermarket", "ration", "bakery", "nature basket", "spencers", "jiomart", "dmart ready",
                  "country delight", "milkbasket", "star bazaar", "more retail", "ratnadeep", "big bazaar",
                  "smart bazaar", "grofers", "amazon fresh", "flipkart grocery", "fresh to home", "meat shop",
                  "chicken shop", "fish market", "general store", "provision store", "nandini milk",
                  "amul parlour", "heritage dairy", "egg shop"],
    "Transport": ["petrol", "diesel", "fuel", "indian oil", "hp petrol pump", "bharat petroleum", "uber",
                  "ola cabs", "rapido", "metro card", "bus pass", "train ticket", "parking", "toll",
                  "fastag", "auto rickshaw", "car service", "bike service", "tyre", "uber india", "ola",
                  "rapido bike", "namma metro", "delhi metro", "mumbai metro", "bpcl", "hpcl", "iocl",
                  "fastag recharge", "blusmart", "meru cabs", "yulu", "bounce", "bmtc bus", "best bus",
                  "cng", "ev charging", "car wash", "puncture repair", "vehicle service", "petrol pump"],
    "Healthcare": ["pharmacy", "medicine", "medical store", "hospital", "doctor consultation", "clinic",
                   "apollo pharmacy", "lab test", "diagnostics", "dental", "1mg", "pharmeasy", "netmeds",
                   "eye checkup", "medplus", "practo", "tata 1mg", "apollo hospital", "manipal hospital",
                   "fortis hospital", "max healthcare", "narayana health", "dr lal pathlabs", "thyrocare",
                   "metropolis lab", "healthians", "wellness forever", "frank ross pharmacy", "physiotherapy",
                   "blood test", "health checkup", "chemist", "nursing home", "vaccination"],
    "Education": ["school fee", "tuition fee", "college fee", "online course", "books", "stationery",
                  "exam fee", "coaching classes", "udemy", "coursera", "byjus", "unacademy", "school bus",
                  "uniform", "vedantu", "physicswallah", "upgrad", "simplilearn", "whitehat jr", "toppr",
                  "school fees", "university fee", "library", "crossword books", "sapna book house",
                  "duolingo", "great learning", "admission fee", "test series"],
    "Insurance": ["insurance", "lic premium", "health insurance", "term insurance", "car insurance",
                  "star health", "hdfc ergo", "policybazaar", "policy renewal", "lic of india", "icici lombard",
                  "acko", "digit insurance", "bajaj allianz", "max life insurance", "sbi life", "tata aig",
                  "care health insurance", "bike insurance", "insurance premium", "hdfc life", "icici prudential"],
    "Loan EMI": ["emi", "car loan emi", "home loan emi", "personal loan", "credit card bill",
                 "bajaj finserv emi", "education loan", "loan repayment", "bajaj finance", "credit card payment",
                 "cred", "cred club", "tata capital", "hdfc ltd", "home credit", "loan emi", "nach debit",
                 "card bill payment", "lazypay", "simpl pay later", "zestmoney", "kreditbee", "moneyview",
                 "two wheeler loan"],
    "Dining Out": ["restaurant", "cafe", "coffee", "swiggy", "zomato", "pizza", "burger", "dominos",
                   "mcdonalds", "kfc", "starbucks", "barbeque nation", "dine out", "food delivery",
                   "haldirams", "chai point", "subway", "eatsure", "dominos pizza", "pizza hut", "burger king",
                   "chaayos", "third wave coffee", "cafe coffee day", "behrouz biryani", "faasos", "box8",
                   "freshmenu", "biryani", "dosa", "hotel restaurant", "bar and grill", "pub", "brewery",
                   "ice cream", "baskin robbins", "naturals ice cream", "wow momo", "taco bell", "dunkin",
                   "mtr", "saravana bhavan", "a2b", "rebel foods", "juice shop", "tea stall", "canteen",
                   "mess", "lunch", "dinner", "breakfast", "snacks"],
    "Shopping": ["amazon", "flipkart", "myntra", "ajio", "meesho", "mall", "clothes", "shoes",
                 "electronics", "croma", "reliance digital", "nykaa", "lifestyle store", "westside",
                 "decathlon", "ikea", "headphones", "mobile phone purchase", "laptop", "amazon pay", "tata cliq",
                 "lenskart", "pepperfry", "urban ladder", "shoppers stop", "pantaloons", "max fashion", "zara",
                 "h and m", "uniqlo", "bata", "puma", "nike", "adidas", "vijay sales", "sangeetha mobiles",
                 "poorvika", "apple store", "samsung store", "titan", "tanishq", "caratlane", "snapdeal",
                 "shopsy", "trends", "fabindia", "home centre", "furniture", "jewellery", "gadget", "watch"],
    "Entertainment": ["movie tickets", "cinema", "pvr", "inox", "concert", "bookmyshow", "gaming",
                      "amusement park", "wonderla", "party", "bowling", "steam games", "playstation",
                      "pvr cinemas", "inox movies", "cinepolis", "timezone", "paytm insider", "district",
                      "zomaland", "comedy show", "theatre", "snow world", "imagicaa", "go karting", "escape room",
                      "xbox", "dream11", "mpl games", "fun city", "museum tickets", "zoo tickets", "events"],
    "Subscriptions": ["netflix", "prime video", "amazon prime", "hotstar", "spotify", "youtube premium",
                      "subscription", "gym membership", "cult fit", "icloud", "google one", "sonyliv",
                      "zee5", "apple music", "linkedin premium", "disney hotstar", "jiocinema", "jiosaavn",
                      "gaana", "apple services", "google play", "microsoft 365", "chatgpt plus", "canva pro",
                      "adobe", "dropbox", "times prime", "swiggy one", "zomato gold", "newspaper",
                      "magazine subscription", "aha", "mx player", "voot", "kindle unlimited", "cultfit",
                      "gold gym", "anytime fitness", "yoga class", "membership fee"],
    "Travel": ["flight tickets", "indigo", "air india", "hotel booking", "airbnb", "makemytrip", "irctc",
               "goibibo", "oyo", "trip", "vacation", "holiday package", "cleartrip", "redbus", "indigo airlines",
               "vistara", "akasa air", "spicejet", "oyo rooms", "treebo", "fabhotels", "yatra", "ixigo",
               "abhibus", "zostel", "resort", "hotel stay", "travel agency", "visa fee", "thomas cook",
               "booking com", "agoda", "trivago", "railway reservation", "tour package", "airport"],
    "Personal Care": ["salon", "haircut", "spa", "beauty parlour", "cosmetics", "grooming", "lakme salon",
                      "barber", "skincare", "urban company salon", "naturals salon", "green trends",
                      "jawed habib", "enrich salon", "toni and guy", "bodycraft", "massage", "manicure",
                      "pedicure", "facial", "mamaearth", "the body shop", "plum goodness", "purplle", "perfume",
                      "unisex salon"],
    "Gifts & Donations": ["gift", "donation", "charity", "temple", "birthday gift", "wedding gift",
                          "ngo", "church", "gurudwara", "festival gift", "temple donation", "giveindia", "iskcon",
                          "ferns n petals", "igp gifts", "archies", "pm cares", "akshaya patra", "cry india",
                          "unicef", "mosque", "flowers", "bouquet", "gift card", "shagun", "anniversary gift",
                          "puja items", "prasad"],
    "Savings & Investments": ["sip", "mutual fund", "fixed deposit", "recurring deposit", "ppf", "stocks",
                              "zerodha", "groww", "nps", "gold savings", "savings transfer", "sukanya", "upstox",
                              "angel one", "kuvera", "paytm money", "coin by zerodha", "et money", "smallcase",
                              "digital gold", "sovereign gold bond", "nps contribution", "ppf deposit",
                              "rd installment", "fd booking", "indmoney", "5paisa", "icici direct",
                              "hdfc securities", "share purchase", "equity investment"],
    "Other": ["atm cash withdrawal", "cash withdrawal", "atm withdrawal", "bank charges", "sms charges",
              "annual fee", "penalty charges", "miscellaneous", "transfer to self", "wallet load",
              "paytm wallet", "amazon pay balance"],
    # ---- income
    "Salary": ["salary", "salary credit", "payroll", "monthly salary", "wages", "stipend", "sal credit",
               "salary for the month", "net salary", "pay slip", "incentive", "variable pay"],
    "Business": ["business income", "sales revenue", "shop income", "customer payment", "invoice payment",
                 "razorpay settlement", "paytm settlement", "phonepe business", "gst refund",
                 "vendor payment received", "client payment"],
    "Freelance": ["freelance", "freelance project", "consulting fee", "upwork", "fiverr", "design project",
                  "project payment", "tuition income", "upwork escrow", "freelancer com", "payoneer", "paypal",
                  "contract work", "consultancy charges", "honorarium"],
    "Interest & Dividends": ["interest credit", "fd interest", "savings interest", "dividend",
                             "mutual fund redemption", "interest paid", "int pd", "sb interest", "fd maturity",
                             "rd maturity", "bond interest", "dividend payout", "interest on deposit"],
    "Rental Income": ["rent received", "rental income", "tenant rent", "rent from tenant", "house rent received",
                      "shop rent received", "lease income"],
    "Other Income": ["cashback", "refund", "gift received", "bonus", "reimbursement", "cashback paytm",
                     "refund amazon", "flipkart refund", "reversal", "cred cashback", "google pay reward",
                     "income tax refund", "claim settlement", "prize money"],
}

INCOME_CATEGORIES = ["Salary", "Business", "Freelance", "Interest & Dividends", "Rental Income", "Other Income"]
# How descriptions really look: typed, bank statement / SMS narration, UPI app, card POS, company name.
TEMPLATES = ["{p}", "UPI/{P}/{n}", "{p} payment", "POS {P} {city}", "Paid to {p}", "{P} PVT LTD"]
INCOME_TEMPLATES = ["{p}", "NEFT {P} {n}", "{p} received", "BY TRANSFER {P}"]
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
