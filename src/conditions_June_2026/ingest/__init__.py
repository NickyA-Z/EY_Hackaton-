"""Location Agent ingest layer: any native venue-data format -> one common data model.

Every source module exposes ``parse(path) -> pandas.DataFrame`` in the common schema
(see ``ingest.schema``). Sources are wired up in ``ingest.registry``; adding a new
format (GPX track, coach Excel sheet, ...) means one new module + one registry line.
"""
