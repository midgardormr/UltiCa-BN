# UltiCa for Bright Nights

The `ultica-bn` branch adds Bright Nights artwork and bindings to UltiCa,
ChibiUltica and AltiCa.

## Building

Build and check the packs with:

```sh
python tools/build_bn_tileset.py UltimateCataclysm build/UltimateCataclysm
python tools/build_bn_tileset.py Chibi_Ultica build/Chibi_Ultica
python tools/build_bn_tileset.py Altica build/Altica
```

The build script copies the pack metadata, adapts furniture and terrain
orientation, and checks all bindings against `tools/bn-compatibility.json`.

The **Bright Nights UltiCa builds** workflow checks and builds all three packs on
source changes. Pushes do not publish releases. To publish a batch, open the workflow
in Actions, choose **Run workflow** on `ultica-bn`, and enable **Publish the checked
batch as a release**.
A release contains `UltimateCataclysm.zip`, `ChibiUltica.zip`, `Altica.zip`, and
`SHA256SUMS`.
Tags use `bn-YYYY-MM-DD.N`, with dates in Moscow time and a sequence number
for multiple releases on the same day.

## Editing bindings

BN bindings use sprite names and live in `pngs_bn_bindings*/bindings`.
The directories are grouped by display offset: keep each definition in the
sheet with its required offset, even when it references a PNG from another
sheet. Shared Chibi bindings link to the corresponding UltiCa files.
AltiCa shares the BN sheets and keeps its own character and clothing artwork.

Named tint masks are compiled with the sprite bindings. `BN_ORIENTATION.json`
records the furniture and terrain settings that require matching BN support.

## Upstream updates

**Weekly BN upstream sync** runs every Monday at 07:17 UTC (10:17 Moscow time).
It updates `master` from upstream, prepares a merge into `ultica-bn`, and runs
the tests and builds for all three packs before updating the BN branch.
Conflicts and failed checks leave a PR open with a link to the logs.
If GitHub rejects a push, for example when upstream changes workflow files,
the update is left for manual review in a PR.

The workflow can also be run manually from Actions. Release publication remains
a separate manual action.
