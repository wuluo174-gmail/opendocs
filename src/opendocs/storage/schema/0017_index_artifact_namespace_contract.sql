ALTER TABLE index_artifacts RENAME COLUMN artifact_path TO namespace_path;

UPDATE index_artifacts
SET namespace_path = CASE
    WHEN instr(namespace_path, '/.dense_hnsw_bundles/') > 0 THEN
        substr(
            namespace_path,
            1,
            instr(namespace_path, '/.dense_hnsw_bundles/') - 1
        )
        || '/'
        || substr(
            substr(
                namespace_path,
                instr(namespace_path, '/.dense_hnsw_bundles/') + length('/.dense_hnsw_bundles/')
            ),
            instr(
                substr(
                    namespace_path,
                    instr(namespace_path, '/.dense_hnsw_bundles/') + length('/.dense_hnsw_bundles/')
                ),
                '/'
            ) + 1
        )
    ELSE namespace_path
END;
