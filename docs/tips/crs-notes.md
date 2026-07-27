# CRS notes for South Carolina work

## The one you want

**EPSG:3361 — NAD83(HARN) / South Carolina (ft).**

South Carolina is a single-zone state, so there's no north/south choice to get
wrong. The near neighbours, and why you might see them:

| Code | Datum realisation | Units |
|---|---|---|
| **3361** | NAD83(HARN) | feet |
| 3360 | NAD83(HARN) | metres |
| 2273 | NAD83 (original) | feet |
| 6570 | NAD83(2011) | feet |

They differ by the datum realisation, not the projection. Between NAD83,
NAD83(HARN) and NAD83(2011) the shift in South Carolina is at the centimetre-to
-decimetre level — invisible on a site plan, real on a survey control sheet. If
a survey came in on 2273 and your project is 3361, QGIS will reproject on the
fly and the difference will be smaller than your linework. Don't let that talk
you into mixing them in one dataset; just don't panic if you find both.

## Feet here means international feet

This is the useful part. Most US states define their state plane feet as **US
survey feet** (1200/3937 m ≈ 0.30480061 m). South Carolina is one of the
handful that adopted the **international foot** (0.3048 m exactly).

So EPSG:3361 has a unit conversion factor of exactly 0.3048, and the `ft` vs
`ftUS` trap that bites people in most states does not exist in your data. You
can take a coordinate at face value.

The trap in states that do use ftUS: the two feet differ by 2 parts per
million. On a 100 ft dimension that's 0.0002 ft — nothing. On a State Plane
northing of 600,000 ft it's **1.2 ft**, which is a fence in the wrong place.
The error scales with the coordinate, not the distance, which is exactly why it
survives every sanity check made on a small drawing.

Field Kit reads the conversion factor from the layer's CRS, so this is handled
either way. The *Map units* parameter on the sheet tools exists only for the
case where a layer has no CRS or a wrong one and you need to force it.

## Sheet sizes in EPSG:3361

At 1" margins, landscape:

| Paper | 1"=20' | 1"=40' | 1"=60' | 1"=100' |
|---|---|---|---|---|
| Letter (8.5×11) | 180 × 130 ft | 360 × 260 ft | 540 × 390 ft | 900 × 650 ft |
| Tabloid (11×17) | 300 × 180 ft | 600 × 360 ft | 900 × 540 ft | 1500 × 900 ft |
| ARCH D (24×36) | 680 × 440 ft | 1360 × 880 ft | 2040 × 1320 ft | 3400 × 2200 ft |

The Sheet count estimator produces the equivalent for your actual coverage,
along with how many sheets each row costs.

## Things that go wrong

**A layer that lands at 0,0 or in the ocean off Africa.** Its CRS is wrong or
missing, not its coordinates. Set the layer's CRS (right-click → Properties →
Source) rather than reprojecting it — reprojecting bad coordinates just moves
them somewhere else wrong.

**A layer 3× too big or too small.** Feet interpreted as metres, or the
reverse. Same fix: correct the CRS assignment, don't reproject.

**Project CRS vs layer CRS.** QGIS reprojects on the fly, so a mixed project
looks fine on screen while every measurement, buffer distance and sheet size
you type is in the *project's* units. Set the project CRS to 3361 and leave it.

**Geographic CRS (EPSG:4326) as the project CRS.** Map units become degrees,
and every distance parameter in every tool becomes meaningless. The sheet tools
refuse outright rather than producing a grid measured in degrees.
