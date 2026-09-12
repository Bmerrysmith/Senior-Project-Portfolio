"""
Data refinement pipeline for the Village of Estero meetings dataset.

Stages (bronze -> silver -> gold):

    bronze   : raw CSVs scraped/exported from source systems
               (currently app/data/meetings.csv, app/data/documents.csv)
    silver   : validated, cleaned, typed rows + a separate rejects file
               (written to app/data/silver/)
    gold     : the slice the API serves to ArcGIS — silver minus future
               placeholders, joined with reference data when needed
    reference: human-curated YAML in app/data/reference/

Run the full pipeline:

    python -m app.pipeline.run

Reference data, schemas, cleaning, and loaders are split into submodules so
each stage is small, isolated, and testable.
"""
