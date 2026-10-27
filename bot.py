"""Sira Cards Bot v5 - a Mudae-style card collecting bot.

Commands: /roll /collection /card /browse /profile /daily /sell /sell_dupes
          /trade /gift /wish add|remove|list /leaderboard /quiz /shop /buy /help
          /auction start|list|cancel /bid /uniques /release /quests /sets /weekly /duel /battle
          /admin give_dinars|give_card
"""

import asyncio
import datetime
import json
import math
import os
import random
import re
import sqlite3
import time
from typing import Optional

import discord
from discord import app_commands
from dotenv import load_dotenv

# ----------------------------------------------------------------------------
# Settings you can change
# ----------------------------------------------------------------------------
ROLLS_PER_WINDOW = 10         # rolls per player...
ROLL_WINDOW = 60 * 60         # ...every this many seconds
CLAIM_COOLDOWN = 60 * 60      # seconds between two claims
CLAIM_TIME_LIMIT = 60         # seconds the Claim button stays active

CURRENCY = "Dinars"
CUR = "🪙"
DAILY_BASE = 100              # /daily reward
DAILY_STREAK_BONUS = 20       # extra per streak day (up to STREAK_MAX_BONUS_DAYS)
DAILY_BONUS_ROLLS = 3         # free extra rolls with /daily
DAILY_COOLDOWN = 20 * 60 * 60
STREAK_RESET = 48 * 60 * 60   # miss a day and the streak restarts
QUIZ_REWARD = 30
QUIZ_COOLDOWN = 30
WISHLIST_MAX = 10

# Unique cards ("unique": true in characters.json): one copy per server
INACTIVE_DAYS = 30            # a unique card returns to the pool if its owner is away this long
PAGE_SIZE = 25                # lines per page in /collection

# v5 settings
TZ_OFFSET = 1 * 60 * 60       # your time zone in seconds (UTC+1): decides when a "day" or "week" starts
FEATURED_CHANCE = 0.06        # chance that a roll is the card of the week
FRIDAY_MULT = {"prophet": 2.0, "legendary": 2.0, "epic": 1.75, "rare": 1.3}   # Friday odds boost
SHINY_CHANCE = 0.05           # chance that a rare/epic/legendary roll is shiny
SHINY_RARITIES = {"rare", "epic", "legendary"}
SHINY_POWER = 1.2             # a shiny card is 20% stronger in battles
STREAK_GIFT_EVERY = 7         # a free card every N days of daily streak
STREAK_MAX_BONUS_DAYS = 9     # the streak bonus keeps growing for this many days
QUEST_BONUS = 50              # extra Dinars for finishing the 3 quests of the day
WEEKLY_PRIZES = [300, 200, 100]   # top 3 of the week (best quiz, most new cards)
DUEL_QUESTIONS = 5
DUEL_TIME = 20                # seconds per duel question
DUEL_MAX_BET = 500
BATTLE_MAX_BET = 1000
BATTLE_ROUNDS = 3             # cards per team = rounds
BATTLE_CATEGORIES = {"sahaba", "warrior", "scholar", "scientist"}   # who can fight (never prophets)
STATS = (("might", "Might"), ("wisdom", "Wisdom"), ("lead", "Leadership"))

QUESTS = {
    "roll": ("Roll 5 times", 5, 40),
    "claim": ("Claim a card", 1, 30),
    "quiz": ("Answer 3 quiz questions correctly", 3, 50),
    "social": ("Gift a card, accept a trade or place a bid", 1, 40),
    "fight": ("Play a quiz duel or a card battle", 1, 50),
    "daily": ("Use /daily", 1, 20),
}

SETS = [
    {"id": "hadith", "name": "Hadith Compilers", "title": "Guardian of the Sunnah", "reward": 400,
     "ids": ["muslim", "abu_dawud", "tirmidhi", "nasai", "ibn_majah"]},
    {"id": "paradise", "name": "Companions Promised Paradise", "title": "Pillar of the Ummah", "reward": 600,
     "ids": ["talha", "zubayr", "abdurrahman", "saad", "said_ibn_zayd", "abu_ubayda"]},
    {"id": "mothers", "name": "Mothers of the Believers", "title": "Keeper of the Household", "reward": 800,
     "ids": ["umm_salama", "hafsa", "sawda", "zaynab_jahsh", "zaynab_khuzayma", "juwayriyya",
             "safiyya_huyayy", "umm_habiba", "maymuna"]},
    {"id": "family", "name": "Family of the Prophet", "title": "Of the Blessed House", "reward": 700,
     "ids": ["hasan", "husayn", "abbas", "jafar", "ruqayya", "umm_kulthum_muhammad",
             "zaynab_muhammad", "safiyya_abdulmuttalib"]},
    {"id": "science", "name": "Golden Age of Science", "title": "Master of Knowledge", "reward": 500,
     "ids": ["khwarizmi", "ibn_haytham", "ibn_sina", "razi", "zahrawi", "biruni"]},
    {"id": "conquerors", "name": "Conquerors and Defenders", "title": "Commander of the Frontier", "reward": 500,
     "ids": ["ibn_qasim", "musa_nusayr", "qutayba", "uqba", "qutuz", "baibars"]},
    {"id": "algeria", "name": "Algerian Resistance and Reformers", "title": "Son of the Land", "reward": 600,
     "ids": ["abdelkader", "fatma_nsoumer", "mokrani", "bouamama", "cheikh_haddad",
             "ahmed_bey", "ibn_badis", "ibrahimi"]},
]

# Auctions
AUCTION_FEE = 0.05            # share of the final price kept by the bot
AUCTION_DURATIONS = {         # label: seconds
    "5 minutes": 5 * 60,
    "1 hour": 60 * 60,
    "6 hours": 6 * 60 * 60,
    "24 hours": 24 * 60 * 60,
}
AUCTION_MAX_ACTIVE = 3        # active auctions per player
AUCTION_MIN_PRICE = 10
AUCTION_MAX_PRICE = 1_000_000
AUCTION_MIN_INCREMENT = 10    # a new bid must beat the old one by at least this...
AUCTION_INCREMENT_PCT = 0.05  # ...or by this share, whichever is larger
AUCTION_SNIPE_WINDOW = 30     # a bid in the last N seconds extends the auction...
AUCTION_SNIPE_EXTEND = 30     # ...so that it ends N seconds after that bid

# Quiz
QUIZ_REWARDS = {1: 20, 2: 30, 3: 50}      # trivia reward by difficulty (stars)
QUESTION_TIME = 30                        # seconds to answer one question
CHALLENGE_QUESTIONS = 5                   # questions in the daily challenge
CHALLENGE_REWARD_PER_ANSWER = 20
CHALLENGE_PERFECT_BONUS = 50
CHALLENGE_COOLDOWN = 20 * 60 * 60

# Safety copies of the database
BACKUP_EVERY = 6 * 60 * 60
BACKUP_KEEP = 10

SHOP = {
    "rolls": {"label": "5 extra rolls", "price": 100},
    "claim": {"label": "Reset your claim cooldown", "price": 150},
}

# Order = display order. "weight" = chance to be drawn, "sell" = dinars per copy.
RARITIES = {
    "prophet":   {"label": "Prophet",   "weight": 1.5,  "color": 0x1ABC9C, "sell": 0},
    "legendary": {"label": "Legendary", "weight": 2,    "color": 0xF1C40F, "sell": 300},
    "epic":      {"label": "Epic",      "weight": 8,    "color": 0x9B59B6, "sell": 120},
    "rare":      {"label": "Rare",      "weight": 26,   "color": 0x3498DB, "sell": 50},
    "common":    {"label": "Common",    "weight": 62.5, "color": 0x95A5A6, "sell": 20},
}
CATEGORIES = {
    "prophet": "Prophets",
    "sahaba": "Companions",
    "warrior": "Warriors & Leaders",
    "scholar": "Scholars",
    "scientist": "Scientists & Explorers",
    "event": "Events & Battles",
    "place": "Places & Landmarks",
}
# Rarities that can never be sold or traded (they can still be gifted).
PROTECTED_RARITIES = {"prophet"}
# Categories for which the bot never shows an image (even if you add one).
NO_IMAGE_CATEGORIES = {"prophet"}

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# ----------------------------------------------------------------------------
# Loading data
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID", "").strip()
try:
    OWNER_ID = int(os.getenv("OWNER_ID", "").strip() or 0)
except ValueError:
    OWNER_ID = 0
# Where cards.db and the backups live (default: next to bot.py)
DATA_DIR = os.getenv("DATA_DIR", "").strip() or BASE_DIR
os.makedirs(DATA_DIR, exist_ok=True)

IMAGE_DIR = os.path.join(BASE_DIR, "images")
os.makedirs(IMAGE_DIR, exist_ok=True)

with open(os.path.join(BASE_DIR, "characters.json"), encoding="utf-8") as f:
    CHARACTERS = json.load(f)
for _c in CHARACTERS:
    if _c.get("rarity") not in RARITIES:
        raise SystemExit(f"characters.json: bad rarity for '{_c.get('id')}'")
    if _c.get("category") not in CATEGORIES:
        raise SystemExit(f"characters.json: bad category for '{_c.get('id')}'")
BY_ID = {c["id"]: c for c in CHARACTERS}

QUESTIONS = []
_qpath = os.path.join(BASE_DIR, "quiz_questions.json")
if os.path.isfile(_qpath):
    with open(_qpath, encoding="utf-8") as f:
        QUESTIONS = json.load(f)

DB_PATH = os.path.join(DATA_DIR, "cards.db")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        window_start INTEGER DEFAULT 0,
        rolls_used INTEGER DEFAULT 0,
        last_claim INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS cards (
        user_id INTEGER, char_id TEXT, count INTEGER,
        PRIMARY KEY (user_id, char_id)
    );
    CREATE TABLE IF NOT EXISTS wishlist (
        user_id INTEGER, char_id TEXT,
        PRIMARY KEY (user_id, char_id)
    );
    CREATE TABLE IF NOT EXISTS auctions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER, char_id TEXT, start_price INTEGER,
        bid INTEGER DEFAULT 0, bidder_id INTEGER DEFAULT 0,
        end_ts INTEGER, channel_id INTEGER, message_id INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    );
    """
)
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS quests (
        user_id INTEGER, day INTEGER, kind TEXT,
        progress INTEGER DEFAULT 0, done INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, day, kind)
    );
    CREATE TABLE IF NOT EXISTS shiny (
        user_id INTEGER, char_id TEXT, PRIMARY KEY (user_id, char_id)
    );
    CREATE TABLE IF NOT EXISTS sets_done (
        user_id INTEGER, set_id TEXT, PRIMARY KEY (user_id, set_id)
    );
    CREATE TABLE IF NOT EXISTS weekly (
        week INTEGER, user_id INTEGER,
        quiz INTEGER DEFAULT 0, claims INTEGER DEFAULT 0,
        PRIMARY KEY (week, user_id)
    );
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS quiz_seen (
        user_id INTEGER, qkey TEXT, ts INTEGER, PRIMARY KEY (user_id, qkey)
    );
    """
)
_existing = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
for _col in ("dinars", "last_daily", "streak", "bonus_rolls", "last_quiz",
             "quiz_correct", "quiz_total", "last_challenge", "last_seen"):
    if _col not in _existing:
        db.execute(f"ALTER TABLE users ADD COLUMN {_col} INTEGER DEFAULT 0")
db.execute("UPDATE users SET last_seen=? WHERE last_seen=0", (int(time.time()),))
db.commit()


# ----------------------------------------------------------------------------
# Helpers: data
# ----------------------------------------------------------------------------
def fmt_time(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def get_user(uid: int) -> sqlite3.Row:
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, window_start, rolls_used, last_claim, last_seen) "
        "VALUES (?, 0, 0, 0, ?)",
        (uid, int(time.time())),
    )
    db.commit()
    return db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def add_dinars(uid: int, amount: int) -> None:
    get_user(uid)
    db.execute("UPDATE users SET dinars = dinars + ? WHERE user_id=?", (amount, uid))
    db.commit()


def card_count(uid: int, cid: str) -> int:
    row = db.execute(
        "SELECT count FROM cards WHERE user_id=? AND char_id=?", (uid, cid)
    ).fetchone()
    return row["count"] if row else 0


