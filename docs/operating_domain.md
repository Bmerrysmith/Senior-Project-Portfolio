# AgriNav Perception Operating Domain v0.1

**Status:** research draft; unresolved fields block a deployment claim  
**Date:** 2026-07-20  
**Scope:** plant classification and image-space localization only

## Fixed boundaries

| Dimension | Current boundary |
|---|---|
| protected biological class | cultivated rice (`rice`); no other protected crop is currently supported |
| affirmative target class | biological weeds represented by reviewed target-domain data |
| ambiguous class | unresolved vegetation, aquatic vegetation, and weedy/volunteer rice remain nonactionable |
| output | image-space masks/polygons, derived boxes, class/role, uncertainty, source and model provenance |
| prohibited output | spray/treatment commands, ground coordinates, path planning, actuator timing, or autonomous robot control |
| sensing | RGB only for the first controlled study; multispectral/depth may appear only as separately reported ablations |
| canonical annotation | human-reviewed `rice_protect`, `weed_target`, and `unknown_vegetation` masks/polygons |
| resolution | preserve native raw imagery; 512x512 is an existing derived training view, not yet an approved operating resolution |
| fail behavior | empty, invalid, uncertain, OOD, stale, or unreviewed evidence returns no affirmative weed target |

## Research coverage, not yet an operating promise

The received data include:

- rice from vegetative through reproductive stages;
- flooded paddy, dry/upland imagery, canopy and top-down views;
- field material from China, India, Japan, the Philippines, and Tanzania through RiceSEG;
- water, reflection, glare, duckweed, senescence, panicles, dense foliage, and partial plants;
- a target detector export dominated by rice boxes with rare weeds and incomplete provenance.

These sources support transfer-learning research. They do **not** establish performance for every listed country, field, camera, stage, or condition. A condition enters the claimed operating domain only after it has enough independent train/validation groups and a locked evaluation slice.

## Required challenge/OOD coverage

Keep the following as explicit test slices even when the final operating domain excludes them:

- no-weed/crop-only, bare ground, and no-rice scenes;
- non-target and unknown plants;
- weedy rice and rice-like grasses;
- tiny, occluded, overlapping, truncated, submerged, or border plants;
- water reflection, glare, shadow, duckweed, residue, mud, and senescence;
- blur, compression, exposure failure, lens dirt/droplets, and corrupt frames;
- unfamiliar field/site/session/camera/height/view/weather;
- people, animals, tools, equipment, and unrelated scenes.

OOD/challenge data are for measuring rejection and failure modes. They are not silently reclassified as background.

## Decisions still required from the project owner

These values cannot be inferred safely from the received archives:

1. intended country/region, field type, and cultivation method (flooded paddy, upland, or both);
2. target growth-stage window for first use;
3. exact weed species that count as biological targets and the policy for weedy/volunteer rice and duckweed;
4. camera model, lens, mounting angle/height, image cadence, native resolution, and expected blur/exposure range;
5. minimum weed size and maximum crop/weed occlusion at which a target proposal is useful;
6. target inference hardware, numeric precision, and operating resolution for the p99 latency claim;
7. protected-crop overlap/false-target budget used to select the weed-recall operating point;
8. first independent sites/sessions reserved for validation, sealed test, and OOD challenge.

Until these are approved and versioned, results must be described as rice/weed perception research on named datasets—not as performance throughout a deployment operating domain.

