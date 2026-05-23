# Classics on Apple Silicon

Public GitHub Pages site for voting on classic Windows games to test next on Apple Silicon Macs.

The site is pure static HTML/CSS/JS. Voting uses GitHub Issues: every wishlist game has one issue labeled `wishlist`, and the page reads `+1` reaction counts from the anonymous GitHub REST API.

## Add a game

1. Add the game to `games.json`.
2. Create a matching issue titled `Wishlist: <Game>` with label `wishlist`.
3. Keep `issueTitle` exactly equal to the GitHub issue title.
4. If the game becomes verified, move it from `wishlist` to `tested` and link its recipe repo.

No backend, tokens, game files, installers, or private notes are stored in this repo.