def give_card(uid: int, cid: str, qty: int = 1) -> int:
    db.execute(
        "INSERT INTO cards VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, char_id) DO UPDATE SET count = count + ?",
        (uid, cid, qty, qty),
    )
    db.commit()
    return card_count(uid, cid)


def take_card(uid: int, cid: str, qty: int = 1) -> None:
    have = card_count(uid, cid)
    if have <= qty:
        db.execute("DELETE FROM cards WHERE user_id=? AND char_id=?", (uid, cid))
        db.execute("DELETE FROM shiny WHERE user_id=? AND char_id=?", (uid, cid))
    else:
        db.execute(
            "UPDATE cards SET count = count - ? WHERE user_id=? AND char_id=?",
            (qty, uid, cid),
        )
    db.commit()


def owned_cards(uid: int) -> dict:
    rows = db.execute("SELECT char_id, count FROM cards WHERE user_id=?", (uid,))
    return {r["char_id"]: r["count"] for r in rows if r["char_id"] in BY_ID}


def use_roll(uid: int):
    """Spend one roll. Returns (ok, seconds_until_reset, rolls_left)."""
    u = get_user(uid)
    now = int(time.time())
    ws, used, bonus = u["window_start"], u["rolls_used"], u["bonus_rolls"]
    if now - ws >= ROLL_WINDOW:
        ws, used = now, 0
    if used < ROLLS_PER_WINDOW:
        db.execute(
            "UPDATE users SET window_start=?, rolls_used=? WHERE user_id=?",
            (ws, used + 1, uid),
        )
        db.commit()
        return True, 0, ROLLS_PER_WINDOW - used - 1 + bonus
    if bonus > 0:
        db.execute(
            "UPDATE users SET window_start=?, rolls_used=?, bonus_rolls=? WHERE user_id=?",
            (ws, used, bonus - 1, uid),
        )
        db.commit()
        return True, 0, bonus - 1
    return False, ws + ROLL_WINDOW - now, 0


def rolls_left(u: sqlite3.Row) -> int:
    now = int(time.time())
    used = 0 if now - u["window_start"] >= ROLL_WINDOW else u["rolls_used"]
    return max(ROLLS_PER_WINDOW - used, 0) + u["bonus_rolls"]


def claim_wait(uid: int) -> int:
    return get_user(uid)["last_claim"] + CLAIM_COOLDOWN - int(time.time())


def claim_card(uid: int, cid: str, shiny: bool = False) -> int:
    total = give_card(uid, cid)
    db.execute("UPDATE users SET last_claim=? WHERE user_id=?", (int(time.time()), uid))
    if shiny:
        db.execute("INSERT OR IGNORE INTO shiny (user_id, char_id) VALUES (?, ?)", (uid, cid))
    db.commit()
    weekly_add(uid, "claims")
    return total


def taken_unique_ids() -> set:
    """Unique cards that cannot be rolled: owned by someone or held in an auction."""
    ids = [c["id"] for c in CHARACTERS if c.get("unique")]
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    owned = db.execute(
        f"SELECT DISTINCT char_id FROM cards WHERE count > 0 AND char_id IN ({marks})", ids
    ).fetchall()
    held = db.execute(
        f"SELECT DISTINCT char_id FROM auctions WHERE status='active' AND char_id IN ({marks})", ids
    ).fetchall()
    return {r["char_id"] for r in owned} | {r["char_id"] for r in held}


def unique_owner(cid: str) -> int:
    row = db.execute(
        "SELECT user_id FROM cards WHERE char_id=? AND count > 0 LIMIT 1", (cid,)
    ).fetchone()
    return row["user_id"] if row else 0


def touch_user(uid: int) -> None:
    get_user(uid)
    db.execute("UPDATE users SET last_seen=? WHERE user_id=?", (int(time.time()), uid))
    db.commit()


# ----------------------------------------------------------------------------
# v5 helpers: time, weekly stats, quests, sets, shiny
# ----------------------------------------------------------------------------
def local_now(now=None) -> datetime.datetime:
    ts = (now if now is not None else time.time()) + TZ_OFFSET
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)


def day_id(now=None) -> int:
    return int(((now if now is not None else time.time()) + TZ_OFFSET) // 86400)


def week_id(now=None) -> int:
    year, week, _ = local_now(now).isocalendar()
    return year * 100 + week


def is_friday(now=None) -> bool:
    return local_now(now).weekday() == 4


def week_ends_in(now=None) -> int:
    n = local_now(now)
    midnight = n.replace(hour=0, minute=0, second=0, microsecond=0)
    end = midnight + datetime.timedelta(days=7 - n.weekday())
    return int((end - n).total_seconds())


def featured_card(now=None) -> dict:
    """The card of the week: same for everybody, changes every Monday."""
    pool = [c for c in CHARACTERS if not c.get("unique") and c["rarity"] in ("rare", "epic", "legendary")]
    pool = sorted(pool, key=lambda c: c["id"]) or list(CHARACTERS)
    return random.Random(week_id(now)).choice(pool)


def get_meta(key: str, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value) -> None:
    db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))
    db.commit()


def weekly_add(uid: int, field: str, n: int = 1) -> None:
    assert field in ("quiz", "claims")
    wk = week_id()
    db.execute("INSERT OR IGNORE INTO weekly (week, user_id) VALUES (?, ?)", (wk, uid))
    db.execute(f"UPDATE weekly SET {field} = {field} + ? WHERE week=? AND user_id=?", (n, wk, uid))
    db.commit()


def is_shiny(uid: int, cid: str) -> bool:
    return db.execute(
        "SELECT 1 FROM shiny WHERE user_id=? AND char_id=?", (uid, cid)
    ).fetchone() is not None


def shiny_ids(uid: int) -> set:
    return {r["char_id"] for r in db.execute("SELECT char_id FROM shiny WHERE user_id=?", (uid,))}


def roll_shiny(char: dict) -> bool:
    return char["rarity"] in SHINY_RARITIES and random.random() < SHINY_CHANCE


def battle_eligible(char: dict) -> bool:
    return char["category"] in BATTLE_CATEGORIES and char["rarity"] != "prophet"


def eligible_cards(uid: int) -> list:
    cards = [BY_ID[cid] for cid in owned_cards(uid) if battle_eligible(BY_ID[cid])]
    return sorted(cards, key=lambda c: (-c.get("power", 0), c["name"]))


# --- daily quests -------------------------------------------------------------
def todays_quests(uid: int) -> list:
    day = day_id()
    rows = db.execute("SELECT * FROM quests WHERE user_id=? AND day=?", (uid, day)).fetchall()
    if not rows:
        kinds = random.Random(uid * 100000 + day).sample(sorted(QUESTS), 3)
        for kind in kinds:
            db.execute(
                "INSERT OR IGNORE INTO quests (user_id, day, kind) VALUES (?, ?, ?)", (uid, day, kind)
            )
        db.commit()
        rows = db.execute("SELECT * FROM quests WHERE user_id=? AND day=?", (uid, day)).fetchall()
    return sorted(rows, key=lambda r: r["kind"])


def quest_progress(uid: int, kind: str, n: int = 1) -> list:
    """Advance a quest. Rewards are paid at once. Returns lines to show the player."""
    rows = todays_quests(uid)
    row = next((r for r in rows if r["kind"] == kind), None)
    if row is None or row["done"]:
        return []
    text, goal, reward = QUESTS[kind]
    progress = min(row["progress"] + n, goal)
    done = 1 if progress >= goal else 0
    db.execute(
        "UPDATE quests SET progress=?, done=? WHERE user_id=? AND day=? AND kind=?",
        (progress, done, uid, row["day"], kind),
    )
    db.commit()
    lines = []
    if done:
        add_dinars(uid, reward)
        lines.append(f"📜 Quest done: {text} (+{reward} {CUR})")
        left = db.execute(
            "SELECT COUNT(*) AS n FROM quests WHERE user_id=? AND day=? AND done=0", (uid, row["day"])
        ).fetchone()["n"]
        if left == 0:
            add_dinars(uid, QUEST_BONUS)
            lines.append(f"🌟 All quests of the day done! Bonus +{QUEST_BONUS} {CUR}")
    return lines


async def notify(interaction: discord.Interaction, lines: list) -> None:
    if not lines:
        return
    try:
        await interaction.followup.send("\n".join(lines), ephemeral=True)
    except discord.HTTPException:
        pass


# --- sets ---------------------------------------------------------------------
def set_ids(s: dict) -> list:
    return [i for i in s["ids"] if i in BY_ID]


def check_sets(uid: int) -> list:
    owned = owned_cards(uid)
    done = {r["set_id"] for r in db.execute("SELECT set_id FROM sets_done WHERE user_id=?", (uid,))}
    lines = []
    for s in SETS:
        ids = set_ids(s)
        if s["id"] in done or not ids or not all(i in owned for i in ids):
            continue
        db.execute("INSERT OR IGNORE INTO sets_done (user_id, set_id) VALUES (?, ?)", (uid, s["id"]))
        db.commit()
        add_dinars(uid, s["reward"])
        lines.append(
            f"🏆 Set complete: **{s['name']}**! +{s['reward']} {CUR} and the title *{s['title']}*"
        )
    return lines


def user_titles(uid: int) -> list:
    done = {r["set_id"] for r in db.execute("SELECT set_id FROM sets_done WHERE user_id=?", (uid,))}
    return [s["title"] for s in SETS if s["id"] in done]


# --- quiz questions without repeats -------------------------------------------
def _fresh_choice(uids: list, items: list, key, n: int) -> list:
    seen = set()
    for u in uids:
        seen |= {r["qkey"] for r in db.execute("SELECT qkey FROM quiz_seen WHERE user_id=?", (u,))}
    fresh = [x for x in items if key(x) not in seen]
    if len(fresh) < n:
        # everything was asked: start a new cycle, but never repeat the last few
        for u in uids:
            db.execute(
                "DELETE FROM quiz_seen WHERE user_id=? AND qkey NOT IN "
                "(SELECT qkey FROM quiz_seen WHERE user_id=? ORDER BY ts DESC LIMIT 5)",
                (u, u),
            )
        db.commit()
        seen = set()
        for u in uids:
            seen |= {r["qkey"] for r in db.execute("SELECT qkey FROM quiz_seen WHERE user_id=?", (u,))}
        fresh = [x for x in items if key(x) not in seen]
    chosen = random.sample(fresh if len(fresh) >= n else items, n)
    stamp = int(time.time() * 1000)
    for u in uids:
        for i, x in enumerate(chosen):
            db.execute(
                "INSERT OR REPLACE INTO quiz_seen (user_id, qkey, ts) VALUES (?, ?, ?)",
                (u, key(x), stamp + i),
            )
    db.commit()
    return chosen


def pick_questions(uids: list, n: int = 1) -> list:
    return _fresh_choice(uids, QUESTIONS, lambda q: q.get("id") or q["q"], n)


def pick_who(uid: int) -> dict:
    return _fresh_choice([uid], CHARACTERS, lambda c: "who:" + c["id"], 1)[0]


def pick_character() -> dict:
    taken = taken_unique_ids()
    available = [c for c in CHARACTERS if c["id"] not in taken]
    featured = featured_card()
    if featured["id"] not in taken and random.random() < FEATURED_CHANCE:
        return featured
    friday = is_friday()
    weights = [
        RARITIES[r]["weight"] * (FRIDAY_MULT.get(r, 1.0) if friday else 1.0) for r in RARITIES
    ]
    rarity = random.choices(list(RARITIES), weights=weights)[0]
    pool = [c for c in available if c["rarity"] == rarity] or available or CHARACTERS
    return random.choice(pool)


def find_char(query: str) -> Optional[dict]:
    if query in BY_ID:
        return BY_ID[query]
    q = query.lower().strip()
    for c in CHARACTERS:
        if c["name"].lower() == q:
            return c
    return next((c for c in CHARACTERS if q in c["name"].lower()), None)


def sell_value(char: dict) -> int:
    return RARITIES[char["rarity"]]["sell"]


def is_protected(char: dict) -> bool:
    return char["rarity"] in PROTECTED_RARITIES


