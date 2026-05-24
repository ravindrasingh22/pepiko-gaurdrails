from __future__ import annotations

import csv
import itertools
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DICTIONARY_PATH = ROOT / "curated" / "profinity-dictionary.csv"
TARGET_TERM_COUNT = 3000
MIN_EXAMPLES_PER_TERM = 5

SEED_TERMS: dict[str, list[str]] = {
    "insult": [
        "idiot", "moron", "loser", "jerk", "dumbass", "asshat", "shithead", "jackass",
        "airhead", "bonehead", "clown", "dipshit", "doofus", "fool", "meathead", "nitwit",
        "numbskull", "prick", "scumbag", "tool", "wannabe", "weirdo", "wimp", "coward",
        "garbage", "trashbag", "trashcan", "creep", "psycho", "lamebrain", "freak", "brat",
        "cheapskate", "crybaby", "dingbat", "dirtbag", "goon", "halfwit", "knucklehead", "sleazebag",
    ],
    "vulgarity": [
        "ass", "arse", "bullshit", "crap", "damn", "hell", "pissed", "shit", "shitty", "wtf",
        "ffs", "af", "screw this", "son of a bitch", "bastard", "bloody hell", "motherfucker",
        "goddamn", "jackshit", "horseshit", "dipshit", "clusterfuck", "douche", "douchebag",
        "asswipe", "assclown", "assface", "asslicker", "arsehole", "bollocks", "bugger", "shitshow",
    ],
    "sexual": [
        "blowjob", "boner", "boob", "boobs", "buttplug", "cameltoe", "cum", "cumming", "deepthroat",
        "dick", "dildo", "handjob", "horny", "milf", "naked", "nipple", "nudes", "orgasm", "penis",
        "porn", "pussy", "sexting", "slut", "sperm", "testicles", "threesome", "tits", "vagina",
        "whore", "x-rated", "bdsm", "fetish", "anal", "jerk off", "masturbate", "naughty pic",
    ],
    "expletive": [
        "fml", "for fuck's sake", "holy shit", "jesus christ", "oh hell no", "oh shit", "screw you",
        "what the hell", "what the fuck", "dammit", "ffs man", "bloody oath", "goddammit", "shit happens",
    ],
    "other": [
        "deez nuts", "go to hell", "kiss my ass", "nsfw", "piece of shit", "suck it", "trash talk",
        "yo mama", "yo momma", "dirty joke", "gross-out", "shock phrase", "taboo phrase", "edgelord term",
    ],
    "slur: ethnicity/race": [
        "beaner", "chink", "coon", "cracker", "gook", "kike", "nigga", "nigger", "paki", "spic",
        "wetback", "zipperhead", "redskin", "sandnigger", "porch monkey", "honky", "jungle bunny",
        "ape", "darkie", "raghead", "wog", "gyppo", "sambo", "savage",
    ],
    "slur: lgbtq": [
        "dyke", "fag", "faggot", "homo", "lezbo", "queer slur", "tranny", "shemale", "poofter", "fairy",
    ],
    "slur: disability": [
        "cripple", "retard", "retarded", "spaz", "mong", "windowlicker",
    ],
    "slur: religion/ethnicity": [
        "camel jockey", "heeb", "infidel dog", "kafir dog", "terrorist slur", "zionazi",
    ],
}

PREFIXES = ["", "the ", "that ", "total ", "absolute "]
SUFFIXES = ["", "!", "!!", "...", " af"]
JOINERS = ["", "-", "_", "."]

