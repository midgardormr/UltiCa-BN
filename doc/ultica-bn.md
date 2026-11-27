# UltiCa for Bright Nights

The `ultica-bn` branch adds authored Bright Nights artwork and bindings to
UltiCa, ChibiUltica and AltiCa. Credits and upstream licenses remain in place.
Contextual vehicle selection and its generated sprite banks are excluded.

## Building and compatibility

Install Python 3.12 or newer and the compositor dependencies:

```sh
python -m pip install 'pyvips[binary]' pillow tqdm
python -m unittest discover -s tools/tests
python tools/build_bn_tileset.py UltimateCataclysm build/UltimateCataclysm
python tools/build_bn_tileset.py Chibi_Ultica build/Chibi_Ultica
python tools/build_bn_tileset.py Altica build/Altica
```

Outputs must be empty directories outside the source pack. The wrapper composes
sources, copies pack metadata, adapts native vehicle rotation banks to BN's
N/W/S/E convention and checks the result. Furniture and terrain retain their
source rotation banks, reverse states and native orientation flags.
No orientation sidecar or contextual vehicle metadata is generated.

[BN #10977](https://github.com/cataclysmbn/Cataclysm-BN/pull/10977) pins the bundled
DDA tilesets before their rotation convention changed. The checker compares every
registered source binding, state, frame, canvas, anchor and tint-mask bank with
the compiled atlas. It derives these comparisons from current sources, so an
ordinary upstream artwork update does not require regenerating a frozen
inventory of stock sprite hashes.

Additional required IDs and reference directions can be checked with an external
policy kept outside the fork:

```sh
python tools/build_bn_tileset.py UltimateCataclysm build/UltimateCataclysm --policy /path/to/local-policy.json
```

CI runs source/atlas validation without that optional local file.
This is a pack integrity check; it does not replace testing in the game.

## Editing artwork and bindings

Authored additions live in `pngs_bn_artwork*`; gates and solar panels have their
own registered sheets. Chibi has private equipment overlays; AltiCa and Chibi
share compatible artwork through source links. Keep bindings and PNGs in sheets
with their intended canvas and anchor. Reuse existing sprite names for aliases.
The solar bank contains three panel types and protective glass, each in two
views, under the original upstream names.

Tint masks apply to body parts and protect details including embedded wheel
rims. They are copied from existing masks, deduplicated by pixels and placement,
and compiled alongside FG/BG banks. Cracks, solar panels and equipment do not
receive body paint masks. Preserve original PNGs and mask channels when editing;
mask rotation and variation banks must match their artwork banks.

## CI and releases

CI means automated checks and builds on changes. **Bright Nights UltiCa builds**
runs local tests and builds all three packs. Pushes do not publish releases.
To publish, run that workflow on `ultica-bn` and enable **Publish the checked
batch as a release**. A batch contains `UltimateCataclysm.zip`, `ChibiUltica.zip`,
`Altica.zip`. Release titles and tags use `UltiCa-BN-YYYY-MM-DD`, with Moscow
dates. Additional releases on the same day use `.2`, `.3` and so on.

## Upstream updates

**Weekly BN upstream sync** is scheduled for Mondays at 07:17 UTC (10:17 Moscow).
GitHub schedules run from the default branch, `ultica-bn`. Manual dispatch is
also available.
The workflow updates the `master` mirror, prepares an upstream merge and builds
all three packs before advancing `ultica-bn` to the checked commit. A changed
branch head prevents promotion. Conflicts or failed checks leave a review PR
with the run link. Repository Actions must allow PR creation and branch writes.
Release publication remains a separate manual action.