def dupes_for_sale(uid: int):
    """List of (char, extra_copies) the player can sell (keeps 1 of each)."""
    out = []
    for cid, count in owned_cards(uid).items():
        char = BY_ID[cid]
        if count > 1 and not is_protected(char):
            out.append((char, count - 1))
    return out


# ----------------------------------------------------------------------------
# Helpers: display
# ----------------------------------------------------------------------------
def image_for(char: dict):
    """Returns (local_path, url). Either may be None."""
    if char["category"] in NO_IMAGE_CATEGORIES:
        return None, None
    for ext in IMAGE_EXTS:
        path = os.path.join(IMAGE_DIR, char["id"] + ext)
        if os.path.isfile(path):
            return path, None
    return None, (char.get("image") or None)


def card_files(char: dict):
    path, _ = image_for(char)
    return [discord.File(path)] if path else []


def build_embed(char: dict, footer: Optional[str] = None, shiny: bool = False) -> discord.Embed:
    rarity = RARITIES[char["rarity"]]
    title = ("✨ " if shiny else "") + char["name"]
    embed = discord.Embed(
        title=title, description=char["bio"], color=0xFFD700 if shiny else rarity["color"]
    )
    embed.add_field(name="Title", value=char["title"], inline=True)
    embed.add_field(name="Rarity", value=rarity["label"] + (" (Shiny)" if shiny else ""), inline=True)
    embed.add_field(name="Category", value=CATEGORIES[char["category"]], inline=True)
    if char.get("power"):
        power = round(char["power"] * (SHINY_POWER if shiny else 1))
        embed.add_field(name="Power", value=f"⚔️ {power}", inline=True)
        if battle_eligible(char):
            embed.add_field(
                name="Stats",
                value=" | ".join(f"{label} {char.get(key, 0)}" for key, label in STATS),
                inline=False,
            )
    if char.get("unique"):
        embed.add_field(name="Edition", value="💎 Unique: one copy per server", inline=True)
    text = footer or ""
    if char.get("name_ar"):
        text = f"{text} | {char['name_ar']}" if text else char["name_ar"]
    if text:
        embed.set_footer(text=text)
    path, url = image_for(char)
    if path:
        embed.set_image(url=f"attachment://{os.path.basename(path)}")
    elif url:
        embed.set_image(url=url)
    return embed


def add_chunked_fields(embed: discord.Embed, name: str, lines: list) -> None:
    chunk, size, first = [], 0, True
    for line in lines:
        if size + len(line) + 1 > 1000:
            embed.add_field(name=name if first else "​", value="\n".join(chunk), inline=False)
            chunk, size, first = [], 0, False
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        embed.add_field(name=name if first else "​", value="\n".join(chunk), inline=False)


async def all_autocomplete(interaction: discord.Interaction, current: str):
    needle = current.lower()
    return [
        app_commands.Choice(name=c["name"][:100], value=c["id"])
        for c in CHARACTERS
        if needle in c["name"].lower()
    ][:25]


async def owned_autocomplete(interaction: discord.Interaction, current: str):
    needle = current.lower()
    out = []
    for cid, count in owned_cards(interaction.user.id).items():
        char = BY_ID[cid]
        if needle in char["name"].lower():
            label = char["name"] + (f" (x{count})" if count > 1 else "")
            out.append(app_commands.Choice(name=label[:100], value=cid))
    return out[:25]


CATEGORY_CHOICES = [app_commands.Choice(name=v, value=k) for k, v in CATEGORIES.items()]


# ----------------------------------------------------------------------------
# Views (buttons)
# ----------------------------------------------------------------------------
class ClaimView(discord.ui.View):
    def __init__(self, char: dict, shiny: bool = False):
        super().__init__(timeout=CLAIM_TIME_LIMIT)
        self.char = char
        self.shiny = shiny
        self.claimed = False
        self.message = None

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="✨")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            await interaction.response.send_message("This card was already claimed.", ephemeral=True)
            return
        wait = claim_wait(interaction.user.id)
        if wait > 0:
            await interaction.response.send_message(
                f"You can claim again in **{fmt_time(wait)}**.", ephemeral=True
            )
            return
        if self.char.get("unique") and self.char["id"] in taken_unique_ids():
            self.claimed = True
            button.disabled = True
            embed = build_embed(self.char, footer="This unique card is already owned")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return
        self.claimed = True
        uid = interaction.user.id
        total = claim_card(uid, self.char["id"], self.shiny)
        button.disabled = True
        suffix = " (duplicate)" if total > 1 else ""
        embed = build_embed(
            self.char, footer=f"Claimed by {interaction.user.display_name}{suffix}", shiny=self.shiny
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()
        await notify(interaction, quest_progress(uid, "claim") + check_sets(uid))

    async def on_timeout(self):
        if self.claimed or self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass


class TradeView(discord.ui.View):
    def __init__(self, proposer, target, give, want):
        super().__init__(timeout=120)
        self.proposer, self.target, self.give, self.want = proposer, target, give, want
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                f"Only {self.target.mention} can answer this trade.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        p, t = self.proposer.id, self.target.id
        if card_count(p, self.give["id"]) < 1 or card_count(t, self.want["id"]) < 1:
            await interaction.response.edit_message(
                content="Trade cancelled: one of the cards is no longer available.", embed=None, view=None
            )
            self.stop()
            return
        take_card(p, self.give["id"])
        take_card(t, self.want["id"])
        give_card(t, self.give["id"])
        give_card(p, self.want["id"])
        await interaction.response.edit_message(
            content=(
                f"✅ Trade complete! {self.proposer.mention} received **{self.want['name']}** "
                f"and {self.target.mention} received **{self.give['name']}**."
            ),
            embed=None,
            view=None,
        )
        self.stop()
        quest_progress(p, "social")
        await notify(interaction, quest_progress(t, "social") + check_sets(t))

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Trade declined.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(content="⌛ Trade expired.", embed=None, view=None)
            except discord.HTTPException:
                pass


class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, action):
        super().__init__(timeout=30)
        self.user_id, self.action = user_id, action

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=self.action(), view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


# ----------------------------------------------------------------------------
# Quiz
# ----------------------------------------------------------------------------
STOP_WORDS = {
    "ibn", "bin", "bint", "abu", "umm", "the", "and", "of", "al", "an", "as", "ash", "at",
    "ad", "az", "prophet", "imam", "battle", "mother", "sultan", "emir", "first", "last",
    "treaty", "conquest", "expedition", "migration", "pledge", "second", "night", "journey",
    "ascension", "farewell", "pilgrimage", "revelation", "sayf", "din", "salah",
}


def mask_text(text: str, char: dict) -> str:
    """Hide the answer's own name inside its description."""
    words = set()
    for part in re.split(r"[^A-Za-z']+", char["name"]):
        part = part.strip("'")
        if len(part) >= 4 and part.lower() not in STOP_WORDS:
            words.add(part)
    for word in sorted(words, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(word) + r"\b", "▮▮▮", text, flags=re.IGNORECASE)
    return text


def quiz_options(q: dict):
    options = [(q["a"], True)] + [(w, False) for w in q["w"]]
    random.shuffle(options)
    return options


def record_quiz(uid: int, correct: bool) -> list:
    get_user(uid)
    db.execute(
        "UPDATE users SET quiz_total = quiz_total + 1, quiz_correct = quiz_correct + ? "
        "WHERE user_id=?",
        (1 if correct else 0, uid),
    )
    db.commit()
    if correct:
        weekly_add(uid, "quiz")
        return quest_progress(uid, "quiz")
    return []


class QuizButton(discord.ui.Button):
    def __init__(self, label: str, correct: bool):
        super().__init__(label=label[:80], style=discord.ButtonStyle.secondary)
        self.correct = correct

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle(interaction, self)


class QuizView(discord.ui.View):
    """One question: who/what is this, or a trivia question."""

    def __init__(self, asker_id: int, options: list, reward: int, answer_text: str):
        super().__init__(timeout=QUESTION_TIME)
        self.asker_id, self.reward, self.answer_text = asker_id, reward, answer_text
        self.message = None
        self.done = False
        for label, correct in options:
            self.add_item(QuizButton(label, correct))

    async def handle(self, interaction: discord.Interaction, button: QuizButton):
        if interaction.user.id != self.asker_id:
            await interaction.response.send_message("This quiz isn't yours. Use /quiz!", ephemeral=True)
            return
        if self.done:
            return
        self.done = True
        for child in self.children:
            child.disabled = True
            if child.correct:
                child.style = discord.ButtonStyle.success
            elif child is button:
                child.style = discord.ButtonStyle.danger
        qlines = record_quiz(self.asker_id, button.correct)
        if button.correct:
            add_dinars(self.asker_id, self.reward)
            text = f"✅ Correct! +{self.reward} {CUR} {CURRENCY}"
        else:
            text = f"❌ Wrong. The answer was **{self.answer_text}**."
        await interaction.response.edit_message(content=text, view=self)
        self.stop()
        await notify(interaction, qlines)

    async def on_timeout(self):
        if self.done or self.message is None:
            return
        self.done = True
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(
                content=f"⌛ Time's up! It was **{self.answer_text}**.", view=self
            )
        except discord.HTTPException:
            pass


class ChallengeView(discord.ui.View):
    """Daily challenge: several trivia questions in a row, one message."""

    def __init__(self, asker_id: int, questions: list):
        super().__init__(timeout=QUESTION_TIME)
        self.asker_id, self.questions = asker_id, questions
        self.index, self.score = 0, 0
        self.message = None
        self.finished = False
        self.load_question()

    def load_question(self):
        self.clear_items()
        for label, correct in quiz_options(self.questions[self.index]):
            self.add_item(QuizButton(label, correct))

    def embed(self) -> discord.Embed:
        q = self.questions[self.index]
        embed = discord.Embed(
            title=f"Daily challenge - question {self.index + 1}/{len(self.questions)}",
            description=q["q"],
            color=0xE67E22,
        )
        embed.set_footer(text=f"Score: {self.score} | {QUESTION_TIME} seconds per question")
        return embed

    def reward(self) -> int:
        total = self.score * CHALLENGE_REWARD_PER_ANSWER
        if self.score == len(self.questions):
            total += CHALLENGE_PERFECT_BONUS
        return total

    def summary(self, prefix: str = "") -> str:
        reward = self.reward()
        if reward:
            add_dinars(self.asker_id, reward)
        head = prefix + "\n" if prefix else ""
        return (
            f"{head}🏁 Challenge complete: **{self.score}/{len(self.questions)}** "
            f"- you earned **{reward}** {CUR} {CURRENCY}."
        )

    async def handle(self, interaction: discord.Interaction, button: QuizButton):
        if interaction.user.id != self.asker_id:
            await interaction.response.send_message(
                "This challenge isn't yours. Use /quiz!", ephemeral=True
            )
            return
        if self.finished:
            return
        qlines = record_quiz(self.asker_id, button.correct)
        if button.correct:
            self.score += 1
            prefix = "✅ Correct!"
        else:
            prefix = f"❌ It was **{self.questions[self.index]['a']}**."
        self.index += 1
        if self.index >= len(self.questions):
            self.finished = True
            text = self.summary(prefix)
            self.stop()
            await interaction.response.edit_message(content=text, embed=None, view=None)
            await notify(interaction, qlines)
            return
        self.load_question()
        await interaction.response.edit_message(content=prefix, embed=self.embed(), view=self)
        await notify(interaction, qlines)

    async def on_timeout(self):
        if self.finished or self.message is None:
            return
        self.finished = True
        text = self.summary("⌛ Time's up!")
        try:
            await self.message.edit(content=text, embed=None, view=None)
        except discord.HTTPException:
            pass


# ----------------------------------------------------------------------------
# Auctions
# ----------------------------------------------------------------------------
def auction_row(aid: int):
    return db.execute("SELECT * FROM auctions WHERE id=?", (aid,)).fetchone()


def active_auction_count(uid: int) -> int:
    return db.execute(
        "SELECT COUNT(*) AS n FROM auctions WHERE seller_id=? AND status='active'", (uid,)
    ).fetchone()["n"]


def min_next_bid(a) -> int:
    if a["bid"] <= 0:
        return a["start_price"]
    return a["bid"] + max(AUCTION_MIN_INCREMENT, math.ceil(a["bid"] * AUCTION_INCREMENT_PCT))


