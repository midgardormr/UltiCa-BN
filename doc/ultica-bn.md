# UltiCa for Bright Nights

Graphics and bindings for UltiCa, ChibiUltica and AltiCa in
[Cataclysm: Bright Nights](https://github.com/cataclysmbn/Cataclysm-BN).

## Building

Install Python 3.12 or newer and the build dependencies:

```sh
python -m pip install 'pyvips[binary]' pillow tqdm
python tools/build_bn_tileset.py UltimateCataclysm build/UltimateCataclysm
python tools/build_bn_tileset.py Chibi_Ultica build/Chibi_Ultica
python tools/build_bn_tileset.py Altica build/Altica
```

Output directories must be empty and outside the source pack.
The build checks sprites, bindings, offsets, states and tint masks, and converts
vehicle rotation banks to BN's N/W/S/E order. Furniture keeps its source order.

## Releases

Run **Bright Nights UltiCa builds** on `ultica-bn` with **Publish the checked
batch as a release** enabled. This builds and checks all three packs before
publishing `UltimateCataclysm.zip`, `ChibiUltica.zip` and `Altica.zip`.
Titles and tags use `UltiCa-BN-YYYY-MM-DD`, with Moscow dates and `.2`, `.3`, etc.
for additional releases on the same day. Pushes do not publish releases.

## Upstream sync

**Weekly BN upstream sync** runs on Mondays at 07:17 UTC (10:17 Moscow).
It updates the `master` mirror and merges upstream into `ultica-bn` after all
three packs pass their checks. Conflicts and failed checks leave a review PR.
The workflow also supports manual runs. Repository Actions must allow PR
creation and branch writes.
