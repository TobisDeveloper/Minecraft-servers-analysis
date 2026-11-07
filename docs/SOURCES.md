# Source configuration

Copy `config.example.json` to `config.local.json`, or run `python -m trendfinder init-config`. Lists replace defaults; objects merge. Restart after editing. Keep target markets `["CZ", "SK"]`. Google Trends defaults to `today 12-m`; its scoring assumes weekly points.

## Watch terms and creators

```json
{
  "watch_terms": [{"name": "Your format", "query": "minecraft your format", "aliases": ["unique phrase", "Czech name"]}],
  "youtube": {
    "backend": "auto",
    "search_queries": ["Minecraft SMP CZ SK", "Minecraft nový server", "Minecraft but"],
    "channel_ids": [],
    "local_creator_names": ["SirYakari", "GEJMR", "StudioMoonTV"]
  }
}
```

Use actual `UC...` channel IDs from official pages. API keys enable search, view and subscriber statistics. Watched channels also use public Atom feeds if `feeds` is enabled. Backends: `auto`, `api`, `public`. Public metadata can lack dates/counts; they are not reconstructed. Chronological search is used rather than assuming a stable YouTube "Trending gaming" endpoint.

## TikTok / Facebook / other communities

There is no default privileged TikTok/Facebook connection. Supply an authorized RSS/Atom feed from your own pipeline or a permitted provider; it is polled each scan:

```json
{"feeds": [{"name": "Authorized CZ/SK creators", "url": "https://your-provider.example/feed.xml", "market": "CZ/SK", "family": "creators"}]}
```

Replace the placeholder with a real URL. Families: `community`, `creators`, `reports`. Metadata-only feeds do not supply view/subscriber counts. No feature asks for private-group passwords or browser cookies.

Alternatively place UTF-8 CSVs in `data/imports/` without config, or `imports/` beside the selected config. An explicit `import_dir` overrides this. Relative paths resolve beside the config.

```csv
title,url,published_at,market,family,text
"How do I host Cobblemon with friends?",https://your-authorized-source.example/post,2026-11-01T10:00:00+00:00,SK,community,"Optional body"
```

`title,url,published_at,market` required; family defaults to community. `text` is used for matching, not persisted. Markets: CZ, SK, CZ/SK, GLOBAL, US, GB. Use ISO dates with offsets; naive dates are UTC. Invalid/future/expired rows are ignored. Limits: 30 files, 5 MB/file, 10,000 rows/file. [Schema example](../examples/community-import.csv) uses an expired placeholder row. Imports are labeled user-supplied, not platform-verified.

## Discord

Set `DISCORD_BOT_TOKEN` and numeric `discord_channel_ids`. Use an authorized bot with View Channel, Read Message History and any required Message Content intent. It samples 100 messages/channel and persists only a generic label, date, candidate, intent classification and permission-gated citation; no usernames or message bodies. Do not distribute private-community citations without permission.

## Network access

| Feature | Hosts |
|---|---|
| Packages | pypi.org, files.pythonhosted.org |
| Modrinth / CurseForge | api.modrinth.com / api.curseforge.com |
| Official YouTube | www.googleapis.com |
| Public YouTube/RSS | www.youtube.com, youtube.com, possibly youtubei.googleapis.com |
| Trends / report RSS | trends.google.com / news.google.com |
| Reddit | www.reddit.com |
| Lists | craftlist.org, minecraft-mp.com, minecraft-server-list.com |
| Discord | discord.com |
| Custom feeds | Your provider hostname |
| Local AI | Loopback 127.0.0.1:11434 |

Keep TLS verification enabled. Source metadata is untrusted: dashboard text is escaped, non-HTTP citations rejected, API actions origin-checked and CSV formula prefixes neutralized. Credential-bearing request URLs are not logged. Imported titles may still contain sensitive information; store/export responsibly.

## Upstream references

- [YouTube Data API](https://developers.google.com/youtube/v3/docs), [quota](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Modrinth API](https://docs.modrinth.com/api/)
- [CurseForge API](https://docs.curseforge.com/rest-api/)
- [Discord message API](https://discord.com/developers/docs/resources/message#get-channel-messages)
- [pytrends](https://github.com/GeneralMills/pytrends) — unofficial; rate-limit/maintenance risk
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — unofficial public metadata fallback

An anti-bot response, quota limit or changed markup is a collection limitation, never proof of zero demand. Unit tests mock these interfaces; verify access on your network.
