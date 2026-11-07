import random

from budgetcare.domain.models import MoodTier

SPECIES_CATALOG: dict[str, list[str]] = {
    "hamster": ["Mochi", "Peanut", "Nugget", "Chippy", "Pip", "Bubbles"],
    "rabbit": ["Clover", "Boba", "Snowy", "Bunbun", "Oreo", "Daisy"],
    "cat": ["Luna", "Milo", "Simba", "Whiskers", "Kiki", "Neko"],
    "duckling": ["Puddles", "Waddles", "Ducky", "Quacky", "Sunny", "Pip"],
    "turtle": ["Shelly", "Speedy", "Franklin", "Squirt", "Donnie", "Pebble"],
    "hedgehog": ["Spike", "Prickles", "Sonic", "Bramble", "Hedgey", "Pokey"],
}

SPECIES_EMOJI: dict[str, str] = {
    "hamster": "🐹",
    "rabbit": "🐰",
    "cat": "🐱",
    "duckling": "🐥",
    "turtle": "🐢",
    "hedgehog": "🦔",
}


def pick_pet(existing_pairs: set[tuple[str, str]]) -> tuple[str, str]:
    """Pick a species and name, avoiding already used pairs in active goals if possible."""
    species_list = list(SPECIES_CATALOG.keys())

    for _ in range(5):
        sp = random.choice(species_list)
        name = random.choice(SPECIES_CATALOG[sp])
        if (sp, name) not in existing_pairs:
            return sp, name

    # Fallback if all 5 tries collided
    sp = random.choice(species_list)
    name = random.choice(SPECIES_CATALOG[sp])
    return sp, name


def get_pet_image_path(species: str, tier: MoodTier) -> str:
    """Return the relative image path in storage, e.g. 'pets/hamster/4.png'."""
    return f"pets/{species}/{tier.value}.png"