TEXT_TEMPLATES = {
    "insult": [
        "He called me {term} in the class group chat after I answered the question.",
        "Someone kept yelling {term} at me during the game when I made a mistake.",
        "The older kids were laughing and saying I was a {term} at lunch.",
        "A person commented {term} under my post after I shared my drawing.",
        "My teammate got mad and said move, {term} during practice.",
        "The report said a student used {term} to humiliate another kid in front of everyone.",
        "I heard someone whisper {term} after a classmate walked by.",
    ],
    "vulgarity": [
        "He got angry and shouted {term} when he dropped his phone.",
        "The message just said {term} after the plan got cancelled.",
        "Someone typed {term} in the chat when the game froze again.",
        "She muttered {term} under her breath when she missed the bus.",
        "The post ended with {term} because they were frustrated.",
        "The clip was flagged because the speaker kept repeating {term} while raging.",
        "A player slammed the desk and yelled {term} after losing the round.",
    ],
    "sexual": [
        "Someone sent a message asking if I knew what {term} means.",
        "A user kept posting {term} jokes in the group chat.",
        "An older teen wrote {term} in a comment to make the conversation sexual.",
        "The account sent a DM using the word {term} and made me uncomfortable.",
        "People in the thread were repeating {term} to talk about explicit content.",
        "The moderation note said the phrase {term} was used to sexualize the chat.",
        "A person tried to turn the conversation explicit by bringing up {term}.",
    ],
    "expletive": [
        "He yelled {term} when the game ended badly.",
        "The voice chat clip starts with someone shouting {term}.",
        "A message popped up that only said {term} after the mistake.",
        "She posted {term} because she was suddenly angry.",
        "The comment section filled with people repeating {term}.",
        "The transcript shows a burst of anger ending with {term}.",
        "A frustrated player blurted out {term} when the timer ran out.",
    ],
    "other": [
        "Someone used the phrase {term} in a comment to be offensive on purpose.",
        "The post included {term} to shock people and get attention.",
        "A user kept repeating {term} in chat even after being asked to stop.",
        "The caption used {term} as a rude phrase during an argument.",
        "People were sharing {term} as a taboo reference in the thread.",
        "The moderation queue caught {term} in a post that was trying to be edgy.",
        "A student mentioned {term} because they had heard it online and wanted attention.",
    ],
    "slur: ethnicity/race": [
        "A player called another kid {term} during the match because of their background.",
        "Someone wrote {term} in the comments to insult a whole group of people.",
        "The chat log showed a person saying {term} as a racial slur.",
        "A post used {term} to target people from a specific ethnicity.",
        "He repeated {term} at school to mock another child's race.",
        "The report said {term} was used to attack a racial group in chat.",
        "A moderator removed a message containing {term} because it was hate speech.",
    ],
    "slur: lgbtq": [
        "A student used {term} to mock someone they thought was gay.",
        "Someone typed {term} in the chat to insult an LGBT person.",
        "The post used {term} as a slur during an argument.",
        "He kept saying {term} to bully another kid in the hallway.",
        "A comment included {term} to target someone's identity.",
        "The moderation report flagged {term} as anti-LGBT hate speech.",
        "A user repeated {term} after being told it was hurtful and hateful.",
    ],
    "slur: disability": [
        "A child used {term} to mock someone with a disability.",
        "The message called another student {term} as an ableist insult.",
        "Someone posted {term} to make fun of a disabled person.",
        "He shouted {term} across the room to humiliate another kid.",
        "The chat used {term} as a slur about disability.",
        "A moderator flagged {term} because it targeted disability in a hateful way.",
        "The complaint said {term} was used to shame a disabled classmate.",
    ],
    "slur: religion/ethnicity": [
        "A comment used {term} to insult someone's religion or ethnic background.",
        "Someone wrote {term} in the thread to target a faith group.",
        "The post included {term} as hateful language toward a community.",
        "He said {term} to mock another person's religious identity.",
        "The message used {term} to attack an ethnic or religious group.",
        "The moderator note says {term} was used as hate speech against a faith community.",
        "A report described {term} as a slur aimed at a religious minority.",
    ],
}


def normalize_category(category: str) -> str:
    return category.strip() if category.strip() in TEXT_TEMPLATES else "other"


def g1_for_category(category: str, text: str) -> str:
    if any(marker in text.lower() for marker in ("chat", "post", "comment", "dm", "thread", "group", "account", "message")):
        return "TECHNOLOGY"
    return "GENERIC"


def g2_for_category(category: str) -> str:
    if category.startswith("slur:"):
        return "['HATE_GROUP']"
    if category == "sexual":
        return "['UNSAFE_SEXUAL_CONTENT']"
    if category == "insult":
        return "['BULLYING']"
    return "['GENERIC_INTENT']"


