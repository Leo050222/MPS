# Split JSON by problem_id / Problem_ID

This repo contains dataset JSON files where a single `.json` may contain multiple problems.

The script `util/split_json_by_problem_id.py` scans one or more root directories recursively and writes **one JSON file per problem** into the **same directory** as the source JSON file.

## Dry run (recommended first)

```bash
python util/split_json_by_problem_id.py \
  data/smp_100_verified_non-instead \
  data/smp_100_verified_non-instead_and_non-question \
  --dry-run --verbose
```

## Actually write files

```bash
python util/split_json_by_problem_id.py \
  data/smp_100_verified_non-instead \
  data/smp_100_verified_non-instead_and_non-question
```

## Notes

- The output filename is `{problem_id}.json` (Windows-safe). The script recognizes `problem_id` and `Problem_ID`.
- If `{problem_id}.json` already exists, the default behavior is to write `{problem_id}_2.json`, `{problem_id}_3.json`, ...
- Use `--overwrite` if you prefer overwriting existing `{problem_id}.json`.
- Use `--limit N` to process only the first N JSON files while testing.
