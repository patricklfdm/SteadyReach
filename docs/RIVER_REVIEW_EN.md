# Reviewing a 1D river reach

**English** | [简体中文](RIVER_REVIEW_CN.md) | [River workflow](RIVER_REACH_EN.md)

## On the geometry preview

Open **Section directions**. Each cut is compared with the normal to the mapped channel using two distances tied to adjacent section spacing. A turn that follows a bend can remain in place. Different local and wider directions identify a bend worth inspecting. Consistent skew (at least 22° locally and 18° at the wider scale, with directions agreeing within 12°) qualifies for a bounded rotation search. Those thresholds guide inspection. Rotation is limited to 30° and requires a unique centerline crossing, finite DEM elevations and compatibility with nearby sections. For a computed reach, candidate rotations are also screened against the previous native stage at previously dry sections. Recheck all endpoints after the new solve. A locked bank selection can still move its station label when a straight cut is extended to the left. Its map position is preserved.

Use each **section profile** to compare the proposed left and right banks, their competing stations and slope-break support across three scales. A distinct, consistent pair may be staged in the editable draft. Terraces, competing shoulders, weak agreement and structures can require judgment. A sampled DEM bank is an inference. Click a different point or type its station to choose another location.

A dry section end may stop short of a second floodplain flow path. After a Q100 solve, SteadyReach checks large changes in native left/right flow share between neighbors. Where evidence warrants, it samples a strip between their same-side overbanks and tests for a connected low route at the lower of the two stages and with an interpolated stage. Missing elevations, an intervening ridge or a stage-dependent path are reported separately. Inspect imagery, levees, secondary channels and the neighboring profiles. The **lateral coverage** alternative requires an explicit choice before it can be adopted. Only a new hydraulic calculation can show the effect of the proposed footprint.

## Before and after a calculation

On the parameter page, inspect the **key river inputs** including Q, channel and overbank roughness, bed representation and end conditions. Check the stated basis and competing values. If the only bed evidence is a surface DEM, report the calculation as conditional. Use the final confirmation when the displayed inputs describe the intended case.

On the result page open **Suggested next steps**. Expand a group to see the affected stations and native codes. **Profile and neighbors** opens the computed station with its adjacent reaches visible for comparison. **Comparison with previous calculation** shows water levels, changes in bank positions and Q100 left/right flow shares at matching centers. A small change in stage may coexist with a large redistribution of overbank flow.

For a boundary or roughness sensitivity run, select a range tied to the site, review the proposed cases and confirm the batch. The results give the largest signed difference, its station, and the list of stations above the internal 0.10 ft screen for each tested profile. A zero response applies only to that tested range and model. Use observed flood levels or surveyed profiles for independent validation.

## How many operator actions?

Expand **Recorded operations for this project edition**. The count measures successful requests, such as adopting a layout, saving edited fields and confirming computation. A single batch consent can start multiple calculations. Older editions may have only partial history. Reading a map, discussing an assumption, reading external studies, elapsed review time and individual mouse clicks are outside the count. The saved receipts hold the route and operation counts and omit entered parameter values and reviewer identity.
