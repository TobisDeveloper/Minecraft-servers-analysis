"""Hypotheses to measure, not assertions that these formats are trending."""
import re
import unicodedata

from .models import Candidate


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower())
                   if not unicodedata.combining(c))


def matches(text: str, candidate: Candidate) -> bool:
    text = normalize(text)
    return any(re.search(r"(?<!\w)" + re.escape(normalize(a)) + r"(?!\w)", text)
               for a in candidate.aliases)


def catalog() -> list[Candidate]:
    rows = [
        ("lifesteal", "Lifesteal SMP", ["lifesteal", "life steal", "kradez srdci"], "lifesteal smp", "Paper + a licensed Lifesteal plugin", 4,
         ["Pin Paper and plugin versions; configure heart limits and combat logging.", "Offer a whitelisted friend-group preset and a separate public PvP preset.", "Test death, revive, anti-dupe, permissions, grief protection and backups."],
         ["PvP churn and toxicity", "Plugin license and economy exploits"], "Vlastni Lifesteal SMP pro partu za 2 minuty.", "Vlastny Lifesteal SMP pre partiu za 2 minuty."),
        ("cobblemon", "Cobblemon / creature collecting", ["cobblemon", "cobbleverse", "cobblemon academy"], "cobblemon", "Fabric or NeoForge + an explicitly licensed server modpack", 8,
         ["Select one server-compatible pack and pin its loader, Minecraft and mod versions.", "Generate a matching client manifest; pre-generate a bounded world.", "Test battles, trades, persistence, spawn rules and a restore with 6-10 players."],
         ["Pack redistribution and third-party IP", "CPU load during exploration", "Client install friction"], "Vlastni Cobblemon svet pro kamarady. Stejna verze, jeden klik.", "Vlastny Cobblemon svet pre kamaratov. Rovnake verzie, jeden klik."),
        ("create", "Create / factory co-op", ["create mod", "create modpack", "create server", "create: astral", "create above and beyond"], "minecraft create modpack", "Fabric/Forge/NeoForge + a pinned Create server pack", 8,
         ["Offer a small co-op pack with a matching client install guide.", "Set contraption and chunk-loader limits; benchmark automation-heavy bases.", "Test recipes, trains, permissions, backups and rolling upgrades."],
         ["Tick-heavy factories", "Loader/version fragmentation"], "Postavte vlastni tovarnu s partou. Create server bez nastavovani.", "Postavte vlastnu tovaren s partiou. Create server bez nastavovania."),
        ("hardcore", "One-life / event hardcore", ["hardcore", "one life", "1 life", "100 days", "100 dni", "jeden zivot"], "minecraft hardcore", "Paper + event, spectator and whitelist plugins", 4,
         ["Create an opt-in one-life rule set with an explicit event end date.", "Provide spectator mode, a streamer-safe whitelist and an event reset tool.", "Rehearse death handling, reconnects, backups and moderator recovery."],
         ["Short event lifecycle", "Lost-progress support burden"], "Jeden zivot. Vlastni hardcore vikend pro celou partu.", "Jeden zivot. Vlastny hardcore vikend pre celu partiu."),
        ("rpg", "RPG / questing worlds", ["rpg", "prominence", "dawncraft", "craft to exile", "questing"], "minecraft rpg modpack", "Licensed RPG modpack or Paper + quest plugins", 10,
         ["Pin one server pack and document its client requirements.", "Tune progression and boss spawning for a small persistent group.", "Test quests, party saves, economy and rollback before sale."],
         ["High content-maintenance cost", "Large client downloads"], "Vase parta, vlastni RPG svet. Pripravene questy i server.", "Vasa partia, vlastny RPG svet. Pripravene questy aj server."),
        ("vanillaplus", "Cozy / Vanilla+ co-op", ["vanilla+", "vanilla plus", "cozy minecraft", "better minecraft", "better mc"], "minecraft vanilla plus", "Paper or a lightweight, licensed Vanilla+ modpack", 4,
         ["Choose a bounded feature set: proximity voice, claims, sleep vote and cosmetics.", "Make an optional Geyser/Floodgate profile only after compatibility testing.", "Test permissions, abuse controls, voice ports and backup restoration."],
         ["Broad category; weak differentiation", "Voice chat requires extra UDP configuration"], "Klidny Minecraft pro kamarady. Vlastni svet, zadne starosti.", "Pokojny Minecraft pre kamaratov. Vlastny svet, ziadne starosti."),
        ("civilization", "Civilization / social experiments", ["civilization", "civilisation", "civilizace", "civilizacia", "100 players", "100 hracu"], "minecraft civilization", "Paper + teams, borders and event tooling", 8,
         ["Start with a scheduled, whitelisted creator event rather than an always-on network.", "Configure team borders, stages, spectator access and moderator audit logs.", "Load-test the expected simultaneous players and pre-generate the map."],
         ["Needs creators and moderators", "Peak concurrency is expensive"], "Vlastni civilizacni event. Tym, mapa a pravidla pripraveny.", "Vlastny civilizacny event. Tim, mapa a pravidla pripravene."),
        ("skyblock", "SkyBlock / OneBlock co-op", ["skyblock", "sky block", "oneblock", "one block"], "minecraft oneblock", "Paper + licensed island and economy plugins", 4,
         ["Ship a private-group island preset with protected ownership.", "Test island resets, co-op invites, generators and trade exploits.", "Differentiate with short creator challenges and Czech/Slovak onboarding."],
         ["Mature, crowded format", "Economy exploits"], "Vlastni OneBlock vyzva pro partu. Ostrov za 2 minuty.", "Vlastna OneBlock vyzva pre partiu. Ostrov za 2 minuty."),
        ("horror", "Horror / survival events", ["horror", "from the fog", "cave dweller", "fear nightfall"], "minecraft horror modpack", "A server-compatible, licensed horror modpack", 6,
         ["Check that the pack supports dedicated servers; some horror mods are client-only.", "Publish content warnings and an opt-in private event preset.", "Test mob spawning, save integrity and a clean event reset."],
         ["Seasonal spikes", "Client-only mods", "Limited replayability"], "Hororovy Minecraft vecer s partou. Pripraveny server.", "Hororovy Minecraft vecer s partiou. Pripraveny server."),
        ("crossplay", "Crossplay / social economy", ["crossplay", "cross-play", "geyser", "bedrock java", "towny", "earth smp"], "minecraft crossplay server", "Paper + Geyser/Floodgate + claims/economy", 6,
         ["Pin compatible Java/Bedrock versions and expose the configured UDP port.", "Protect account linking, permissions and economy from edition-specific exploits.", "Test login, inventories, claims and purchases from both editions."],
         ["Edition compatibility updates", "Economy moderation", "Payment compliance"], "Java i Bedrock v jednom svete. Server pro celou partu.", "Java aj Bedrock v jednom svete. Server pre celu partiu."),
    ]
    return [Candidate(*row) for row in rows]


def discovered_pack(project_id: str, title: str, slug: str) -> Candidate:
    return Candidate("pack-" + project_id, title[:80], [title[:80], slug], title[:80],
                     "Verify the project license, dedicated-server files and exact loader before packaging", 8,
                     ["Validate server support and redistribution rights directly with the project.",
                      "Build a pinned server + client manifest and a clean restore procedure.",
                      "Run a private 6-10 player load test before publishing a template."],
                     ["Newly discovered hypothesis", "RAM estimate is provisional", "License and server support require review"],
                     "Vlastni modpack server pro partu. Brzy v testovani.",
                     "Vlastny modpack server pre partiu. Coskoro v testovani.", project_id)
