# Upgrade Final Vector

This directory holds the shared runtime embedding artifact used by the local automation path.

- Runtime default: `upgrade_final_vector/embeddings_upgrade_final.pkl`
- Builder: `작동중코드/build_upgrade_final_vector.py`
- Sources: current final vector, external vectors, local account combined vectors, and local account text-only vectors
- Disk store: generated locally as `embeddings_upgrade_final_diskstore/` and not required in git

Large pickle artifacts should be committed through Git LFS. Local disk-store files are reproducible from the pickle.
