# Digitising without leaving gaps

Half of this problem is a tool, and half of it is three settings nobody turns
on. The settings are worth more than the tools, because they stop gaps
happening instead of cleaning them up afterwards. Set these first.

---

## The three settings that do the work

### 1. Snapping, configured properly

*Project → Snapping Options*, or the magnet in the toolbar.

- Turn snapping on (the magnet), then switch the mode from **Active layer** to
  **All layers** or **Advanced**. Active-layer-only snapping is the single
  biggest source of gaps: you snap beautifully to the layer you're drawing and
  ignore the parcel line you're supposed to meet.
- Set the type to **Vertex and Segment**. Vertex-only means you can only land
  on existing corners, so a new corner halfway along someone else's edge slides
  off it.
- Set the tolerance in **pixels**, not map units, around 12-15. In map units,
  a tolerance that works zoomed in does nothing zoomed out.
- Tick **Snapping on intersection**. Lets you land exactly where two lines
  cross even though there is no vertex there.
- In Advanced mode you get a per-layer table - snap to the ROW and parcel
  layers, ignore the aerial index and the labels.

### 2. Topological editing

Same dialog, the icon that looks like two shapes sharing an edge.

With it on, moving a vertex that two polygons share moves it in **both**.
Without it, you move one and open a gap you will not see until you print. Turn
it on and leave it on.

It only applies to geometries that already share a vertex exactly. Two polygons
whose edges merely run alongside each other are not topologically connected -
that's what *Snap to layer and verify* is for.

### 3. Avoid overlap (the old "avoid intersections")

Also in Snapping Options: the column that lets you pick layers to avoid
overlapping.

Draw a new polygon sloppily over its neighbour and QGIS trims the new one back
to the shared edge automatically. This is the closest thing QGIS has to
"digitise a coverage" mode, and it gives you an exact shared edge for free.

The catch: it only clips the *new* geometry against the layers you tick, and it
can produce surprising results if the neighbour has invalid geometry. Fix
geometries first.

---

## Tracing

Press `T` while in a digitising tool, or use the trace button. With snapping
on, clicking two points on an existing feature makes the new geometry follow
that feature's edge between them, curve for curve.

- The **tracing offset** box (next to the trace toggle) traces at a fixed
  distance from the feature. Positive one way, negative the other. Handy for
  a sidewalk parallel to a ROW line - but for anything more than a quick line,
  *Right of way from centerline* gives you a repeatable result.
- Tracing follows what is *rendered*, so if the layer is filtered or scale-
  limited it will not trace what you cannot see.
- It will not trace across a gap. If tracing stops halfway along what looks
  like a continuous edge, you have just found a topology break - run *Close
  dangling line ends* on the linework.

## The Advanced Digitising panel

`Ctrl+4`, or *View → Panels → Advanced Digitizing*. This is the panel that
turns QGIS into something you can draw a ROW with.

While drawing, type a value into a box and press `Enter` to lock it:

| Box | Locks |
|---|---|
| `d` | distance from the last vertex |
| `a` | absolute angle (bearing) |
| `x` / `y` | an exact coordinate |

So a 150-foot leg at a bearing of 45 degrees is `d` 150, `a` 45, click. Prefix
an angle with `a` relative to the previous segment for deflection angles. This
is how you draw geometry that closes exactly instead of nearly.

---

## When it has already gone wrong

Cleaning up, roughly in the order to try:

1. **Vector → Geometry Tools → Check Validity**, or *Fix geometries*, first.
   Every other tool behaves badly on invalid input.
2. **Field Kit → Editing → Fill gaps between polygons** in *Report only* mode.
   Look at what it found and how big the gaps are before you fill anything -
   the gap layer's `area` column tells you what threshold to use.
3. **Field Kit → Editing → Snap to layer and verify** if the polygons are
   close but not sharing vertices. Start with a small tolerance and the move
   guard set; look at the displacement vectors before accepting the result.
4. **Field Kit → Editing → Close dangling line ends** for linework that nearly
   meets, then *Polygonize* if you are building polygons from it.
5. The **Geometry Checker** core plugin (*Vector → Check Geometries*) for a
   broad audit. It finds more classes of error than anything here, and its
   fixes are harder to review - use it to find, then decide.

## What none of this fixes

Two datasets from different sources with a genuine 3-foot disagreement about
where the property line is. No tolerance setting resolves that; someone has to
decide which one is right. Snapping the wrong one to the right one just makes
the disagreement invisible.
