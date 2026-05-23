# Deals watcher

GitHub Actions runs `.github/workflows/check-deals.yml` every 6 hours and on manual dispatch.

Required repository secrets:

1. Open `https://github.com/matthiasSchedel/apple-silicon-classics/settings/secrets/actions`.
2. Add `TELEGRAM_BOT_TOKEN` from the existing `telegram-send` config.
3. Add `TELEGRAM_CHAT_ID` with Matthias's Telegram user ID.
4. After the PR is merged and secrets exist, run `gh workflow run check-deals.yml`.

The action updates `data/price-history.json` and commits it back when prices change. Alerts fire for watch-price crossings, configured discount drops, new observed lows after the first baseline check, and new Fanatical bundle matches.