def auction_embed(a, final: Optional[str] = None) -> discord.Embed:
    char = BY_ID[a["char_id"]]
    embed = build_embed(char)
    embed.title = f"🔨 Auction #{a['id']}: {char['name']}"
    embed.add_field(name="Seller", value=f"<@{a['seller_id']}>", inline=True)
    if a["bid"] > 0:
        embed.add_field(
            name="Highest bid", value=f"{CUR} {a['bid']} by <@{a['bidder_id']}>", inline=True
        )
    else:
        embed.add_field(name="Starting price", value=f"{CUR} {a['start_price']}", inline=True)
    if final:
        embed.add_field(name="Result", value=final, inline=False)
    else:
        embed.add_field(name="Ends", value=f"<t:{a['end_ts']}:R>", inline=True)
        embed.add_field(name="Minimum next bid", value=f"{CUR} {min_next_bid(a)}", inline=True)
    return embed


def place_bid(aid: int, uid: int, amount: int):
    """Returns (ok, error_text, previous_top_bidder_id)."""
    a = auction_row(aid)
    now = int(time.time())
    if a is None or a["status"] != "active" or now >= a["end_ts"]:
        return False, "This auction is over.", 0
    if uid == a["seller_id"]:
        return False, "You can't bid on your own auction.", 0
    need = min_next_bid(a)
    if amount < need:
        return False, f"The minimum bid is {need} {CURRENCY}.", 0
    cost = amount - (a["bid"] if a["bidder_id"] == uid else 0)
    have = get_user(uid)["dinars"]
    if have < cost:
        return False, f"Not enough {CURRENCY}: you need {cost}, you have {have}.", 0
    prev = 0
    if a["bidder_id"] and a["bidder_id"] != uid:
        add_dinars(a["bidder_id"], a["bid"])  # refund the previous top bidder
        prev = a["bidder_id"]
    add_dinars(uid, -cost)
    end_ts = a["end_ts"]
    if end_ts - now <= AUCTION_SNIPE_WINDOW:
        end_ts = now + AUCTION_SNIPE_EXTEND
    db.execute(
        "UPDATE auctions SET bid=?, bidder_id=?, end_ts=? WHERE id=?",
        (amount, uid, end_ts, aid),
    )
    db.commit()
    return True, "", prev


