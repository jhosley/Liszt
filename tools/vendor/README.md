# Vendored helpers

`add_slide.py`, duplicates a PowerPoint slide with all the package bookkeeping
(content types, relationships, `<p:sldIdLst>` registration). `tools/render_slides.py`
needs it only when APPENDING a slide pair the template does not already contain.

It lives here so the renderer carries its own copy and needs nothing installed
alongside it. If your template deck already has a pair for every scenario, the renderer
never calls it.