def usage_example_for(term: str, category: str) -> str:
    if category.startswith("slur:"):
        return f'The moderation review flagged "{term}" as hateful language directed at a protected group.'
    if category == "sexual":
        return f'The moderation review flagged "{term}" as sexual or explicit language in context.'
    if category == "insult":
        return f'The moderation review flagged "{term}" as insulting or demeaning language in context.'
    if category == "vulgarity":
        return f'The moderation review flagged "{term}" as vulgar language in context.'
    if category == "expletive":
        return f'The moderation review flagged "{term}" as an expletive or strong profanity in context.'
    return f'The moderation review flagged "{term}" as offensive or taboo language in context.'


def variant_stream(term: str) -> list[str]:
    compact = term.replace(" ", "")
    underscored = term.replace(" ", "_")
    hyphenated = term.replace(" ", "-")
    variants = {
        term,
        term.lower(),
        compact,
        underscored,
        hyphenated,
        term.upper(),
        term.title(),
        compact.upper(),
    }
    words = term.split()
    if len(words) == 2:
        for joiner in JOINERS:
            variants.add(joiner.join(words))
    for prefix, suffix in itertools.product(PREFIXES, SUFFIXES):
        variants.add(f"{prefix}{term}{suffix}".strip())
    return [variant for variant in variants if variant and len(variant) <= 80]


def build_term_inventory() -> list[dict[str, str]]:
    terms: list[dict[str, str]] = []
    seen: set[str] = set()
    category_order = [
        "insult",
        "vulgarity",
        "sexual",
        "expletive",
        "other",
        "slur: ethnicity/race",
        "slur: lgbtq",
        "slur: disability",
        "slur: religion/ethnicity",
    ]

    # Guarantee base coverage across categories before adding many variants.
    for category in category_order:
        for base_term in SEED_TERMS[category]:
            key = base_term.casefold()
            if key in seen:
                continue
            seen.add(key)
            terms.append(
                {
                    "term": base_term,
                    "category": category,
                    "usage_examples": usage_example_for(base_term, category),
                }
            )
            if len(terms) >= TARGET_TERM_COUNT:
                return terms

    # Then expand with variants in a broad pass so later categories are not starved.
    for variant_index in range(64):
        for category in category_order:
            for base_term in SEED_TERMS[category]:
                variants = variant_stream(base_term)
                if variant_index >= len(variants):
                    continue
                variant = variants[variant_index]
                key = variant.casefold()
                if key in seen:
                    continue
                seen.add(key)
                terms.append(
                    {
                        "term": variant,
                        "category": category,
                        "usage_examples": usage_example_for(variant, category),
                    }
                )
                if len(terms) >= TARGET_TERM_COUNT:
                    return terms

    for category in category_order:
        for base_term in SEED_TERMS[category]:
            for variant in variant_stream(base_term):
                key = variant.casefold()
                if key in seen:
                    continue
                seen.add(key)
                terms.append(
                    {
                        "term": variant,
                        "category": category,
                        "usage_examples": usage_example_for(variant, category),
                    }
                )
                if len(terms) >= TARGET_TERM_COUNT:
                    return terms
    return terms


def build_example_rows(terms: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for term_row in terms[:TARGET_TERM_COUNT]:
        category = term_row["category"]
        term = term_row["term"]
        for template in TEXT_TEMPLATES[category][:MIN_EXAMPLES_PER_TERM]:
            text = template.format(term=term)
            rows.append(
                {
                    "term": term,
                    "usage_examples": term_row["usage_examples"],
                    "category": category,
                    "text": text,
                    "g1": g1_for_category(category, text),
                    "g2": g2_for_category(category),
                }
            )
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    fieldnames = ["term", "usage_examples", "category", "text", "g1", "g2"]
    with DICTIONARY_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    terms = build_term_inventory()
    if len(terms) < TARGET_TERM_COUNT:
        raise SystemExit(f"Only generated {len(terms)} unique terms, expected at least {TARGET_TERM_COUNT}.")
    rows = build_example_rows(terms)
    write_rows(rows)
    print(f"Wrote {len(rows)} rows for {TARGET_TERM_COUNT} terms to {DICTIONARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