async def get_channel_safe(channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
    return channel


async def announce(channel_id: int, text: str) -> None:
    channel = await get_channel_safe(channel_id)
    if channel is None:
        return
    try:
        await channel.send(text)
    except discord.HTTPException:
        pass


async def refresh_auction_message(a, final: Optional[str] = None) -> None:
    if not a["message_id"] or a["char_id"] not in BY_ID:
        return
    channel = await get_channel_safe(a["channel_id"])
    if channel is None:
        return
    try:
        message = await channel.fetch_message(a["message_id"])
        await message.edit(
            embed=auction_embed(a, final), view=None if final else AuctionView()
        )
    except discord.HTTPException:
        pass


async def settle_auction(aid: int) -> None:
    """Close an auction whose time is up: pay the seller, give the card."""
    a = auction_row(aid)
    if a is None or a["status"] != "active" or a["end_ts"] > int(time.time()):
        return
    # Everything up to the commit below runs without awaiting, so it cannot interleave.
    char_id = a["char_id"]
    name = BY_ID[char_id]["name"] if char_id in BY_ID else char_id
    if a["bidder_id"]:
        fee = int(a["bid"] * AUCTION_FEE)
        payout = a["bid"] - fee
        give_card(a["bidder_id"], char_id)
        add_dinars(a["seller_id"], payout)
        status = "sold"
        result = (
            f"Sold to <@{a['bidder_id']}> for {CUR} {a['bid']} "
            f"(seller received {payout} after the {int(AUCTION_FEE * 100)}% fee)."
        )
        notice = (
            f"🔨 Auction **#{aid}** ended: <@{a['bidder_id']}> won **{name}** for "
            f"**{a['bid']}** {CUR}. <@{a['seller_id']}> received **{payout}** {CUR}."
        )
    else:
        give_card(a["seller_id"], char_id)
        status = "expired"
        result = "No bids. The card went back to the seller."
        notice = f"⌛ Auction **#{aid}** ended with no bids. <@{a['seller_id']}> got **{name}** back."
    db.execute("UPDATE auctions SET status=? WHERE id=?", (status, aid))
    db.commit()
    await refresh_auction_message(auction_row(aid), final=result)
    await announce(a["channel_id"], notice)


class AuctionView(discord.ui.View):
    """Persistent view: the button keeps working after a restart."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Bid (minimum)", style=discord.ButtonStyle.primary, emoji="🔨",
        custom_id="auction:bid",
    )
    async def bid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = db.execute(
            "SELECT id FROM auctions WHERE message_id=? AND status='active'",
            (interaction.message.id,),
        ).fetchone()
        if row is None:
            await interaction.response.send_message("This auction is over.", ephemeral=True)
            return
        a = auction_row(row["id"])
        ok, text, prev = place_bid(a["id"], interaction.user.id, min_next_bid(a))
        if not ok:
            await interaction.response.send_message(text, ephemeral=True)
            return
        a = auction_row(a["id"])
        await interaction.response.edit_message(embed=auction_embed(a), view=self)
        if prev:
            await interaction.followup.send(
                f"<@{prev}>, you were outbid on auction **#{a['id']}** "
                f"({BY_ID[a['char_id']]['name']}). New bid: **{a['bid']}** {CUR} "
                f"by {interaction.user.mention}."
            )


async def auction_loop():
    await bot.wait_until_ready()
    while True:
        try:
            rows = db.execute(
                "SELECT id FROM auctions WHERE status='active' AND end_ts <= ?",
                (int(time.time()),),
            ).fetchall()
            for row in rows:
                await settle_auction(row["id"])
        except Exception as exc:  # keep the loop alive whatever happens
            print("auction loop error:", exc)
        await asyncio.sleep(10)


# ----------------------------------------------------------------------------
# Backups
# ----------------------------------------------------------------------------
def run_backup() -> str:
    folder = os.path.join(DATA_DIR, "backups")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "cards-" + time.strftime("%Y%m%d-%H%M%S") + ".db")
    target = sqlite3.connect(path)
    try:
        with target:
            db.backup(target)
    finally:
        target.close()
    files = sorted(f for f in os.listdir(folder) if f.startswith("cards-") and f.endswith(".db"))
    for old in files[:-BACKUP_KEEP]:
        os.remove(os.path.join(folder, old))
    return path


async def backup_loop():
    while True:
        try:
            run_backup()
        except Exception as exc:
            print("backup error:", exc)
        await asyncio.sleep(BACKUP_EVERY)


# ----------------------------------------------------------------------------
# Pages (collection, browse)
# ----------------------------------------------------------------------------
def build_pages(title: str, lines: list, header: str = "", per_page: int = PAGE_SIZE) -> list:
    chunks = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    pages = []
    for n, chunk in enumerate(chunks, 1):
        text = (header + "\n\n" if header else "") + "\n".join(chunk)
        embed = discord.Embed(title=title, description=text, color=0x2ECC71)
        embed.set_footer(text=f"Page {n}/{len(chunks)}")
        pages.append(embed)
    return pages


def collection_pages(title: str, owned: dict, total: int, shinies: Optional[set] = None) -> list:
    shinies = shinies or set()
    lines = []
    for key, info in RARITIES.items():
        entries = sorted(
            (
                ("💎 " if BY_ID[cid].get("unique") else "") + BY_ID[cid]["name"]
                + (" ✨" if cid in shinies else ""),
                n,
            )
            for cid, n in owned.items()
            if BY_ID[cid]["rarity"] == key
        )
        if not entries:
            continue
        lines.append(f"**{info['label']}** ({len(entries)})")
        for name, n in entries:
            lines.append(f"• {name}" + (f" x{n}" if n > 1 else ""))
    return build_pages(title, lines, header=f"{len(owned)} / {total} unique cards")


class PagedView(discord.ui.View):
    def __init__(self, user_id: int, pages: list):
        super().__init__(timeout=180)
        self.user_id, self.pages, self.index = user_id, pages, 0
        self.message = None
        self.sync_buttons()

    def sync_buttons(self):
        self.prev_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Use the command yourself to flip through the pages.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(self.index - 1, 0)
        self.sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(self.index + 1, len(self.pages) - 1)
        self.sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    async def on_timeout(self):
        if self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass


async def send_paged(interaction: discord.Interaction, pages: list, ephemeral: bool = False):
    if len(pages) == 1:
        await interaction.response.send_message(embed=pages[0], ephemeral=ephemeral)
        return
    view = PagedView(interaction.user.id, pages)
    await interaction.response.send_message(embed=pages[0], view=view, ephemeral=ephemeral)
    view.message = await interaction.original_response()


# ----------------------------------------------------------------------------
# Unique cards that come back
# ----------------------------------------------------------------------------
def release_inactive_uniques(now: Optional[int] = None) -> list:
    """Unique cards whose owner has been away for INACTIVE_DAYS go back to the pool."""
    now = now or int(time.time())
    limit = now - INACTIVE_DAYS * 24 * 60 * 60
    returned = []
    for char in CHARACTERS:
        if not char.get("unique"):
            continue
        rows = db.execute(
            "SELECT c.user_id AS uid FROM cards c JOIN users u ON u.user_id = c.user_id "
            "WHERE c.char_id=? AND c.count > 0 AND u.last_seen > 0 AND u.last_seen < ?",
            (char["id"], limit),
        ).fetchall()
        for row in rows:
            take_card(row["uid"], char["id"], card_count(row["uid"], char["id"]))
            if sell_value(char):
                add_dinars(row["uid"], sell_value(char))
            returned.append((row["uid"], char["id"]))
    return returned


async def inactivity_loop():
    await bot.wait_until_ready()
    while True:
        try:
            for uid, cid in release_inactive_uniques():
                print(f"unique card {cid} returned to the pool (owner {uid} inactive)")
        except Exception as exc:
            print("inactivity loop error:", exc)
        await asyncio.sleep(60 * 60)


# ----------------------------------------------------------------------------
# Bot
# ----------------------------------------------------------------------------
class SiraBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(AuctionView())
        self.bg_tasks = [
            asyncio.create_task(auction_loop()),
            asyncio.create_task(backup_loop()),
            asyncio.create_task(inactivity_loop()),
            asyncio.create_task(weekly_loop()),
        ]
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} - {len(CHARACTERS)} characters loaded.")

    async def on_interaction(self, interaction: discord.Interaction):
        try:
            touch_user(interaction.user.id)
        except Exception as exc:
            print("touch error:", exc)


bot = SiraBot()


# ----------------------------------------------------------------------------
# Commands: rolling and viewing
# ----------------------------------------------------------------------------
@bot.tree.command(name="roll", description="Roll a random character card")
async def roll(interaction: discord.Interaction):
    uid = interaction.user.id
    ok, wait, remaining = use_roll(uid)
    if not ok:
        await interaction.response.send_message(
            f"No rolls left. Next reset in **{fmt_time(wait)}**. "
            f"You can also use /daily or buy rolls with /shop.",
            ephemeral=True,
        )
        return
    if interaction.channel_id:
        set_meta("announce_channel", interaction.channel_id)

    char = pick_character()
    shiny = roll_shiny(char)
    text = f"{interaction.user.mention} rolled! ({remaining} rolls left)"
    if is_friday():
        text += "\n🕌 **Friday boost:** better odds for rare cards today!"
    if char["id"] == featured_card()["id"]:
        text += "\n⭐ **Card of the week!**"
    if shiny:
        text += "\n✨ **SHINY!** A brilliant version, 20% stronger in battles."
    if char.get("unique"):
        text += "\n💎 **Unique card!** Only one copy exists on this server."
    wishers = db.execute(
        "SELECT user_id FROM wishlist WHERE char_id=? AND user_id != ? LIMIT 5",
        (char["id"], uid),
    ).fetchall()
    if wishers:
        text += "\n⭐ On the wishlist of: " + " ".join(f"<@{w['user_id']}>" for w in wishers)
    if db.execute(
        "SELECT 1 FROM wishlist WHERE char_id=? AND user_id=?", (char["id"], uid)
    ).fetchone():
        text += "\n⭐ This one is on your wishlist!"

    view = ClaimView(char, shiny)
    await interaction.response.send_message(
        content=text,
        embed=build_embed(char, shiny=shiny),
        view=view,
        files=card_files(char) or discord.utils.MISSING,
    )
    view.message = await interaction.original_response()
    await notify(interaction, quest_progress(uid, "roll"))


@bot.tree.command(name="collection", description="Show your cards (or another player's)")
@app_commands.describe(member="Whose collection to show", category="Only show one category")
@app_commands.choices(category=CATEGORY_CHOICES)
async def collection(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
    category: Optional[app_commands.Choice[str]] = None,
):
    target = member or interaction.user
    owned = owned_cards(target.id)
    if category:
        owned = {k: v for k, v in owned.items() if BY_ID[k]["category"] == category.value}
    if not owned:
        await interaction.response.send_message(
            "Nothing here yet. Use `/roll` and claim a card!", ephemeral=True
        )
        return
    total = sum(1 for c in CHARACTERS if not category or c["category"] == category.value)
    title = f"{target.display_name}'s collection" + (f" - {category.name}" if category else "")
    await send_paged(interaction, collection_pages(title, owned, total, shiny_ids(target.id)))


@bot.tree.command(name="browse", description="See every card of a category")
@app_commands.choices(category=CATEGORY_CHOICES)
async def browse(interaction: discord.Interaction, category: app_commands.Choice[str]):
    owned = owned_cards(interaction.user.id)
    taken = taken_unique_ids()
    order = list(RARITIES)
    chars = [c for c in CHARACTERS if c["category"] == category.value]
    chars.sort(key=lambda c: (order.index(c["rarity"]), c["name"]))
    lines = []
    for c in chars:
        if c["id"] in owned:
            mark = "✅"
        elif c.get("unique") and c["id"] in taken:
            mark = "🔒"
        else:
            mark = "⬜"
        gem = " 💎" if c.get("unique") else ""
        lines.append(f"{mark} {c['name']}{gem} - {RARITIES[c['rarity']]['label']}")
    have = sum(1 for c in chars if c["id"] in owned)
    header = f"You own {have} / {len(chars)}   (✅ owned, ⬜ missing, 🔒 unique card taken)"
    await send_paged(interaction, build_pages(category.name, lines, header, per_page=20), ephemeral=True)


@bot.tree.command(name="card", description="Look up a character")
@app_commands.describe(name="Character name")
async def card_cmd(interaction: discord.Interaction, name: str):
    char = find_char(name)
    if char is None:
        await interaction.response.send_message("Character not found.", ephemeral=True)
        return
    count = card_count(interaction.user.id, char["id"])
    text = f"You own **{count}** of this card." if count else None
    if char.get("unique"):
        owner = unique_owner(char["id"])
        if owner:
            text = f"💎 Unique card, owned by <@{owner}>." + (f" {text}" if text else "")
        elif char["id"] in taken_unique_ids():
            text = "💎 Unique card, currently up for auction."
        else:
            text = "💎 Unique card, still available to roll!"
    await interaction.response.send_message(
        content=text,
        embed=build_embed(char, shiny=is_shiny(interaction.user.id, char["id"])),
        files=card_files(char) or discord.utils.MISSING,
    )


card_cmd.autocomplete("name")(all_autocomplete)


@bot.tree.command(name="profile", description="Show your stats (or another player's)")
async def profile(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    u = get_user(target.id)
    owned = owned_cards(target.id)
    embed = discord.Embed(title=f"{target.display_name}'s profile", color=0x2ECC71)
    embed.add_field(name=CURRENCY, value=f"{CUR} {u['dinars']}", inline=True)
    embed.add_field(name="Daily streak", value=f"{u['streak']} day(s)", inline=True)
    embed.add_field(name="Rolls left", value=str(rolls_left(u)), inline=True)
    if u["quiz_total"]:
        embed.add_field(
            name="Quiz",
            value=f"{u['quiz_correct']} / {u['quiz_total']} correct",
            inline=True,
        )
    embed.add_field(
        name="Cards",
        value=f"{len(owned)} / {len(CHARACTERS)} unique, {sum(owned.values())} total",
        inline=False,
    )
    lines = []
    for key, label in CATEGORIES.items():
        have = sum(1 for cid in owned if BY_ID[cid]["category"] == key)
        total = sum(1 for c in CHARACTERS if c["category"] == key)
        lines.append(f"{label}: {have} / {total}")
    embed.add_field(name="Progress", value="\n".join(lines), inline=False)
    extra = []
    shinies = len(shiny_ids(target.id))
    if shinies:
        extra.append(f"✨ {shinies} shiny card(s)")
    titles = user_titles(target.id)
    if titles:
        extra.append("🏆 " + ", ".join(titles))
    if extra:
        embed.add_field(name="Achievements", value="\n".join(extra), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="Top collectors")
async def leaderboard(interaction: discord.Interaction):
    rows = db.execute(
        "SELECT user_id, COUNT(*) AS n FROM cards GROUP BY user_id ORDER BY n DESC LIMIT 10"
    ).fetchall()
    if not rows:
        await interaction.response.send_message("Nobody has a card yet!", ephemeral=True)
        return
    lines = [f"**{i}.** <@{r['user_id']}> - {r['n']} / {len(CHARACTERS)}" for i, r in enumerate(rows, 1)]
    embed = discord.Embed(title="Top collectors", description="\n".join(lines), color=0xF1C40F)
    await interaction.response.send_message(embed=embed)


# ----------------------------------------------------------------------------
# Commands: economy
# ----------------------------------------------------------------------------
@bot.tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    uid = interaction.user.id
    u = get_user(uid)
    now = int(time.time())
    wait = u["last_daily"] + DAILY_COOLDOWN - now
    if u["last_daily"] and wait > 0:
        await interaction.response.send_message(
            f"Come back in **{fmt_time(wait)}**.", ephemeral=True
        )
        return
    streak = u["streak"] + 1 if u["last_daily"] and now - u["last_daily"] < STREAK_RESET else 1
    reward = DAILY_BASE + DAILY_STREAK_BONUS * min(streak - 1, STREAK_MAX_BONUS_DAYS)
    db.execute(
        "UPDATE users SET dinars=dinars+?, last_daily=?, streak=?, bonus_rolls=bonus_rolls+? "
        "WHERE user_id=?",
        (reward, now, streak, DAILY_BONUS_ROLLS, uid),
    )
    db.commit()
    text = (
        f"🎁 Daily reward: **{reward}** {CUR} {CURRENCY} and **{DAILY_BONUS_ROLLS}** bonus rolls! "
        f"(streak: {streak} day{'s' if streak > 1 else ''})"
    )
    if streak % STREAK_GIFT_EVERY == 0:
        taken = taken_unique_ids()
        rarity = random.choices(["rare", "epic", "legendary"], weights=[70, 25, 5])[0]
        pool = [c for c in CHARACTERS if c["rarity"] == rarity and c["id"] not in taken]
        gift_card = random.choice(pool or CHARACTERS)
        give_card(uid, gift_card["id"])
        text += f"\n🎉 {streak} days in a row! Free card: **{gift_card['name']}** ({RARITIES[gift_card['rarity']]['label']})"
    else:
        left = STREAK_GIFT_EVERY - streak % STREAK_GIFT_EVERY
        text += f"\nFree card in {left} day{'s' if left > 1 else ''} if you keep your streak."
    await interaction.response.send_message(text)
    await notify(interaction, quest_progress(uid, "daily") + check_sets(uid))


@bot.tree.command(name="sell", description="Sell duplicate copies of a card (you keep one)")
@app_commands.describe(name="Card to sell", amount="How many copies")
async def sell(interaction: discord.Interaction, name: str, amount: app_commands.Range[int, 1, 100] = 1):
    char = find_char(name)
    if char is None:
        await interaction.response.send_message("Character not found.", ephemeral=True)
        return
    if is_protected(char):
        await interaction.response.send_message(
            f"**{char['name']}** cards cannot be sold.", ephemeral=True
        )
        return
    spare = card_count(interaction.user.id, char["id"]) - 1
    if spare < 1:
        await interaction.response.send_message(
            "You have no duplicate of this card (you always keep one).", ephemeral=True
        )
        return
    amount = min(amount, spare)
    gain = amount * sell_value(char)
    take_card(interaction.user.id, char["id"], amount)
    add_dinars(interaction.user.id, gain)
    await interaction.response.send_message(
        f"Sold {amount}x **{char['name']}** for **{gain}** {CUR} {CURRENCY}."
    )


sell.autocomplete("name")(owned_autocomplete)


@bot.tree.command(name="sell_dupes", description="Sell all your duplicates at once (keeps one of each)")
async def sell_dupes(interaction: discord.Interaction):
    uid = interaction.user.id
    dupes = dupes_for_sale(uid)
    if not dupes:
        await interaction.response.send_message("You have no duplicates to sell.", ephemeral=True)
        return
    total_cards = sum(n for _, n in dupes)
    total_gain = sum(n * sell_value(c) for c, n in dupes)

    def action() -> str:
        gained, sold = 0, 0
        for char, n in dupes_for_sale(uid):
            take_card(uid, char["id"], n)
            gained += n * sell_value(char)
            sold += n
        add_dinars(uid, gained)
        return f"Sold {sold} duplicate cards for **{gained}** {CUR} {CURRENCY}."

    await interaction.response.send_message(
        f"Sell **{total_cards}** duplicate cards for **{total_gain}** {CUR} {CURRENCY}?",
        view=ConfirmView(uid, action),
        ephemeral=True,
    )


@bot.tree.command(name="shop", description="See what you can buy")
async def shop(interaction: discord.Interaction):
    u = get_user(interaction.user.id)
    lines = [f"**{k}** - {v['label']}: {v['price']} {CUR}" for k, v in SHOP.items()]
    await interaction.response.send_message(
        f"You have {CUR} **{u['dinars']}** {CURRENCY}.\n\n" + "\n".join(lines) + "\n\nUse `/buy`.",
        ephemeral=True,
    )


@bot.tree.command(name="buy", description="Buy something from the shop")
@app_commands.choices(
    item=[app_commands.Choice(name=f"{v['label']} ({v['price']})", value=k) for k, v in SHOP.items()]
)
async def buy(interaction: discord.Interaction, item: app_commands.Choice[str]):
    uid = interaction.user.id
    u = get_user(uid)
    price = SHOP[item.value]["price"]
    if u["dinars"] < price:
        await interaction.response.send_message(
            f"Not enough {CURRENCY}: you need {price}, you have {u['dinars']}.", ephemeral=True
        )
        return
    if item.value == "rolls":
        db.execute(
            "UPDATE users SET dinars=dinars-?, bonus_rolls=bonus_rolls+5 WHERE user_id=?",
            (price, uid),
        )
        msg = "You bought **5 extra rolls**."
    else:
        db.execute(
            "UPDATE users SET dinars=dinars-?, last_claim=0 WHERE user_id=?", (price, uid)
        )
        msg = "Your claim cooldown has been reset."
    db.commit()
    await interaction.response.send_message(f"{msg} (-{price} {CUR})", ephemeral=True)


# ----------------------------------------------------------------------------
# Commands: trading and gifts
# ----------------------------------------------------------------------------
@bot.tree.command(name="trade", description="Offer a card swap to another player")
@app_commands.describe(member="Who to trade with", give="Your card", want="Their card you want")
async def trade(interaction: discord.Interaction, member: discord.Member, give: str, want: str):
    me = interaction.user
    if member.bot or member.id == me.id:
        await interaction.response.send_message("Pick another real player.", ephemeral=True)
        return
    give_c, want_c = find_char(give), find_char(want)
    if give_c is None or want_c is None:
        await interaction.response.send_message("Character not found.", ephemeral=True)
        return
    if is_protected(give_c) or is_protected(want_c):
        await interaction.response.send_message(
            "Prophet cards cannot be traded.", ephemeral=True
        )
        return
    if card_count(me.id, give_c["id"]) < 1:
        await interaction.response.send_message(f"You don't own **{give_c['name']}**.", ephemeral=True)
        return
    if card_count(member.id, want_c["id"]) < 1:
        await interaction.response.send_message(
            f"{member.display_name} doesn't own **{want_c['name']}**.", ephemeral=True
        )
        return

    embed = discord.Embed(title="Trade offer", color=0x3498DB)
    embed.add_field(
        name=f"{me.display_name} gives",
        value=f"**{give_c['name']}** ({RARITIES[give_c['rarity']]['label']})",
    )
    embed.add_field(
        name=f"{member.display_name} gives",
        value=f"**{want_c['name']}** ({RARITIES[want_c['rarity']]['label']})",
    )
    view = TradeView(me, member, give_c, want_c)
    await interaction.response.send_message(
        content=f"{member.mention}, {me.mention} wants to trade with you:", embed=embed, view=view
    )
    view.message = await interaction.original_response()


trade.autocomplete("give")(owned_autocomplete)
trade.autocomplete("want")(all_autocomplete)


@bot.tree.command(name="gift", description="Give one of your cards to another player")
@app_commands.describe(member="Who receives it", name="Your card")
async def gift(interaction: discord.Interaction, member: discord.Member, name: str):
    char = find_char(name)
    if member.bot or member.id == interaction.user.id:
        await interaction.response.send_message("Pick another real player.", ephemeral=True)
        return
    if char is None or card_count(interaction.user.id, char["id"]) < 1:
        await interaction.response.send_message("You don't own this card.", ephemeral=True)
        return
    take_card(interaction.user.id, char["id"])
    give_card(member.id, char["id"])
    await interaction.response.send_message(
        f"🎁 {interaction.user.mention} gave **{char['name']}** to {member.mention}!"
    )
    await notify(interaction, quest_progress(interaction.user.id, "social"))


gift.autocomplete("name")(owned_autocomplete)


# ----------------------------------------------------------------------------
# Commands: wishlist
# ----------------------------------------------------------------------------
wish = app_commands.Group(name="wish", description="Your wishlist (you get pinged when it's rolled)")
bot.tree.add_command(wish)


@wish.command(name="add", description="Add a character to your wishlist")
async def wish_add(interaction: discord.Interaction, name: str):
    char = find_char(name)
    if char is None:
        await interaction.response.send_message("Character not found.", ephemeral=True)
        return
    uid = interaction.user.id
    n = db.execute("SELECT COUNT(*) AS n FROM wishlist WHERE user_id=?", (uid,)).fetchone()["n"]
    if n >= WISHLIST_MAX:
        await interaction.response.send_message(
            f"Your wishlist is full ({WISHLIST_MAX}).", ephemeral=True
        )
        return
    db.execute("INSERT OR IGNORE INTO wishlist VALUES (?, ?)", (uid, char["id"]))
    db.commit()
    await interaction.response.send_message(f"⭐ **{char['name']}** added to your wishlist.", ephemeral=True)


@wish.command(name="remove", description="Remove a character from your wishlist")
async def wish_remove(interaction: discord.Interaction, name: str):
    char = find_char(name)
    if char is None:
        await interaction.response.send_message("Character not found.", ephemeral=True)
        return
    db.execute("DELETE FROM wishlist WHERE user_id=? AND char_id=?", (interaction.user.id, char["id"]))
    db.commit()
    await interaction.response.send_message(f"Removed **{char['name']}**.", ephemeral=True)


@wish.command(name="list", description="Show your wishlist")
async def wish_list(interaction: discord.Interaction):
    rows = db.execute("SELECT char_id FROM wishlist WHERE user_id=?", (interaction.user.id,)).fetchall()
    names = [BY_ID[r["char_id"]]["name"] for r in rows if r["char_id"] in BY_ID]
    text = "\n".join(f"⭐ {n}" for n in names) if names else "Your wishlist is empty."
    await interaction.response.send_message(text, ephemeral=True)


wish_add.autocomplete("name")(all_autocomplete)
wish_remove.autocomplete("name")(all_autocomplete)


# ----------------------------------------------------------------------------
# Commands: quiz and help
# ----------------------------------------------------------------------------
@bot.tree.command(name="quiz", description="Test your knowledge and win Dinars")
@app_commands.describe(mode="Which kind of quiz")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Trivia question", value="trivia"),
        app_commands.Choice(name="Who or what is this?", value="who"),
        app_commands.Choice(name="Daily challenge (5 questions)", value="challenge"),
    ]
)
async def quiz(interaction: discord.Interaction, mode: Optional[app_commands.Choice[str]] = None):
    uid = interaction.user.id
    u = get_user(uid)
    now = int(time.time())
    kind = mode.value if mode else "trivia"
    if kind == "trivia" and not QUESTIONS:
        kind = "who"

    if kind == "challenge":
        if len(QUESTIONS) < CHALLENGE_QUESTIONS:
            await interaction.response.send_message("Not enough questions yet.", ephemeral=True)
            return
        wait = u["last_challenge"] + CHALLENGE_COOLDOWN - now
        if wait > 0:
            await interaction.response.send_message(
                f"Next daily challenge in **{fmt_time(wait)}**.", ephemeral=True
            )
            return
        db.execute("UPDATE users SET last_challenge=? WHERE user_id=?", (now, uid))
        db.commit()
        view = ChallengeView(uid, pick_questions([uid], CHALLENGE_QUESTIONS))
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.message = await interaction.original_response()
        return

    wait = u["last_quiz"] + QUIZ_COOLDOWN - now
    if wait > 0:
        await interaction.response.send_message(
            f"Next quiz in **{fmt_time(wait)}**.", ephemeral=True
        )
        return
    db.execute("UPDATE users SET last_quiz=? WHERE user_id=?", (now, uid))
    db.commit()

    if kind == "who":
        answer = pick_who(uid)
        pool = [
            c for c in CHARACTERS
            if c["category"] == answer["category"] and c["id"] != answer["id"]
        ]
        if len(pool) < 3:
            pool = [c for c in CHARACTERS if c["id"] != answer["id"]]
        options = [(answer["name"], True)] + [(c["name"], False) for c in random.sample(pool, 3)]
        random.shuffle(options)
        embed = discord.Embed(
            title="Who or what is this?",
            description=mask_text(answer["bio"], answer),
            color=0xE67E22,
        )
        embed.set_footer(
            text=f"Category: {CATEGORIES[answer['category']]} | {QUESTION_TIME} seconds | +{QUIZ_REWARD} dinars"
        )
        view = QuizView(uid, options, QUIZ_REWARD, answer["name"])
    else:
        q = pick_questions([uid], 1)[0]
        reward = QUIZ_REWARDS.get(q["level"], QUIZ_REWARD)
        embed = discord.Embed(
            title="Trivia " + "⭐" * q["level"], description=q["q"], color=0xE67E22
        )
        embed.set_footer(
            text=f"{q['category']} | {QUESTION_TIME} seconds | +{reward} dinars"
        )
        view = QuizView(uid, quiz_options(q), reward, q["a"])

    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()


# ----------------------------------------------------------------------------
# Commands: auctions
# ----------------------------------------------------------------------------
auction = app_commands.Group(name="auction", description="Auctions between players")
bot.tree.add_command(auction)


@auction.command(name="start", description="Put one of your cards up for auction")
@app_commands.describe(card="Card to auction", price="Starting price in Dinars", duration="How long it runs")
@app_commands.choices(
    duration=[app_commands.Choice(name=k, value=v) for k, v in AUCTION_DURATIONS.items()]
)
async def auction_start(
    interaction: discord.Interaction,
    card: str,
    price: app_commands.Range[int, AUCTION_MIN_PRICE, AUCTION_MAX_PRICE],
    duration: app_commands.Choice[int],
):
    uid = interaction.user.id
    char = find_char(card)
    if char is None or card_count(uid, char["id"]) < 1:
        await interaction.response.send_message("You don't own this card.", ephemeral=True)
        return
    if is_protected(char):
        await interaction.response.send_message(
            f"**{char['name']}** cards cannot be sold.", ephemeral=True
        )
        return
    if active_auction_count(uid) >= AUCTION_MAX_ACTIVE:
        await interaction.response.send_message(
            f"You already have {AUCTION_MAX_ACTIVE} active auctions.", ephemeral=True
        )
        return

    take_card(uid, char["id"])  # the card is held by the bot until the auction ends
    end_ts = int(time.time()) + duration.value
    cur = db.execute(
        "INSERT INTO auctions (seller_id, char_id, start_price, end_ts, channel_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (uid, char["id"], price, end_ts, interaction.channel_id),
    )
    aid = cur.lastrowid
    db.commit()

    text = f"🔨 {interaction.user.mention} started an auction!"
    wishers = db.execute(
        "SELECT user_id FROM wishlist WHERE char_id=? AND user_id != ? LIMIT 5", (char["id"], uid)
    ).fetchall()
    if wishers:
        text += "\n⭐ On the wishlist of: " + " ".join(f"<@{w['user_id']}>" for w in wishers)
    try:
        await interaction.response.send_message(
            content=text,
            embed=auction_embed(auction_row(aid)),
            view=AuctionView(),
            files=card_files(char) or discord.utils.MISSING,
        )
        message = await interaction.original_response()
    except discord.HTTPException:
        db.execute("UPDATE auctions SET status='cancelled' WHERE id=?", (aid,))
        db.commit()
        give_card(uid, char["id"])
        return
    db.execute("UPDATE auctions SET message_id=? WHERE id=?", (message.id, aid))
    db.commit()


auction_start.autocomplete("card")(owned_autocomplete)


@auction.command(name="list", description="Show the active auctions")
async def auction_list(interaction: discord.Interaction):
    rows = db.execute(
        "SELECT * FROM auctions WHERE status='active' ORDER BY end_ts LIMIT 15"
    ).fetchall()
    if not rows:
        await interaction.response.send_message("No active auctions right now.", ephemeral=True)
        return
    lines = []
    for a in rows:
        char = BY_ID.get(a["char_id"])
        name = char["name"] if char else a["char_id"]
        price = a["bid"] if a["bid"] else a["start_price"]
        label = "bid" if a["bid"] else "start"
        link = ""
        if a["message_id"] and interaction.guild_id:
            link = f" [jump](https://discord.com/channels/{interaction.guild_id}/{a['channel_id']}/{a['message_id']})"
        lines.append(f"**#{a['id']}** {name} - {label} {CUR} {price} - ends <t:{a['end_ts']}:R>{link}")
    embed = discord.Embed(title="Active auctions", description="\n".join(lines), color=0xE67E22)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@auction.command(name="cancel", description="Cancel one of your auctions (only if it has no bids)")
@app_commands.describe(auction_id="Auction number")
async def auction_cancel(interaction: discord.Interaction, auction_id: int):
    a = auction_row(auction_id)
    if a is None or a["seller_id"] != interaction.user.id or a["status"] != "active":
        await interaction.response.send_message(
            "You have no active auction with this number.", ephemeral=True
        )
        return
    if a["bid"] > 0:
        await interaction.response.send_message(
            "This auction already has a bid, it can't be cancelled.", ephemeral=True
        )
        return
    db.execute("UPDATE auctions SET status='cancelled' WHERE id=?", (auction_id,))
    db.commit()
    give_card(a["seller_id"], a["char_id"])
    await interaction.response.send_message(f"Auction #{auction_id} cancelled, the card is back in your collection.", ephemeral=True)
    await refresh_auction_message(auction_row(auction_id), final="Cancelled by the seller.")


async def auction_autocomplete(interaction: discord.Interaction, current: str):
    needle = current.lower().strip()
    out = []
    rows = db.execute("SELECT * FROM auctions WHERE status='active' ORDER BY end_ts LIMIT 50").fetchall()
    for a in rows:
        char = BY_ID.get(a["char_id"])
        name = char["name"] if char else a["char_id"]
        if needle and needle not in name.lower() and needle not in str(a["id"]):
            continue
        out.append(app_commands.Choice(name=f"#{a['id']} {name} - {a['bid'] or a['start_price']}"[:100], value=a["id"]))
    return out[:25]


auction_cancel.autocomplete("auction_id")(auction_autocomplete)


@bot.tree.command(name="bid", description="Bid on an auction")
@app_commands.describe(auction_id="Auction number", amount="Your bid in Dinars")
async def bid(
    interaction: discord.Interaction,
    auction_id: int,
    amount: app_commands.Range[int, 1, AUCTION_MAX_PRICE],
):
    ok, text, prev = place_bid(auction_id, interaction.user.id, amount)
    if not ok:
        await interaction.response.send_message(text, ephemeral=True)
        return
    a = auction_row(auction_id)
    await interaction.response.send_message(
        f"✅ You are the highest bidder on #{auction_id} with **{amount}** {CUR}.", ephemeral=True
    )
    await notify(interaction, quest_progress(interaction.user.id, "social"))
    await refresh_auction_message(a)
    if prev:
        await announce(
            a["channel_id"],
            f"<@{prev}>, you were outbid on auction **#{auction_id}** "
            f"({BY_ID[a['char_id']]['name']}). New bid: **{amount}** {CUR} by {interaction.user.mention}.",
        )


bid.autocomplete("auction_id")(auction_autocomplete)


# ----------------------------------------------------------------------------
# Commands: owner tools (set OWNER_ID in .env)
# ----------------------------------------------------------------------------
admin = app_commands.Group(name="admin", description="Owner-only tools")
bot.tree.add_command(admin)


def is_owner(interaction: discord.Interaction) -> bool:
    return bool(OWNER_ID) and interaction.user.id == OWNER_ID


@admin.command(name="give_dinars", description="Owner only: give Dinars to a player")
async def admin_give_dinars(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_owner(interaction):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    add_dinars(member.id, amount)
    await interaction.response.send_message(
        f"Gave {amount} {CURRENCY} to {member.display_name}.", ephemeral=True
    )


@admin.command(name="give_card", description="Owner only: give a card to a player")
async def admin_give_card(interaction: discord.Interaction, member: discord.Member, name: str):
    if not is_owner(interaction):
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    char = find_char(name)
    if char is None:
        await interaction.response.send_message("Character not found.", ephemeral=True)
        return
    if char.get("unique") and char["id"] in taken_unique_ids():
        await interaction.response.send_message(
            "This unique card already exists on the server.", ephemeral=True
        )
        return
    give_card(member.id, char["id"])
    await interaction.response.send_message(
        f"Gave **{char['name']}** to {member.display_name}.", ephemeral=True
    )


admin_give_card.autocomplete("name")(all_autocomplete)


# ----------------------------------------------------------------------------
# Commands: unique cards
# ----------------------------------------------------------------------------
@bot.tree.command(name="uniques", description="Show the unique cards and who owns them")
async def uniques(interaction: discord.Interaction):
    taken = taken_unique_ids()
    order = list(RARITIES)
    cards = sorted(
        (c for c in CHARACTERS if c.get("unique")),
        key=lambda c: (order.index(c["rarity"]), c["name"]),
    )
    lines = []
    for c in cards:
        owner = unique_owner(c["id"])
        if owner:
            status = f"<@{owner}>"
        elif c["id"] in taken:
            status = "in an auction"
        else:
            status = "available"
        lines.append(f"💎 **{c['name']}** ({RARITIES[c['rarity']]['label']}) - {status}")
    embed = discord.Embed(
        title="Unique cards",
        description="\n".join(lines)
        + f"\n\nOnly one copy of each exists on this server. If the owner is away for "
        f"{INACTIVE_DAYS} days, the card goes back into the pool.",
        color=0x1ABC9C,
    )
    await interaction.response.send_message(embed=embed)


async def owned_unique_autocomplete(interaction: discord.Interaction, current: str):
    needle = current.lower()
    out = []
    for cid in owned_cards(interaction.user.id):
        char = BY_ID[cid]
        if char.get("unique") and needle in char["name"].lower():
            out.append(app_commands.Choice(name=char["name"][:100], value=cid))
    return out[:25]


@bot.tree.command(name="release", description="Give up a unique card so anyone can roll it again")
@app_commands.describe(name="The unique card to give back")
async def release(interaction: discord.Interaction, name: str):
    uid = interaction.user.id
    char = find_char(name)
    if char is None or not char.get("unique") or card_count(uid, char["id"]) < 1:
        await interaction.response.send_message("You don't own this unique card.", ephemeral=True)
        return
    refund = sell_value(char)

    def action() -> str:
        if card_count(uid, char["id"]) < 1:
            return "You no longer own this card."
        take_card(uid, char["id"], card_count(uid, char["id"]))
        if refund:
            add_dinars(uid, refund)
        gain = f" You received **{refund}** {CUR} {CURRENCY}." if refund else ""
        return f"**{char['name']}** went back into the pool.{gain}"

    await interaction.response.send_message(
        f"Give back **{char['name']}**? Anyone will be able to roll it again."
        + (f" You get {refund} {CUR} {CURRENCY}." if refund else ""),
        view=ConfirmView(uid, action),
        ephemeral=True,
    )


release.autocomplete("name")(owned_unique_autocomplete)


# ----------------------------------------------------------------------------
# Quests, sets, weekly ranking
# ----------------------------------------------------------------------------
@bot.tree.command(name="quests", description="Your 3 quests of the day")
async def quests_cmd(interaction: discord.Interaction):
    rows = todays_quests(interaction.user.id)
    lines = []
    for r in rows:
        text, goal, reward = QUESTS[r["kind"]]
        mark = "✅" if r["done"] else "⬜"
        lines.append(f"{mark} **{text}** - {r['progress']}/{goal} - {reward} {CUR}")
    if all(r["done"] for r in rows):
        lines.append("\n🌟 All done for today, see you tomorrow!")
    else:
        lines.append(f"\nFinish all 3 for a bonus of {QUEST_BONUS} {CUR}. New quests every day.")
    embed = discord.Embed(title="Quests of the day", description="\n".join(lines), color=0x3498DB)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="sets", description="Card sets to complete for a reward and a title")
async def sets_cmd(interaction: discord.Interaction):
    uid = interaction.user.id
    won = check_sets(uid)
    owned = owned_cards(uid)
    done = {r["set_id"] for r in db.execute("SELECT set_id FROM sets_done WHERE user_id=?", (uid,))}
    lines = []
    for s in SETS:
        ids = set_ids(s)
        have = sum(1 for i in ids if i in owned)
        mark = "✅" if s["id"] in done else "⬜"
        lines.append(f"{mark} **{s['name']}** {have}/{len(ids)} - {s['reward']} {CUR} + title *{s['title']}*")
        if s["id"] not in done:
            missing = [BY_ID[i]["name"] for i in ids if i not in owned]
            if missing and len(missing) <= 4:
                lines.append("   Missing: " + ", ".join(missing))
    embed = discord.Embed(title="Sets", description="\n".join(lines), color=0xF1C40F)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await notify(interaction, won)


@bot.tree.command(name="weekly", description="Card of the week, Friday boost and weekly rankings")
async def weekly_cmd(interaction: discord.Interaction):
    if interaction.channel_id:
        set_meta("announce_channel", interaction.channel_id)
    wk = week_id()
    feat = featured_card()
    lines = [
        f"⭐ **Card of the week:** {feat['name']} ({RARITIES[feat['rarity']]['label']}) - shows up more often until Monday.",
        "🕌 **Friday boost:** "
        + ("ACTIVE today, better odds for rare cards!" if is_friday() else "every Friday, better odds for rare cards."),
        f"⏳ The week ends in **{fmt_time(week_ends_in())}**.",
    ]
    embed = discord.Embed(title="This week", description="\n".join(lines), color=0xE67E22)
    for field, label in (("quiz", "Best quiz (correct answers)"), ("claims", "Most new cards claimed")):
        rows = db.execute(
            f"SELECT user_id, {field} AS n FROM weekly WHERE week=? AND {field} > 0 "
            f"ORDER BY n DESC, user_id LIMIT 5",
            (wk,),
        ).fetchall()
        text = "\n".join(f"**{i}.** <@{r['user_id']}> - {r['n']}" for i, r in enumerate(rows, 1)) or "Nobody yet"
        embed.add_field(name=label, value=text, inline=True)
    prizes = " / ".join(str(p) for p in WEEKLY_PRIZES)
    embed.set_footer(text=f"Prizes for the top 3 of each ranking: {prizes} {CURRENCY}")
    await interaction.response.send_message(embed=embed)


async def settle_week() -> None:
    cur = week_id()
    old = get_meta("current_week")
    if old is None:
        set_meta("current_week", cur)
        return
    old = int(old)
    if old == cur:
        return
    set_meta("current_week", cur)
    lines = []
    for field, label in (("quiz", "Best quiz"), ("claims", "Most new cards")):
        rows = db.execute(
            f"SELECT user_id, {field} AS n FROM weekly WHERE week=? AND {field} > 0 "
            f"ORDER BY n DESC, user_id LIMIT {len(WEEKLY_PRIZES)}",
            (old,),
        ).fetchall()
        for pos, r in enumerate(rows):
            add_dinars(r["user_id"], WEEKLY_PRIZES[pos])
            lines.append(f"{label} #{pos + 1}: <@{r['user_id']}> ({r['n']}) wins {WEEKLY_PRIZES[pos]} {CUR}")
    db.execute("DELETE FROM weekly WHERE week < ?", (old,))
    db.commit()
    channel = get_meta("announce_channel")
    if lines and channel:
        await announce(int(channel), "🏁 **Weekly ranking is over!**\n" + "\n".join(lines))


async def weekly_loop():
    await bot.wait_until_ready()
    while True:
        try:
            await settle_week()
        except Exception as exc:
            print("weekly loop error:", exc)
        await asyncio.sleep(10 * 60)


# ----------------------------------------------------------------------------
# Quiz duels
# ----------------------------------------------------------------------------
BUSY = set()   # players currently in a duel or battle


class DuelQuestionView(discord.ui.View):
    def __init__(self, players: tuple, q: dict):
        super().__init__(timeout=DUEL_TIME + 5)
        self.players, self.q = players, q
        self.locked, self.winner, self.done = set(), 0, False
        self.finished = asyncio.Event()
        for label, correct in quiz_options(q):
            self.add_item(QuizButton(label, correct))

    def close(self):
        self.done = True
        for child in self.children:
            child.disabled = True
            if child.correct:
                child.style = discord.ButtonStyle.success

    async def handle(self, interaction: discord.Interaction, button: QuizButton):
        uid = interaction.user.id
        if uid not in self.players:
            await interaction.response.send_message("This duel isn't yours.", ephemeral=True)
            return
        if self.done or uid in self.locked:
            await interaction.response.send_message("You can't answer this one anymore.", ephemeral=True)
            return
        if button.correct:
            self.winner = uid
            self.close()
            await interaction.response.edit_message(
                content=f"✅ {interaction.user.mention} answered first!", view=self
            )
            self.finished.set()
            self.stop()
        else:
            self.locked.add(uid)
            await interaction.response.send_message("❌ Wrong! You're out for this question.", ephemeral=True)
            if len(self.locked) >= len(self.players):
                self.close()
                self.finished.set()


async def run_duel(channel_id: int, a, b, bet: int) -> None:
    try:
        channel = await get_channel_safe(channel_id)
        if channel is None:
            if bet:
                add_dinars(a.id, bet)
                add_dinars(b.id, bet)
            return
        questions = pick_questions([a.id, b.id], DUEL_QUESTIONS)
        score = {a.id: 0, b.id: 0}
        for i, q in enumerate(questions, 1):
            view = DuelQuestionView((a.id, b.id), q)
            embed = discord.Embed(
                title=f"Duel - question {i}/{len(questions)}", description=q["q"], color=0xE74C3C
            )
            embed.set_footer(
                text=f"{a.display_name} {score[a.id]} - {score[b.id]} {b.display_name} | first correct answer wins the point"
            )
            msg = await channel.send(embed=embed, view=view)
            try:
                await asyncio.wait_for(view.finished.wait(), DUEL_TIME)
            except asyncio.TimeoutError:
                pass
            if not view.winner:
                view.close()
                try:
                    await msg.edit(content=f"⌛ Nobody got it. The answer was **{q['a']}**.", view=view)
                except discord.HTTPException:
                    pass
            else:
                score[view.winner] += 1
            await asyncio.sleep(2)
        sa, sb = score[a.id], score[b.id]
        pot = bet * 2
        if sa == sb:
            if bet:
                add_dinars(a.id, bet)
                add_dinars(b.id, bet)
            result = f"🤝 Draw {sa}-{sb}!" + (" Bets refunded." if bet else "")
        else:
            winner = a if sa > sb else b
            if pot:
                add_dinars(winner.id, pot)
            result = f"🏆 {winner.mention} wins the duel {max(sa, sb)}-{min(sa, sb)}!" + (
                f" +{pot} {CUR}" if pot else ""
            )
        lines = [result]
        for p in (a, b):
            lines += quest_progress(p.id, "fight")
        await channel.send("\n".join(lines))
    except Exception as exc:
        print("duel error:", exc)
        if bet:
            add_dinars(a.id, bet)
            add_dinars(b.id, bet)
    finally:
        BUSY.discard(a.id)
        BUSY.discard(b.id)


class DuelInvite(discord.ui.View):
    def __init__(self, challenger, target, bet: int):
        super().__init__(timeout=120)
        self.challenger, self.target, self.bet = challenger, target, bet
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                f"Only {self.target.mention} can answer this challenge.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        a, b = self.challenger, self.target
        if a.id in BUSY or b.id in BUSY:
            await interaction.response.edit_message(content="Someone is already in a duel or battle.", view=None)
            self.stop()
            return
        if self.bet and (get_user(a.id)["dinars"] < self.bet or get_user(b.id)["dinars"] < self.bet):
            await interaction.response.edit_message(
                content="Duel cancelled: someone can't afford the bet anymore.", view=None
            )
            self.stop()
            return
        if self.bet:
            add_dinars(a.id, -self.bet)
            add_dinars(b.id, -self.bet)
        BUSY.add(a.id)
        BUSY.add(b.id)
        await interaction.response.edit_message(
            content=f"⚔️ Duel accepted! {a.mention} vs {b.mention} - first to answer correctly scores.", view=None
        )
        self.stop()
        asyncio.create_task(run_duel(interaction.channel_id, a, b, self.bet))

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Duel declined.", view=None)
        self.stop()

    async def on_timeout(self):
        if self.message is not None:
            try:
                await self.message.edit(content="⌛ Duel challenge expired.", view=None)
            except discord.HTTPException:
                pass


@bot.tree.command(name="duel", description="Challenge a player to a quiz duel: first correct answer wins the point")
@app_commands.describe(member="Who you challenge", bet=f"Dinars each player puts in (max {DUEL_MAX_BET})")
async def duel(
    interaction: discord.Interaction,
    member: discord.Member,
    bet: app_commands.Range[int, 0, DUEL_MAX_BET] = 0,
):
    me = interaction.user
    if member.bot or member.id == me.id:
        await interaction.response.send_message("Pick another real player.", ephemeral=True)
        return
    if len(QUESTIONS) < DUEL_QUESTIONS:
        await interaction.response.send_message("Not enough questions yet.", ephemeral=True)
        return
    if me.id in BUSY or member.id in BUSY:
        await interaction.response.send_message("Someone is already in a duel or battle.", ephemeral=True)
        return
    if bet and (get_user(me.id)["dinars"] < bet or get_user(member.id)["dinars"] < bet):
        await interaction.response.send_message("Both players need enough Dinars for this bet.", ephemeral=True)
        return
    view = DuelInvite(me, member, bet)
    await interaction.response.send_message(
        f"⚔️ {me.mention} challenges {member.mention} to a quiz duel! "
        f"{DUEL_QUESTIONS} questions, first correct answer wins each point."
        + (f" Bet: **{bet}** {CUR} each." if bet else ""),
        view=view,
    )
    view.message = await interaction.original_response()


# ----------------------------------------------------------------------------
# Card battles
# ----------------------------------------------------------------------------
def play_battle(team_a: list, shiny_a: set, team_b: list, shiny_b: set):
    """Each round both cards compare one random stat, with a bit of luck. Returns (wins_a, wins_b, lines)."""
    wa = wb = 0
    lines = []
    for i, (ca, cb) in enumerate(zip(team_a, team_b), 1):
        key, label = random.choice(STATS)
        va = BY_ID[ca][key] * (SHINY_POWER if ca in shiny_a else 1.0) * random.uniform(0.85, 1.15)
        vb = BY_ID[cb][key] * (SHINY_POWER if cb in shiny_b else 1.0) * random.uniform(0.85, 1.15)
        if abs(va - vb) < 1e-9:
            va += random.choice((-0.01, 0.01))
        if va > vb:
            wa += 1
            verdict = "◀ wins"
        else:
            wb += 1
            verdict = "wins ▶"
        lines.append(
            f"**Round {i}** ({label}): {BY_ID[ca]['name']} {int(va)} vs {int(vb)} {BY_ID[cb]['name']} - {verdict}"
        )
    return wa, wb, lines


class TeamSelect(discord.ui.Select):
    def __init__(self, battle, uid: int):
        cards = eligible_cards(uid)[:25]
        options = [
            discord.SelectOption(label=c["name"][:100], value=c["id"], description=f"Power {c.get('power', 0)}")
            for c in cards
        ]
        super().__init__(
            placeholder=f"Pick {BATTLE_ROUNDS} cards (order = rounds)",
            min_values=BATTLE_ROUNDS,
            max_values=BATTLE_ROUNDS,
            options=options,
        )
        self.battle, self.uid = battle, uid

    async def callback(self, interaction: discord.Interaction):
        await self.battle.set_team(interaction, self.uid, list(self.values))


class TeamPickView(discord.ui.View):
    def __init__(self, battle, uid: int):
        super().__init__(timeout=300)
        self.add_item(TeamSelect(battle, uid))


class BattleView(discord.ui.View):
    def __init__(self, challenger, target, bet: int):
        super().__init__(timeout=300)
        self.challenger, self.target, self.bet = challenger, target, bet
        self.teams = {}
        self.accepted = False
        self.resolved = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.challenger.id, self.target.id):
            await interaction.response.send_message("This battle isn't yours.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(f"Only {self.target.mention} can accept.", ephemeral=True)
            return
        if self.accepted:
            await interaction.response.send_message("Already accepted: pick your team.", ephemeral=True)
            return
        if len(eligible_cards(self.target.id)) < BATTLE_ROUNDS:
            await interaction.response.send_message(
                f"You need at least {BATTLE_ROUNDS} fighters (companions, warriors, scholars or scientists).",
                ephemeral=True,
            )
            return
        self.accepted = True
        await interaction.response.send_message(
            "Choose your team:", view=TeamPickView(self, self.target.id), ephemeral=True
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            return
        self.resolved = True
        BUSY.discard(self.challenger.id)
        BUSY.discard(self.target.id)
        await interaction.response.edit_message(content="❌ Battle cancelled.", embed=None, view=None)
        self.stop()

    async def set_team(self, interaction: discord.Interaction, uid: int, cids: list):
        if self.resolved:
            await interaction.response.edit_message(content="This battle is over.", view=None)
            return
        if any(card_count(uid, c) < 1 for c in cids):
            await interaction.response.edit_message(content="You no longer own one of these cards.", view=None)
            return
        self.teams[uid] = cids
        names = ", ".join(BY_ID[c]["name"] for c in cids)
        await interaction.response.edit_message(content=f"✅ Team locked in: {names}", view=None)
        if self.accepted and len(self.teams) == 2:
            await self.resolve()

    async def resolve(self):
        if self.resolved:
            return
        self.resolved = True
        a, b = self.challenger, self.target
        try:
            ok = all(
                card_count(p.id, c) >= 1 for p in (a, b) for c in self.teams[p.id]
            ) and (not self.bet or (get_user(a.id)["dinars"] >= self.bet and get_user(b.id)["dinars"] >= self.bet))
            if not ok:
                text = "Battle cancelled: a card or the bet is no longer available."
            else:
                wa, wb, lines = play_battle(
                    self.teams[a.id], shiny_ids(a.id), self.teams[b.id], shiny_ids(b.id)
                )
                winner = a if wa > wb else b
                text = "\n".join(lines) + f"\n\n🏆 {winner.mention} wins the battle {max(wa, wb)}-{min(wa, wb)}!"
                if self.bet:
                    add_dinars(a.id, -self.bet)
                    add_dinars(b.id, -self.bet)
                    add_dinars(winner.id, self.bet * 2)
                    text += f" +{self.bet * 2} {CUR}"
                extra = quest_progress(a.id, "fight") + quest_progress(b.id, "fight")
                if extra:
                    text += "\n" + "\n".join(extra)
            if self.message is not None:
                await self.message.edit(content=text, embed=None, view=None)
        except discord.HTTPException:
            pass
        finally:
            BUSY.discard(a.id)
            BUSY.discard(b.id)
            self.stop()

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        BUSY.discard(self.challenger.id)
        BUSY.discard(self.target.id)
        if self.message is not None:
            try:
                await self.message.edit(content="⌛ Battle expired.", embed=None, view=None)
            except discord.HTTPException:
                pass


@bot.tree.command(name="battle", description="Fight another player with a team of 3 cards (best of 3 rounds)")
@app_commands.describe(member="Your opponent", bet=f"Dinars each player puts in (max {BATTLE_MAX_BET})")
async def battle(
    interaction: discord.Interaction,
    member: discord.Member,
    bet: app_commands.Range[int, 0, BATTLE_MAX_BET] = 0,
):
    me = interaction.user
    if member.bot or member.id == me.id:
        await interaction.response.send_message("Pick another real player.", ephemeral=True)
        return
    if me.id in BUSY or member.id in BUSY:
        await interaction.response.send_message("Someone is already in a duel or battle.", ephemeral=True)
        return
    if len(eligible_cards(me.id)) < BATTLE_ROUNDS:
        await interaction.response.send_message(
            f"You need at least {BATTLE_ROUNDS} fighters (companions, warriors, scholars or scientists). "
            "Prophets never fight.",
            ephemeral=True,
        )
        return
    if bet and (get_user(me.id)["dinars"] < bet or get_user(member.id)["dinars"] < bet):
        await interaction.response.send_message("Both players need enough Dinars for this bet.", ephemeral=True)
        return
    BUSY.add(me.id)
    BUSY.add(member.id)
    view = BattleView(me, member, bet)
    await interaction.response.send_message(
        f"⚔️ {me.mention} challenges {member.mention} to a card battle! "
        f"Each player picks {BATTLE_ROUNDS} cards; every round compares one stat (Might, Wisdom or Leadership)."
        + (f" Bet: **{bet}** {CUR} each." if bet else "")
        + f"\n{member.mention}, press Accept and choose your team.",
        view=view,
    )
    view.message = await interaction.original_response()
    await interaction.followup.send(
        "Choose your team (your top 25 cards by power are listed):",
        view=TeamPickView(view, me.id),
        ephemeral=True,
    )


# ----------------------------------------------------------------------------
# Help
# ----------------------------------------------------------------------------
@bot.tree.command(name="help", description="Show the commands")
async def help_command(interaction: discord.Interaction):
    text = (
        "**Cards**\n"
        "`/roll` roll a card, press Claim to keep it\n"
        "`/collection` your cards, `/browse` full list by category, `/card` look up anyone\n"
        "`/profile` your stats, `/leaderboard` top collectors\n\n"
        "**Economy**\n"
        f"`/daily` free {CURRENCY} + rolls, `/sell`, `/sell_dupes` sell duplicates, `/shop` and `/buy`\n"
        f"`/quiz` trivia, who-is-this, or the daily challenge to win {CURRENCY}\n"
        "`/quests` 3 quests per day, `/sets` complete sets for titles, `/weekly` card of the week and rankings\n\n"
        "**Players**\n"
        "`/trade` swap cards, `/gift` give a card, `/wish add|remove|list` get pinged for a card\n"
        f"`/uniques` the unique cards (one copy per server), `/release` give one back\n"
        "`/duel` quiz duel (first correct answer scores), `/battle` fight with a team of 3 cards\n"
        "`/auction start|list|cancel` and `/bid` auctions between players "
        f"({int(AUCTION_FEE * 100)}% fee for the seller)\n\n"
        f"You get {ROLLS_PER_WINDOW} rolls per hour and can claim once every "
        f"{CLAIM_COOLDOWN // 60} minutes. Prophet cards cannot be sold, traded or auctioned."
    )
    await interaction.response.send_message(text, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Missing DISCORD_TOKEN. Create a .env file (see README).")
    bot.run(TOKEN)
