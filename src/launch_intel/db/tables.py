# TODO(phase-later): ORM tables mirroring models/launch.py, models/source.py,
# models/evidence.py — including a pgvector embedding column on the launches
# table for dedup/embeddings.py to write to. Mirror Launch's fields exactly;
# do not let the ORM schema drift from the shared Pydantic contract.
